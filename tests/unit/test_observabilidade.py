"""O trace da conversa: um por atendimento, e não um por turno.

Sem marcador de risco, e de propósito. É teste de feature — `docs/testes.md` §3
item 1 —, e o `risco` fica reservado para o que fecha uma linha da matriz. A linha
R5 do Langfuse (PII mascarada na origem) é medida em
`tests/security/test_pii_redaction.py`, que é outra pergunta sobre o mesmo SDK.

Nada aqui abre rede: `create_trace_id` é uma função pura de hash, e o caminho sem
credencial é exercitado trocando `client` por um duplo.
"""

import logging
from typing import Any

import pytest

from vendinha import observability
from vendinha.observability import callback_handler, trace_id_da_sessao


def test_a_mesma_sessao_da_sempre_o_mesmo_trace() -> None:
    """O tripwire desta feature.

    Cada `POST /chat` é uma requisição própria, então o handler do LangChain abre um
    run raiz por turno — e um run raiz por turno é um TRACE por turno. Ler um
    atendimento de doze turnos virava abrir doze traces e remontar a ordem de
    cabeça.

    O que junta tudo é o id derivado da sessão ser o MESMO em toda chamada. Se
    alguém trocar isto por um id aleatório, o Langfuse volta a mostrar N traces sem
    erro nenhum, sem log nenhum, e a regressão só aparece quando alguém for
    depurar uma conversa. É essa a falha que esta asserção segura.
    """
    assert trace_id_da_sessao("abc123") == trace_id_da_sessao("abc123")


def test_sessoes_diferentes_nao_se_misturam() -> None:
    """Um trace por atendimento é o objetivo; um trace para dois, não."""
    assert trace_id_da_sessao("abc123") != trace_id_da_sessao("def456")


def test_o_id_tem_a_forma_que_o_langfuse_exige() -> None:
    """32 hex minúsculos — 16 bytes de trace id do OpenTelemetry.

    Vem de `Langfuse.create_trace_id`, e é justamente por vir de lá que o formato
    não é problema nosso. A asserção existe para o dia em que alguém "simplificar"
    isto para o próprio `session_id`, que é hex de 32 por coincidência do `uuid4().hex`
    e deixaria de ser no dia em que o id da sessão mudasse de forma.
    """
    gerado = trace_id_da_sessao("abc123")

    assert len(gerado) == 32
    assert gerado == gerado.lower()
    assert all(caractere in "0123456789abcdef" for caractere in gerado)


@pytest.mark.parametrize("sessao", [None, "abc123"])
def test_sem_langfuse_configurado_nao_ha_handler(
    monkeypatch: pytest.MonkeyPatch, sessao: str | None
) -> None:
    """ADR-010 aplicado às duas formas de pedir o handler.

    Sem credencial, o atendimento roda sem trace em vez de não rodar — e isso vale
    tanto para o handler da subida quanto para o por sessão. Um `CallbackHandler`
    construído aqui falaria com o cliente default do SDK, sem `mask_otel_spans`, e
    exportaria a conversa inteira sem redação nenhuma.
    """

    def sem_cliente(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(observability, "client", sem_cliente)

    assert callback_handler(session_id=sessao) is None


def test_a_suite_nao_exporta_trace_nenhum() -> None:
    """O tripwire da fixture `_o_langfuse_fica_fora_da_suite`.

    Este repositório já aprendeu três vezes que testar a função nunca prova que
    alguém a chamou — é por isso que existem `redaction_is_installed` e
    `export_masking_is_installed`. Esta é a mesma pergunta uma casa adiante: a
    fixture do `conftest` está de fato valendo enquanto a suíte roda?

    Sem esta asserção, apagar a fixture num refactor deixa tudo verde e faz a suíte
    voltar a mandar centenas de traces de modelo dublê para o projeto de produção —
    sem erro, sem log, e só perceptível para quem for abrir o Langfuse à procura de
    um atendimento e encontrar 97 conversas de 4 ms na frente dele.
    """
    assert observability.client() is None, (
        "a suite construiu um cliente Langfuse de verdade: ela esta exportando trace "
        "para o projeto de producao com a credencial do .env"
    )


@pytest.mark.parametrize(
    ("app_env", "esperado"),
    [
        ("local", "local"),
        ("prod", "prod"),
        ("dev-vps", "dev-vps"),
        ("com_sublinhado", "com_sublinhado"),
        # Normalizado em vez de recusado: `APP_ENV=PROD` é a mesma intenção escrita
        # com a mão pesada, e recusá-la mandaria o trace para `default` por causa de
        # duas teclas.
        ("PROD", "prod"),
        ("  Local  ", "local"),
        # Fora do padrão do Langfuse: vira `None`, e o log diz por quê.
        ("prod!", None),
        ("com espaco", None),
        ("acentuação", None),
        ("", None),
        ("x" * 41, None),
        # O prefixo é reservado pelo Langfuse.
        ("langfuse", None),
        ("langfuse-prod", None),
    ],
)
def test_o_ambiente_do_trace_respeita_a_regra_do_langfuse(
    app_env: str, esperado: str | None
) -> None:
    """O SDK recusa um ambiente fora do padrão **em silêncio**.

    Um `APP_ENV` inválido não quebra nada e não avisa nada: o trace simplesmente
    volta para `default`, que é o balde indistinguível que declarar ambiente existe
    para evitar. Esta tabela é o que impede a regressão de ser invisível.
    """
    assert observability.ambiente_do_trace(app_env) == esperado


def _linha_de_acesso(caminho: str, status: int) -> logging.LogRecord:
    """Um registro com a forma exata que o uvicorn produz no log de acesso.

    Cinco args posicionais e nenhum `extra` — conferido em
    `uvicorn/protocols/http/h11_impl.py`. Montar o registro à mão em vez de subir o
    servidor é o que mantém isto na camada `unit` (ADR-011).
    """
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:54895", "GET", caminho, "1.1", status),
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("caminho", "status", "aparece"),
    [
        # O ruído que motivou o filtro: agente de monitoramento varrendo a porta.
        ("/metrics", 404, False),
        ("/metrics?format=prometheus", 404, False),
        # 404 que significa alguma coisa continua aparecendo. É a razão de o filtro
        # ser por caminho e não por status: silenciar todo 404 esconderia uma rota
        # que mudou de lugar ou um webhook apontado errado.
        ("/admin/metricas", 404, True),
        ("/metricas", 404, True),
        ("/chat", 404, True),
        # E o dia em que /metrics existir de verdade, ele volta a ser logado.
        ("/metrics", 200, True),
    ],
)
def test_so_o_404_de_rota_que_nao_servimos_some_do_log(
    caminho: str, status: int, aparece: bool
) -> None:
    filtro = observability._DropUnservedProbes()
    assert filtro.filter(_linha_de_acesso(caminho, status)) is aparece


def test_forma_inesperada_de_registro_e_logada_em_vez_de_quebrar() -> None:
    """Uma atualização do uvicorn que mude os args degrada para "loga tudo".

    O contrário — deixar a exceção subir — seria um erro dentro da chamada de log,
    no caminho de toda requisição.
    """
    registro = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg="algo de outro formato",
        args=None,
        exc_info=None,
    )

    assert observability._DropUnservedProbes().filter(registro) is True


def test_o_filtro_e_instalado_no_logger_de_acesso() -> None:
    """Metade de baixo da fiação: a função liga o filtro no logger certo.

    A de cima — a aplicação chama a função — é
    `test_the_application_silences_the_unserved_probes_when_it_starts`, em
    `test_boot.py`. Este arquivo citava a lição de `redaction_is_installed` (rodada 2
    da verificação da S-02) e cobria só esta metade, o que deixava apagar a chamada do
    `lifespan` sem nenhum teste vermelho.
    """
    acesso = logging.getLogger("uvicorn.access")
    antes = list(acesso.filters)
    acesso.filters = []
    try:
        assert observability.silence_unserved_probes() is True
        assert observability.unserved_probes_are_silenced()
    finally:
        acesso.filters = antes


def test_ligar_o_filtro_duas_vezes_nao_empilha_dois() -> None:
    """A suíte monta uma aplicação por teste, e o `uvicorn.access` é do processo.

    Sem idempotência cada `TestClient(create_app(...))` deixava mais uma instância
    pendurada no logger global. Nenhuma consequência observável — todas devolvem o
    mesmo veredito —, mas o `install_log_redaction` vizinho foi escrito com o cuidado
    oposto, e o valor de retorno existe para que isto possa ser afirmado.
    """
    acesso = logging.getLogger("uvicorn.access")
    antes = list(acesso.filters)
    acesso.filters = []
    try:
        assert observability.silence_unserved_probes() is True
        for _ in range(4):
            assert observability.silence_unserved_probes() is False

        instalados = [f for f in acesso.filters if isinstance(f, observability._DropUnservedProbes)]
        assert len(instalados) == 1
    finally:
        acesso.filters = antes
