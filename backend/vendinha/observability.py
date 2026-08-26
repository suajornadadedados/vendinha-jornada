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


def callback_handler() -> CallbackHandler | None:
    """The LangChain callback that turns a graph run into a trace, or `None`.

    Order matters and is the reason this is a function rather than a constant: the
    handler talks to the global Langfuse client, so the client — the one carrying
    our masking hook — has to exist first. A handler built before it would export
    through a default client with no redaction at all.
    """
    if client() is None:
        return None
    try:
        return CallbackHandler()
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
