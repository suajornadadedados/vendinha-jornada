"""Langfuse instrumentation — and the two rules that govern it.

**One: the customer never pays for observability being down.** ADR-010 accepted a
third party in the observability path and named the price in the same breath —
*"indisponibilidade do Langfuse não pode derrubar o atendimento: a instrumentação
falha em silêncio, nunca propaga exceção"*. So every function here that touches the
network or the SDK returns `None` on failure and logs it, and the chat endpoint
runs with no callback rather than not running.

**Two: the masking hook fails closed, and that asymmetry is deliberate.** The
Langfuse contract says that if `mask_otel_spans` raises, the *whole export batch is
dropped*. So the one function here that does NOT catch its exceptions is the
redaction hook: a broken redactor costs a trace, never a leak. Rule one is about
the customer's session; rule two is about a batch of spans nobody is waiting for.
Wrapping the hook in a `try` to be "safe" would invert exactly the trade ADR-010
made, because returning `None` from it means *export this batch unchanged*.
"""

import logging
import re
from functools import lru_cache
from typing import Any

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanPatch,
)

from vendinha.config import get_settings
from vendinha.redaction import redactor

logger = logging.getLogger(__name__)


def mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Redact every string attribute in one export batch, just before it ships.

    This is the boundary the R5 security test aims at. It runs after Langfuse has
    decided what to export, so it sees spans from instrumentations we do not own —
    the LangChain callback handler among them — which is precisely why redacting
    only our own inputs would not be a guarantee.

    No `try` here, on purpose: see the module docstring.
    """
    active = redactor()
    patches: dict[Any, OtelSpanPatch] = {}

    for identifier, span in params.spans.items():
        changed = active.attributes(span.attributes)
        if changed:
            patches[identifier] = OtelSpanPatch(set_attributes=changed)

    if not patches:
        # `None` means "batch unchanged", which is correct only because nothing in
        # it needed changing. Never return this from an error path.
        return None
    return MaskOtelSpansResult(span_patches=patches)


@lru_cache(maxsize=1)
def client() -> Langfuse | None:
    """The configured Langfuse client, or `None` when there is nothing to send to.

    Cached because the client owns a background exporter thread: building a second
    one per request would be a thread leak with a queue attached.
    """
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.info("Langfuse sem credencial; seguindo sem trace (ADR-010)")
        return None

    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
            mask_otel_spans=mask_otel_spans,
        )
    except Exception:
        logger.warning("Langfuse indisponivel; seguindo sem trace", exc_info=True)
        return None


def trace_id_da_sessao(session_id: str) -> str:
    """O id de trace desta sessão — o MESMO em todo turno dela.

    `create_trace_id` deriva um id de 32 hex determinístico a partir da semente, que
    é como o Langfuse manda correlacionar um id externo com um trace dele. O id da
    sessão já é o `thread_id` do checkpointer e o que o cliente guarda no
    `localStorage`, então a conversa inteira tem uma chave só, de ponta a ponta.
    """
    return Langfuse.create_trace_id(seed=session_id)


# A regra do Langfuse para nome de ambiente, copiada da documentação dele:
# minúsculas, dígitos, hífen e sublinhado, no máximo 40, e nunca começando com
# "langfuse" — esse prefixo é reservado.
_AMBIENTE_ACEITO = re.compile(r"^(?!langfuse)[a-z0-9_-]{1,40}$")


def ambiente_do_trace(app_env: str) -> str | None:
    """O `APP_ENV` na forma que o Langfuse aceita, ou `None` quando não há forma.

    **Por que declarar ambiente.** Sem ele todo trace cai em `default`, que é onde
    o Langfuse põe quem não disse nada — e onde caíam, juntos e indistinguíveis, o
    atendimento de verdade e as centenas de traces que a suíte de testes exportava.
    Os evals já se separam assim desde o ADR-014 (`visor.AMBIENTE`); esta função é
    a metade que faltava, do lado do atendimento.

    **Derivado de `APP_ENV` e não de uma constante.** Essa variável já é a que
    decide comportamento sensível a ambiente — é ela que gateia o `PUT /config` —,
    então derivar daqui garante que o rótulo do trace não possa divergir da
    identidade do deploy. Quando a S-08 subir DEV e PROD na mesma conta, os dois se
    separam sozinhos, sem uma segunda variável para alguém esquecer de trocar.

    **`None` quando o valor não serve, e em voz alta.** O SDK recusa um ambiente
    fora do padrão, e recusa em silêncio: o trace iria para `default` sem nada
    avisando, que é exatamente a confusão que esta função existe para desfazer.
    Melhor um aviso no log dizendo qual valor foi recusado.
    """
    normalizado = app_env.strip().lower()
    if _AMBIENTE_ACEITO.match(normalizado):
        return normalizado
    logger.warning(
        "APP_ENV=%r nao serve como ambiente de trace (o Langfuse aceita %s); os traces "
        "desta instancia vao para `default` e nao se separam dos de outra",
        app_env,
        _AMBIENTE_ACEITO.pattern,
    )
    return None


def callback_handler(session_id: str | None = None) -> CallbackHandler | None:
    """The LangChain callback that turns a graph run into a trace, or `None`.

    Order matters and is the reason this is a function rather than a constant: the
    handler talks to the global Langfuse client, so the client — the one carrying
    our masking hook — has to exist first. A handler built before it would export
    through a default client with no redaction at all.

    **Com `session_id`, a conversa inteira vira UM trace.** Cada `POST /chat` é uma
    requisição própria, e sem isto o handler abre um run raiz novo a cada turno —
    logo, um trace por turno. Quem quisesse ler o atendimento tinha que abrir doze
    traces e remontar a ordem na cabeça. Fixar o `trace_id` derivado da sessão faz
    as observações de todos os turnos caírem no mesmo trace, que é o mesmo efeito que
    o runner de evals já obtém de outro jeito: lá existe um `start_as_current_observation`
    por caso, envolvendo todas as falas, e aqui não existe requisição que envolva o
    atendimento inteiro.

    O preço, dito em voz alta: a latência do trace passa a ser o relógio de parede da
    conversa — minutos ou horas —, e não o tempo de um turno. A latência que importa
    para o RNF-4 é a do primeiro token, e ela é medida no `observador` e vive no
    painel, não aqui.
    """
    if client() is None:
        return None
    try:
        if session_id is None:
            return CallbackHandler()
        return CallbackHandler(trace_context={"trace_id": trace_id_da_sessao(session_id)})
    except Exception:
        logger.warning("nao consegui instrumentar a conversa; seguindo sem trace", exc_info=True)
        return None


class RedactingFormatter(logging.Formatter):
    """Wraps another formatter and redacts everything it produces.

    A *formatter* and not a filter, and that is the whole fix. A filter sees
    `record.msg` and `record.args`; it never sees the traceback, because the
    traceback is rendered later, by the formatter. And the traceback is the leak
    that matters: `logger.exception(...)` in the chat handler receives whatever the
    provider SDK or psycopg raised, and those exceptions carry API keys and DSNs
    that nobody chose to log.

    Wrapping instead of replacing keeps uvicorn's own format — colours, timestamps,
    the access log shape — so turning redaction on does not change how the logs read.
    """

    def __init__(self, inner: logging.Formatter) -> None:
        super().__init__()
        self._inner = inner

    def format(self, record: logging.LogRecord) -> str:
        return redactor().text(self._inner.format(record))


# Paths this application deliberately does not serve, probed by tooling that
# assumes a convention. `/metrics` is the Prometheus exporter path: monitoring
# agents, IDE plugins and container tooling sweep it on every local port, and each
# sweep prints a 404 nobody can act on.
#
# Adding the route to quiet the log would be the wrong fix — it would mean claiming
# to export Prometheus metrics we do not have. The observability of this project is
# Langfuse plus `/admin/metricas` (ADR-007, ADR-010).
_UNSERVED_PROBES = frozenset({"/metrics"})


class _DropUnservedProbes(logging.Filter):
    """Drops the access-log line for a 404 on a path we never claimed to serve.

    Narrow on purpose: only these paths, and only on 404. Dropping *every* 404 would
    also hide the ones that mean something — a frontend calling a route that moved, a
    webhook pointed at the wrong path — and those are the 404s worth seeing.

    uvicorn logs access with five positional args and no `extra`:
    `(client_addr, method, path_with_query, http_version, status)`. Reading
    `record.args` is therefore the only source; the shape is checked before use so a
    uvicorn upgrade that changes it degrades to "log everything", never to a crash
    inside the logging call.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) != 5:
            return True
        path, status = args[2], args[4]
        if not isinstance(path, str) or not isinstance(status, int):
            return True
        return not (status == 404 and path.split("?", 1)[0] in _UNSERVED_PROBES)


def unserved_probes_are_silenced() -> bool:
    """Whether the access logger is currently dropping those 404s.

    Exists so a test can ask about the *application*, not about the function — the
    same two-level question `redaction_is_installed` answers, and for the same reason:
    proving the installer works never proves the app calls it.
    """
    return any(
        isinstance(existing, _DropUnservedProbes)
        for existing in logging.getLogger("uvicorn.access").filters
    )


def silence_unserved_probes() -> bool:
    """Stop the access log from reporting 404s for paths nothing here serves.

    Idempotent, and the return says which happened: `True` installed a filter, `False`
    found one already there. `Logger.addFilter` de-duplicates by identity only, so
    calling this twice would otherwise stack a second instance — harmless in
    production, where `create_app` runs once, but the suite builds an app per test and
    would pile them onto the process-wide `uvicorn.access` logger.
    """
    if unserved_probes_are_silenced():
        return False
    logging.getLogger("uvicorn.access").addFilter(_DropUnservedProbes())
    return True


def _every_handler() -> list[logging.Handler]:
    """Every handler currently configured, on the root and on every named logger."""
    handlers = list(logging.getLogger().handlers)
    for logger_or_placeholder in logging.Logger.manager.loggerDict.values():
        if isinstance(logger_or_placeholder, logging.Logger):
            handlers.extend(logger_or_placeholder.handlers)
    return handlers


def export_masking_is_installed(langfuse_client: Langfuse) -> bool:
    """Se ESTE cliente exporta através do nosso gancho de redação.

    Existe por causa do achado Alta da terceira verificação: apagar
    `mask_otel_spans=mask_otel_spans` do construtor deixava a suíte inteira verde, e
    a aplicação mandava CPF, e-mail e telefone em claro para o Langfuse Cloud —
    verificado lendo o trace de volta pela API pública.

    É a mesma pergunta das duas rodadas anteriores, uma casa adiante: rodada 1, nada
    provava que o filtro de log era instalado; rodada 2, nada provava que a aplicação
    instalava; rodada 3, nada provava que o cliente foi construído com o gancho.
    Testar a função que redige nunca prova que alguém a ligou no caminho de saída.

    Lê um atributo privado do SDK de propósito. É acoplamento a terceiro e vai
    quebrar numa atualização — que é exatamente o que se quer: uma atualização que
    mova esse campo tem que reprovar a suíte, não passar em silêncio levando junto o
    invariante de release do REQ-4.
    """
    recursos = getattr(langfuse_client, "_resources", None)
    return getattr(recursos, "mask_otel_spans", None) is mask_otel_spans


def redaction_is_installed() -> bool:
    """Whether any configured handler is currently redacting.

    Exists so a test can ask about the *application*, not about the function. The
    round-1 hole was a filter that never got installed; the round-2 hole was a test
    that proved the installer works while nothing proved the app ever calls it.
    Both are the same question — is it reachable? — asked one level apart.
    """
    return any(isinstance(handler.formatter, RedactingFormatter) for handler in _every_handler())


def install_log_redaction() -> int:
    """Make every configured handler redact. Returns how many were wrapped.

    **Side effect worth declaring (R-13):** when the root has no handlers, this adds
    a `StreamHandler` to it. That changes where *any* third-party log in the process
    lands — from `logging.lastResort` to this handler. It is the decision that makes
    the redaction reach our own logger at all, and it is not free of surprise.

    Returning the count is not decoration: it is what lets a test fail when this
    function becomes a no-op. The previous version walked `logging.getLogger().handlers`
    only, and under uvicorn the root logger has **no handlers at all** — uvicorn
    configures `uvicorn.*` and leaves the root empty. So nothing was installed,
    records fell through to `logging.lastResort`, and the whole thing was inert while
    looking configured.
    """
    # `LOG_LEVEL` é aplicado aqui, e aqui é o lugar certo: esta função já é o
    # único ponto do processo que mexe no logger raiz, e um segundo lugar
    # disputando o nível é como se acaba com uma variável que só funciona
    # dependendo da ordem de import. Ressalva R-5 da verificação da S-02 — a
    # variável estava documentada no `.env.example` e nenhum código a lia.
    nivel = logging.getLevelNamesMapping().get(get_settings().log_level.upper())
    if nivel is not None:
        logging.getLogger().setLevel(nivel)

    handlers = _every_handler()

    if not logging.getLogger().handlers:
        # Nothing on the root means records reach `logging.lastResort`, which has no
        # formatter to wrap. Give the root something that can be redacted, so a
        # library logging through an unconfigured logger is covered too.
        fallback = logging.StreamHandler()
        logging.getLogger().addHandler(fallback)
        handlers.append(fallback)

    wrapped = 0
    for handler in handlers:
        if isinstance(handler.formatter, RedactingFormatter):
            continue
        handler.setFormatter(RedactingFormatter(handler.formatter or logging.Formatter()))
        wrapped += 1
    return wrapped
