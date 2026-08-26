"""Cost and latency ceilings — RNF-3, and the R6 line of the risk matrix.

Two bounds, and they fail in opposite directions on purpose.

**The session cap is counted in tokens, read back off the conversation.** D-2 in
the spec has the reasoning: a cap in money needs a price table per model, and since
ADR-012 made the provider configurable that means several tables, each rotting
quietly until a number is wrong in a direction nobody notices. `usage_metadata` is
normalised by LangChain across vendors, and it already rides inside the
checkpointed messages — so the counter survives a restart with no second store to
keep in sync and nothing to drift. Cost in currency stays where `docs/riscos.md`
R6 already put it: the Langfuse dashboard.

**The per-call timeout raises.** A hung provider is not a slow provider, and the
difference is that waiting does not help. `TimedOut` carries the name of what
stalled, because "timeout" with no subject is the least useful line in any log.

The message at the ceiling is product copy and it is deliberately vague about the
mechanism. `evals/adversarial/adversarial-006` fails a run that exposes
configuration values, internal limits or tool names — and "you have exceeded your
60000 token budget" is exactly the sentence a careless implementation writes.
"""

import asyncio
from collections.abc import Awaitable, Iterable, Sequence
from typing import TypeVar

from langchain_core.messages import AIMessage, BaseMessage

T = TypeVar("T")

# Honest about the outcome, silent about the machinery. It also has to leave the
# customer somewhere to go: a refusal with no next step reads as a fault.
LIMIT_REACHED_MESSAGE = (
    "Essa nossa conversa já ficou bem longa e eu preciso parar por aqui. "
    "Se quiser continuar, é só começar uma conversa nova que eu te atendo de novo."
)


class TimedOut(Exception):
    """A call did not finish inside its ceiling. Names what stalled."""


def tokens_spent(messages: Iterable[BaseMessage]) -> int:
    """Everything the model has produced in this conversation so far.

    A message without `usage_metadata` counts as zero. That under-counts, which is
    the wrong direction for a cost ceiling — but some providers omit usage on
    streamed chunks, and taking down a live conversation over a bookkeeping detail
    is the worse of the two failures by a wide margin.
    """
    total = 0
    for message in messages:
        if isinstance(message, AIMessage) and message.usage_metadata:
            total += message.usage_metadata.get("total_tokens", 0)
    return total


def within_budget(messages: Sequence[BaseMessage], cap: int) -> bool:
    """True while the session may still spend. Inclusive of the cap itself."""
    return tokens_spent(messages) <= cap


async def run_with_timeout(awaitable: Awaitable[T], seconds: float, what: str) -> T:
    """Bound one external call. Raises `TimedOut` naming `what` did not finish."""
    try:
        async with asyncio.timeout(seconds):
            return await awaitable
    except TimeoutError as expired:
        raise TimedOut(f"{what} passou de {seconds}s") from expired
