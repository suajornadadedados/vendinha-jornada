"""R5 — nothing sensitive leaves this process, and the question is reachability.

`docs/testes.md` §1 draws the line these tests sit on: a unit test says the
function redacts correctly, a security test says the un-redacted value has no path
out. Both matter here, and the second is the one that produces a guarantee.

Since ADR-010 the traces go to Langfuse Cloud, so "out of this process" means "out
of our infrastructure". That is why REQ-4 of S-02 is an invariant of release rather
than hygiene: with the export hook broken, the leak is not to a container on the
same machine.

The export tests are the important ones. They do not ask the redactor whether it
works — they build an OpenTelemetry batch shaped like the one Langfuse actually
hands the hook, including a span from a third-party instrumentation scope our code
never touches, and assert that what comes back out is clean. That is the difference
between "we remembered to redact" and "the path does not exist".

Credentials ride along under ADR-012: the provider API key is a second class of
secret inside the process, and D-4 of the spec records why it is tested here rather
than in a file of its own — same seam, same boundary, and `docs/testes.md` §2
already maps that seam to this file.
"""

import io
import logging
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanData,
    OtelSpanIdentifier,
)
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.catalogo import CatalogoEmMemoria, carregar_seed
from vendinha.config import get_settings
from vendinha.config_store import InMemoryConfigStore
from vendinha.graph import build_graph
from vendinha.observability import (
    client,
    export_masking_is_installed,
    install_log_redaction,
    mask_otel_spans,
    redaction_is_installed,
)
from vendinha.redaction import KNOWN_VALUES, Redactor, redactor
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Subagent,
    registrar,
)


def _sem_catalogo() -> Subagent:
    """O subagent da recomendação sem nenhuma tool.

    Este arquivo não mede recomendação — mede o mascaramento de PII. Um subagent
    sem tool mantém o grafo no formato de uma volta só, que é o que estas
    asserções descrevem, e deixa o laço de tools para quem o testa.
    """
    return registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])


# Keys shaped like the real thing and belonging to nobody. The guardrail in
# CLAUDE.md is absolute: no real credential in the repository, not even in a test.
FAKE_PROVIDER_KEY = "sk-ant-api03-" + "A" * 40
FAKE_LANGFUSE_KEY = "sk-lf-" + "b" * 32


def _span(scope: str, **attributes: Any) -> tuple[OtelSpanIdentifier, OtelSpanData]:
    identifier = OtelSpanIdentifier(trace_id=f"trace-{scope}", span_id=f"span-{scope}")
    data = OtelSpanData(
        trace_id=identifier.trace_id,
        span_id=identifier.span_id,
        parent_span_id=None,
        name="conversa",
        instrumentation_scope_name=scope,
        instrumentation_scope_version="1.0",
        attributes=dict(attributes),
        resource_attributes={},
    )
    return identifier, data


def _export(**spans: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Run one batch through the hook and return the attributes as they would ship."""
    batch = dict(_span(scope, **attrs) for scope, attrs in spans.items())
    result = mask_otel_spans(params=MaskOtelSpansParams(spans=batch))

    shipped: dict[str, dict[str, str]] = {}
    patches = result.span_patches if isinstance(result, MaskOtelSpansResult) else {}
    for identifier, data in batch.items():
        attrs = dict(data.attributes)
        patch = patches.get(identifier)
        if patch is not None:
            for key in patch.delete_attributes:
                attrs.pop(key, None)
            attrs.update(patch.set_attributes)
        assert data.instrumentation_scope_name is not None
        shipped[data.instrumentation_scope_name] = {str(k): str(v) for k, v in attrs.items()}
    return shipped


@pytest.mark.risco("R5")
def test_a_cpf_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    """Punctuated or not — the customer types it either way, and both are the CPF."""
    for cpf in (pii_de_teste["cpf"], pii_de_teste["cpf_sem_pontuacao"]):
        redacted = redactor().text(f"pode faturar no CPF {cpf}, por favor")
        assert cpf not in redacted
        assert "[CPF]" in redacted


@pytest.mark.risco("R5")
def test_an_email_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    redacted = redactor().text(f"meu email e {pii_de_teste['email']}")
    assert pii_de_teste["email"] not in redacted
    assert "[EMAIL]" in redacted


@pytest.mark.risco("R5")
def test_a_phone_number_never_survives_redaction(pii_de_teste: dict[str, str]) -> None:
    redacted = redactor().text(f"me chama no {pii_de_teste['telefone']}")
    assert pii_de_teste["telefone"] not in redacted
    assert "[TELEFONE]" in redacted


@pytest.mark.risco("R5")
def test_a_known_name_is_masked_even_when_only_the_first_name_appears(
    pii_de_teste: dict[str, str],
) -> None:
    """The honest half of REQ-4, and the reason it is written this way.

    CPF, e-mail, phone and credentials have a shape, so a pattern finds them in any
    text. A name does not. Claiming generic name detection would mean shipping an
    NER model and a promise this project cannot keep — see D-6 in the spec. What
    the code does guarantee: once a name has been collected, that string stops
    leaving the process.

    The first name on its own is the case that matters and the one a naive
    implementation misses. A customer introduces herself as "Marta Ribeiro" once,
    and every reply after that says "Marta" — masking only the full string leaves
    the name in every turn but the first. Removing that half of the implementation
    used to leave this file green; now it does not.
    """
    full_name = pii_de_teste["nome"]
    first_name = full_name.split()[0]

    assert full_name in redactor().text(f"em nome de {full_name}"), (
        "sem contexto, um nome e so um texto"
    )

    com_o_nome = Redactor(known_values=frozenset({full_name}))
    redacted = com_o_nome.text(f"claro, {first_name}! confirmo o pedido de {full_name}")

    assert full_name not in redacted
    assert first_name not in redacted, "o primeiro nome sozinho tambem e o nome"
    assert redacted.count("[NOME]") == 2


@pytest.mark.risco("R5")
def test_a_provider_credential_never_survives_redaction() -> None:
    """ADR-012 put a third-party secret inside the process; this is half of its price."""
    for key in (FAKE_PROVIDER_KEY, FAKE_LANGFUSE_KEY):
        redacted = redactor().text(f"Authorization: Bearer {key}")
        assert key not in redacted
        assert "[CREDENCIAL]" in redacted


@pytest.mark.risco("R5")
def test_the_export_hook_scrubs_every_string_attribute(pii_de_teste: dict[str, str]) -> None:
    """The reachability test: a batch shaped like the real one, and nothing gets out.

    The `langchain` span matters more than ours. It is written by an instrumentation
    we do not control, carrying whatever the callback handler saw — and it ships
    through the same client and the same hook.
    """
    cpf = pii_de_teste["cpf"]
    email = pii_de_teste["email"]

    shipped = _export(
        **{
            "langfuse-sdk": {
                "langfuse.observation.input": f"cliente: {cpf}",
                "langfuse.session.id": "sessao-42",
            },
            "langchain": {
                "gen_ai.prompt.0.content": f"meu email e {email} e meu cpf {cpf}",
                "gen_ai.completion.0.content": f"confirmado, {cpf}",
                "gen_ai.request.model": "claude-haiku-4-5",
            },
        }
    )

    everything = " ".join(value for span in shipped.values() for value in span.values())
    for secret in (cpf, email, pii_de_teste["cpf_sem_pontuacao"]):
        assert secret not in everything, f"{secret!r} chegaria ao Langfuse em claro"

    assert "[CPF]" in everything and "[EMAIL]" in everything
    # Redaction is not deletion: a trace where every attribute is gone debugs
    # nothing, and the session id is what makes a trace findable at all.
    assert shipped["langfuse-sdk"]["langfuse.session.id"] == "sessao-42"
    assert shipped["langchain"]["gen_ai.request.model"] == "claude-haiku-4-5"


@pytest.mark.risco("R5")
def test_a_list_valued_attribute_is_scrubbed_like_a_string_one(
    pii_de_teste: dict[str, str],
) -> None:
    """R5 — ressalva R-4 da verificação da S-02, fechada aqui.

    Um atributo OTel é um escalar **ou uma sequência homogênea de escalares**, e
    `Redactor.attributes` só olhava para `str`. Uma lista de strings atravessava
    intocada: mascarada em lugar nenhum, exportada inteira.

    Na S-02 isso era latente, porque nada no processo produzia uma. Na S-03
    produz: as tools de catálogo devolvem `harmonizacao`, `ocasiao` e
    `notas_sensoriais`, e as instrumentações que não são nossas põem atributo de
    lista em span como coisa corriqueira — `gen_ai.prompt` é o exemplo óbvio.

    O outro lado do teste é o de sempre: redação não é deleção. A lista continua
    sendo uma lista, com o mesmo número de itens, e o que não é PII sobrevive.
    """
    cpf = pii_de_teste["cpf"]
    email = pii_de_teste["email"]

    batch = dict(
        [
            _span(
                "langchain",
                **{
                    "gen_ai.prompt.contents": [f"cpf {cpf}", f"email {email}", "queijo canastra"],
                    "vendinha.harmonizacao": ["vinho tinto encorpado", "café coado"],
                },
            )
        ]
    )
    resultado = mask_otel_spans(params=MaskOtelSpansParams(spans=batch))

    assert isinstance(resultado, MaskOtelSpansResult)
    patch = next(iter(resultado.span_patches.values()))
    assert patch is not None
    bruto = patch.set_attributes["gen_ai.prompt.contents"]

    assert isinstance(bruto, tuple)
    conteudos = [str(item) for item in bruto]
    assert len(conteudos) == 3, "redação não é deleção: a lista mantém o tamanho"
    assert cpf not in " ".join(conteudos)
    assert email not in " ".join(conteudos)
    assert "[CPF]" in conteudos[0] and "[EMAIL]" in conteudos[1]
    assert conteudos[2] == "queijo canastra", "o item sem PII atravessa intocado"

    assert "vendinha.harmonizacao" not in patch.set_attributes, (
        "uma lista sem nada a redigir não entra no patch — o patch é esparso"
    )


@pytest.mark.risco("R5")
def test_a_remembered_name_does_not_reach_the_export_either(
    pii_de_teste: dict[str, str],
) -> None:
    """The known-value half has to hold at the boundary, not only in the function.

    The export runs on the OpenTelemetry worker thread, with no request context —
    which is exactly why the registry is process-wide instead of a `contextvar`. A
    test that only exercised `Redactor` directly would never notice the difference,
    and the difference is the whole guarantee.
    """
    full_name = pii_de_teste["nome"]
    first_name = full_name.split()[0]

    KNOWN_VALUES.clear()
    try:
        KNOWN_VALUES.remember(full_name)
        shipped = _export(
            **{"langchain": {"gen_ai.completion.0.content": f"claro, {first_name}, ja anotei"}}
        )
        content = shipped["langchain"]["gen_ai.completion.0.content"]
        assert first_name not in content
        assert "[NOME]" in content
    finally:
        KNOWN_VALUES.clear()


@pytest.mark.risco("R5")
def test_the_export_hook_leaves_a_clean_span_untouched() -> None:
    """No patch for spans with nothing to hide — churn hides the real edits."""
    batch = dict([_span("langchain", **{"gen_ai.request.model": "gpt-5-mini"})])
    result = mask_otel_spans(params=MaskOtelSpansParams(spans=batch))
    assert result is None or not result.span_patches


@pytest.mark.risco("R5")
def test_a_price_is_not_mistaken_for_personal_data() -> None:
    """Over-masking is the failure mode nobody reports: the trace is clean and useless.

    Prices, order ids and quantities look like digits to a careless pattern, and a
    trace that redacts them is a trace nobody can debug — which is how a team ends
    up turning masking off entirely.
    """
    text = "o Canastra meia-cura sai por 89.90 e o pedido 100234 tem 3 itens"
    assert redactor().text(text) == text


CATALOGO_DO_SEED = Path(__file__).resolve().parents[2] / "data" / "catalogo"


def _catalogo_de_teste() -> CatalogoEmMemoria:
    """O catálogo que a subida confere (R-10), sem contêiner.

    `create_app` recusa subir com catálogo vazio, e é de propósito: sem `make
    seed` o agente responde "não encontrei nada" com toda a sinceridade, o que
    parece falha do modelo e é falha de setup. O teste percorre esse preflight de
    verdade em vez de contorná-lo — era essa a ressalva R-14.
    """
    return CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED))


@pytest.fixture
def logging_como_o_uvicorn_monta() -> Iterator[io.StringIO]:
    """Reproduce the logging setup uvicorn actually creates, and restore it after.

    This is the shape that made the previous implementation inert: uvicorn configures
    its own `uvicorn.*` loggers and leaves the **root with no handlers at all**. A
    test that attaches the redactor by hand never sees that, which is exactly why the
    hole survived — the test proved the function worked and said nothing about
    whether it was ever installed.
    """
    root = logging.getLogger()
    handlers_do_root = root.handlers[:]
    uvicorn_logger = logging.getLogger("uvicorn.error")
    handlers_do_uvicorn = uvicorn_logger.handlers[:]

    # Snapshot de TODOS os handlers do processo, e nao so dos dois que esta fixture
    # monta: `install_log_redaction()` cobre o processo inteiro, entao um teste que
    # rodou antes deixa formatters embrulhados em loggers que esta fixture nunca viu.
    # Sem restaurar todos, a afirmacao "ainda nao esta instalado" depende da ordem
    # dos testes — que e a forma mais chata de teste instavel.
    todos = list(root.handlers)
    for objeto in logging.Logger.manager.loggerDict.values():
        if isinstance(objeto, logging.Logger):
            todos.extend(objeto.handlers)
    formatters = {h: h.formatter for h in todos + handlers_do_root + handlers_do_uvicorn}
    for handler in todos:
        handler.setFormatter(None)

    root.handlers = []
    saida = io.StringIO()
    handler = logging.StreamHandler(saida)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    uvicorn_logger.handlers = [handler]
    uvicorn_logger.setLevel(logging.INFO)

    try:
        yield saida
    finally:
        root.handlers = handlers_do_root
        uvicorn_logger.handlers = handlers_do_uvicorn
        for h, f in formatters.items():
            h.setFormatter(f)


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("logging_como_o_uvicorn_monta")
def test_installing_log_redaction_actually_installs_something() -> None:
    """The reachability half: a no-op installer has to fail this file.

    `install_log_redaction()` returning zero means every log line in the process
    leaves unredacted, with nothing else in the suite noticing. `docs/riscos.md` R5
    says traces **and** logs.
    """
    assert install_log_redaction() > 0, "nenhum handler foi coberto — a instalacao e inerte"


@pytest.mark.risco("R5")
def test_a_traceback_never_carries_pii_or_credentials_out(
    pii_de_teste: dict[str, str], logging_como_o_uvicorn_monta: io.StringIO
) -> None:
    """The leak nobody chooses: `logger.exception` renders whatever was raised.

    The chat handler logs the exception from the provider SDK or from psycopg, and
    those carry API keys and DSNs. A filter cannot reach this — the traceback is
    rendered by the formatter, after every filter has run.
    """
    install_log_redaction()
    cpf = pii_de_teste["cpf"]

    try:
        raise RuntimeError(f"falha ao autenticar com {FAKE_PROVIDER_KEY} para o cliente {cpf}")
    except RuntimeError:
        logging.getLogger("uvicorn.error").exception("falha na sessao %s", "sessao-9")

    escrito = logging_como_o_uvicorn_monta.getvalue()
    assert "Traceback" in escrito, "o teste precisa do traceback renderizado para valer"
    assert cpf not in escrito
    assert FAKE_PROVIDER_KEY not in escrito
    assert "[CPF]" in escrito and "[CREDENCIAL]" in escrito


# Runs in a subprocess on purpose. pytest's logging plugin swaps the root handlers
# around every test call, so a test that asserts on what reaches stderr through the
# root ends up measuring pytest instead of the application. A clean interpreter is
# the only place this path looks like production.
PROVA_EM_SUBPROCESSO = """
import logging, sys
from vendinha.observability import install_log_redaction

# Exactly what uvicorn leaves behind: its own logger configured, root empty.
logging.getLogger().handlers = []
uvicorn = logging.getLogger("uvicorn.error")
uvicorn.handlers = [logging.StreamHandler(sys.stderr)]

install_log_redaction()

try:
    raise RuntimeError("deu ruim com " + sys.argv[1] + " e o cliente " + sys.argv[2])
except RuntimeError:
    logging.getLogger("vendinha.app").exception("falha na sessao %s", "sessao-7")
"""


@pytest.mark.risco("R5")
def test_the_applications_own_logger_is_covered_too(pii_de_teste: dict[str, str]) -> None:
    """`vendinha.app` has no handler anywhere, and it is the one that logs exceptions.

    uvicorn configures `uvicorn.*` and nothing else, so a record from our own module
    propagates to a root with no handlers and falls through to `logging.lastResort`,
    which has no formatter to wrap. That is the production path of the
    `logger.exception(...)` in the chat endpoint — the one that receives whatever the
    provider SDK raised. Covering the named loggers and stopping there leaves exactly
    this one open, and a falsification proved it: removing the root fallback left this
    file green until this test existed.
    """
    cpf = pii_de_teste["cpf"]
    resultado = subprocess.run(  # noqa: S603 - argv fixo, escrito neste arquivo
        [sys.executable, "-c", PROVA_EM_SUBPROCESSO, FAKE_PROVIDER_KEY, cpf],
        capture_output=True,
        text=True,
        check=False,
    )

    escrito = resultado.stderr
    assert "Traceback" in escrito, "sem traceback renderizado o teste nao prova nada"
    assert cpf not in escrito
    assert FAKE_PROVIDER_KEY not in escrito
    assert "[CPF]" in escrito and "[CREDENCIAL]" in escrito


@pytest.mark.risco("R5")
@pytest.mark.usefixtures("logging_como_o_uvicorn_monta")
def test_the_application_turns_redaction_on_when_it_starts() -> None:
    """A instalacao tem que ser provada na APLICACAO, nao na funcao.

    Este teste existe por causa de um achado da segunda verificacao independente: os
    testes provavam que `install_log_redaction()` cobre os handlers, e nenhum provava
    que o `lifespan` chega a chama-la. Apagar a chamada do `app.py` deixava a suite
    inteira verde — o mesmo buraco da rodada anterior, um nivel acima.

    A licao, registrada porque ja aconteceu tres vezes nesta spec: testar a funcao
    que faz nao e testar que alguem a chama.
    """
    assert not redaction_is_installed(), "a fixture deveria ter deixado o logging cru"

    graph = build_graph(GenericFakeChatModel(messages=iter([])), InMemorySaver(), _sem_catalogo())
    with TestClient(
        create_app(graph=graph, store=InMemoryConfigStore(), catalogo=_catalogo_de_teste())
    ):
        assert redaction_is_installed(), "a aplicacao subiu sem ligar a redacao de log"


@pytest.mark.risco("R5")
def test_the_langfuse_client_is_built_with_the_masking_hook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O gancho tem que estar NO CLIENTE, nao so existir como funcao.

    Terceira verificacao independente, achado de gravidade Alta: apagar
    `mask_otel_spans=mask_otel_spans` do construtor deixava a suite verde, e a
    aplicacao exportava CPF, e-mail e telefone em claro para o Langfuse Cloud —
    medido lendo o trace de volta pela API publica.

    E a mesma pergunta das outras duas rodadas, uma casa adiante. Nao existe teste de
    redacao que substitua este: a funcao pode estar perfeita e nunca ser chamada no
    caminho de saida. Esta e a metade "trace" do REQ-4, que a spec chama de
    invariante de release e sobre a qual o ADR-010 apoia a escolha de nuvem.
    """
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-" + "a" * 20)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-" + "b" * 20)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://127.0.0.1:1")
    get_settings.cache_clear()
    client.cache_clear()

    try:
        construido = client()
        assert construido is not None, "credencial presente e o cliente nao subiu"
        assert export_masking_is_installed(construido), (
            "o cliente Langfuse foi construido sem o gancho de redacao: "
            "todo trace desta aplicacao sairia em claro"
        )
    finally:
        client.cache_clear()
        get_settings.cache_clear()


@pytest.mark.risco("R5")
def test_a_known_name_glued_to_other_text_is_masked_too(
    pii_de_teste: dict[str, str],
) -> None:
    """Para NOME a direcao segura e mascarar demais, e isso e escolha registrada.

    A reescrita de desempenho da rodada 2 trocou substring por `\\b` em silencio, e a
    terceira verificacao pegou: um nome grudado em outro texto deixou de ser coberto.
    Nome que escapa e vazamento de PII; palavra parecida mascarada a mais e so um log
    menos bonito. Este teste fixa a escolha para ela nao mudar de novo sem alguem ver.
    """
    nome = pii_de_teste["nome"]
    partes = nome.split()
    redactor_com_nome = Redactor(known_values=frozenset({nome}))

    for texto in (
        f"usuario {nome}123",
        f"arquivo-{nome}-final.txt",
        f"{nome}s",
        f"id:{partes[1]}99",
    ):
        redigido = redactor_com_nome.text(texto)
        # Conferir TODAS as partes, e nao so a primeira: com `\b` o primeiro nome
        # ainda casava (vem seguido de espaco) e o sobrenome grudado no numero
        # escapava — a versao anterior deste teste passava com a implementacao
        # quebrada exatamente por isso.
        for parte in [nome, *partes]:
            assert parte not in redigido, f"{parte!r} escapou em {texto!r}"


@pytest.mark.risco("R5")
def test_clearing_the_registry_also_clears_the_compiled_pattern(
    pii_de_teste: dict[str, str],
) -> None:
    """`clear()` que nao alcanca o cache do modulo deixa os nomes vivos."""
    from vendinha.redaction import _known_values_pattern, redactor

    nome = pii_de_teste["nome"]
    KNOWN_VALUES.clear()
    try:
        KNOWN_VALUES.remember(nome)
        assert "[NOME]" in redactor().text(f"oi {nome}")

        KNOWN_VALUES.clear()

        # A afirmacao que importa e sobre RETENCAO, e ela vem ANTES de usar o redator
        # de novo: comportamento sozinho nao pega nada aqui, porque depois do
        # `clear()` o redator e consultado com o conjunto vazio e nao mascararia de
        # todo jeito — enquanto o nome segue vivo dentro do `lru_cache`, que e o que a
        # NC-O descreve. Um `clear()` que nao esquece nao e um `clear()`.
        assert _known_values_pattern.cache_info().currsize == 0, (
            "o padrao compilado ainda guarda os nomes depois do clear()"
        )
        assert redactor().text(f"oi {nome}") == f"oi {nome}"
    finally:
        KNOWN_VALUES.clear()


@pytest.mark.risco("R5")
def test_the_password_inside_a_connection_string_never_leaves() -> None:
    """O segredo que ninguem escolhe logar: toda excecao do psycopg carrega o DSN.

    `db.py` imprime o DSN quando o setup falha, e o `logger.exception` do endpoint
    recebe qualquer erro de conexao. A forma local (`@127.0.0.1`) sumia por acidente,
    porque casava com o padrao de e-mail; `@postgres` e `@db`, que sao as formas de
    conteiner da S-08, nao sumiam. Acidente que cobre o caso local e deixa passar o
    caso implantado e a pior combinacao possivel.
    """
    for host in ("postgres", "db", "127.0.0.1", "vendinha-db.interno"):
        dsn = f"postgresql://vendinha:s3nh4-secreta@{host}:5432/vendinha"
        redacted = redactor().text(f"connection to {dsn} failed")

        assert "s3nh4-secreta" not in redacted, f"a senha vazou com host {host!r}"
        assert "[CREDENCIAL]" in redacted
        # Usuario, host e porta continuam: sao o que faz a linha valer a leitura.
        assert host in redacted
        assert "vendinha:" in redacted

    # Senha com `/`, `?`, `#` e `=`. Uma chave base64 tem barra e igual, e senha
    # gerada por cofre tem os tres — o padrao da rodada 2 parava no primeiro deles e
    # deixava o resto da senha na linha.
    for senha in ("aGVsbG8vd29ybGQ=", "p/a?b#c", "S3nh4=com/barra"):
        redacted = redactor().text(
            f"connection to postgresql://vendinha:{senha}@postgres:5432/db failed"
        )
        assert senha not in redacted, f"a senha {senha!r} vazou"
        assert "[CREDENCIAL]" in redacted
        assert "postgres:5432" in redacted


@pytest.mark.risco("R5")
def test_a_plain_log_line_is_redacted_too(
    pii_de_teste: dict[str, str], logging_como_o_uvicorn_monta: io.StringIO
) -> None:
    """`docs/riscos.md` R5 says traces AND logs. A log file is an export too."""
    install_log_redaction()

    logging.getLogger("uvicorn.error").info("cliente informou %s", pii_de_teste["cpf"])

    escrito = logging_como_o_uvicorn_monta.getvalue()
    assert pii_de_teste["cpf"] not in escrito
    assert "[CPF]" in escrito


# O CLI imprime com `print()`, que nao passa por `logging` — entao a redacao de log
# nao o alcanca, e a spec afirmou por engano que a R-6 estava "mitigada pela NC-C".
# A terceira verificacao mediu e desmentiu. Subprocesso porque e o unico jeito de ver
# o que o processo realmente escreve no stderr.
CLI_COM_DSN_RUIM = """
import os, sys
os.environ["DATABASE_URL"] = sys.argv[1]
from vendinha.config import get_settings
get_settings.cache_clear()
from vendinha.db import main

sys.exit(main())
"""


@pytest.mark.risco("R5")
def test_the_setup_cli_never_prints_the_database_password() -> None:
    """`make db-setup` falha com frequencia — e falhar imprimindo a senha e o padrao.

    A mensagem existe para ajudar quem acabou de rodar o comando, e por isso ela
    mostra o DSN. Mostrar o DSN nao e o problema; mostrar a senha e.
    """
    senha = "s3nh4-do-banco-secreta"
    dsn = f"postgresql://vendinha:{senha}@127.0.0.1:1/vendinha"

    resultado = subprocess.run(  # noqa: S603 - argv fixo, escrito neste arquivo
        [sys.executable, "-c", CLI_COM_DSN_RUIM, dsn],
        capture_output=True,
        text=True,
        check=False,
    )

    saida = resultado.stdout + resultado.stderr
    assert resultado.returncode != 0, "o teste depende do caminho de falha do CLI"
    assert senha not in saida, "a senha do banco saiu no stderr"
    assert "[CREDENCIAL]" in saida
    # O resto do DSN continua: e o que faz a mensagem valer para quem esta depurando.
    assert "127.0.0.1" in saida
