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

from langchain_core.messages import AIMessage, BaseMessage

# Honest about the outcome, silent about the machinery. It also has to leave the
# customer somewhere to go: a refusal with no next step reads as a fault.
LIMIT_REACHED_MESSAGE = (
    "Essa nossa conversa já ficou bem longa e eu preciso parar por aqui. "
    "Se quiser continuar, é só começar uma conversa nova que eu te atendo de novo."
)


class TimedOut(Exception):
    """A call did not finish inside its ceiling. Names what stalled."""


def tokens_spent(messages: Iterable[object]) -> int:
    """Everything the model has produced in this conversation so far.

    Takes `Iterable[object]` rather than `Iterable[BaseMessage]` because the body
    already narrows with `isinstance` — and because the eval runner holds the graph
    output as plain objects, the same way `groundedness.transcrever` does, to stay
    importable without LangChain.

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


# The slice of the ceiling held back so that there is always enough left to say
# something. A turn that spends everything fetching and nothing answering is the
# worst possible way to spend a budget — see `tools_still_affordable`.
ANSWER_RESERVE = 0.2


def tools_still_affordable(messages: Sequence[BaseMessage], cap: int) -> bool:
    """True while the session can still afford another round of tool calls.

    **The failure this exists to prevent.** The ceiling used to be checked in one
    place, on the way in to speak — so a turn could search, detail, price and
    validate, have the code approve a composition, and only then discover it had
    no budget left to tell anyone. Every token spent, nothing delivered, and a
    customer looking at a dead end produced by a mechanism that had just worked.

    So there are two lines instead of one, and they fail differently. Crossing
    this one takes the tools away and forces an answer out of what the
    conversation already holds: a worse answer, but an answer. Crossing the hard
    cap in `within_budget` is the backstop that still refuses outright, and it is
    what keeps `adversarial-006` — the loop built to burn money — from having
    found a way around the ceiling by never quite reaching it.

    Degrading first also puts the cost where it belongs. One tool round costs a
    full re-send of the history; one final answer costs the same re-send once. If
    only one of the two fits, it should be the one the customer sees.
    """
    return tokens_spent(messages) <= int(cap * (1 - ANSWER_RESERVE))


async def run_with_timeout[T](awaitable: Awaitable[T], seconds: float, what: str) -> T:
    """Bound one external call. Raises `TimedOut` naming `what` did not finish."""
    try:
        async with asyncio.timeout(seconds):
            return await awaitable
    except TimeoutError as expired:
        raise TimedOut(f"{what} passou de {seconds}s") from expired
