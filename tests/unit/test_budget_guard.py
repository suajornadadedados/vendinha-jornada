"""R6 — the session has a ceiling, and hitting it degrades instead of falling over.

`docs/riscos.md` R6 is "custo/latência descontrolados", and `docs/testes.md` maps it
here: budget cap and per-call timeout respected, cost visible in the Langfuse
dashboard. The dashboard half is not automatable and is not pretended to be — this
file covers the two bounds the code enforces.

**The cap is counted in tokens, and read back off the conversation itself.** That
is the decision recorded as D-2 in the spec: a cap in USD needs a price table per
model, and with the provider configurable (ADR-012) that means several tables, all
rotting quietly. `usage_metadata` is normalised by LangChain across vendors, and it
is already inside the checkpointed messages — so the counter survives a restart
without a second store to keep in sync, and there is nothing to drift.

The second test group is about what the customer sees. `evals/adversarial/
adversarial-006` fails a run that exposes configuration values, internal limits or
tool names, and the message at the ceiling is exactly where a careless
implementation says "you exceeded your 60000 token budget".
"""

import asyncio
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.budget import (
    LIMIT_REACHED_MESSAGE,
    TimedOut,
    run_with_timeout,
    tokens_spent,
    within_budget,
)
from vendinha.graph import build_graph, session_config
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Subagent,
    registrar,
)


def _sem_catalogo() -> Subagent:
    """O subagent da recomendação sem nenhuma tool.

    Este arquivo não mede recomendação — mede o teto de custo e o timeout. Um subagent sem tool
    mantém o grafo no formato de uma volta só, que é o que estas asserções
    descrevem, e deixa o laço de tools para quem o testa.
    """
    return registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])


def _answer(text: str, total: int) -> AIMessage:
    return AIMessage(
        content=text,
        usage_metadata={
            "input_tokens": total // 2,
            "output_tokens": total - total // 2,
            "total_tokens": total,
        },
    )


@pytest.mark.risco("R6")
def test_spending_is_read_back_from_the_conversation() -> None:
    """No side counter: the messages already carry what they cost."""
    messages: list[Any] = [
        HumanMessage(content="oi"),
        _answer("bom dia", 120),
        HumanMessage(content="e ai"),
        _answer("pois nao", 80),
    ]
    assert tokens_spent(messages) == 200


@pytest.mark.risco("R6")
def test_an_answer_without_usage_metadata_counts_as_zero_not_as_a_crash() -> None:
    """Some providers omit usage on streamed chunks; a missing number is not a bug.

    Counting it as zero under-counts, which is the wrong direction for a cost cap —
    but raising here would take down a live conversation over a bookkeeping detail,
    and that trade is not close.
    """
    assert tokens_spent([AIMessage(content="sem metadata")]) == 0


@pytest.mark.risco("R6")
def test_the_cap_allows_up_to_the_limit_and_refuses_past_it() -> None:
    """Spelling out the boundary, because "cap" alone does not say which side it is on.

    Spending exactly the cap is spending your budget, not exceeding it — so it is
    allowed, and the next turn is the one that gets refused.
    """
    assert within_budget([_answer("resposta", 999)], cap=1000) is True
    assert within_budget([_answer("resposta", 1000)], cap=1000) is True
    assert within_budget([_answer("resposta", 1001)], cap=1000) is False


@pytest.mark.risco("R6")
def test_the_limit_message_never_leaks_configuration() -> None:
    """adversarial-006: no config values, no internal limit names, no tool names."""
    lowered = LIMIT_REACHED_MESSAGE.lower()
    for leak in ("token", "budget", "cap", "limite de", "60000", "config", "tool"):
        assert leak not in lowered, f"a resposta de limite vazou {leak!r}"
    assert len(LIMIT_REACHED_MESSAGE) > 20, "uma recusa seca e pior que um limite"


@pytest.mark.risco("R6")
async def test_a_session_over_budget_answers_honestly_without_calling_the_model() -> None:
    """The point of a cost cap is that the expensive call does not happen.

    A guard that refuses *after* invoking the model protects nothing — the money is
    already spent. This model raises if it is touched, so the assertion is about
    reachability rather than about the wording of the reply.
    """

    class ModelThatMustNotBeCalled(GenericFakeChatModel):
        async def ainvoke(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("o modelo foi chamado com a sessao ja no teto")

    checkpointer = InMemorySaver()
    graph = build_graph(
        ModelThatMustNotBeCalled(messages=iter([])),
        checkpointer,
        _sem_catalogo(),
        budget_tokens=100,
    )

    await graph.aupdate_state(session_config("cara"), {"messages": [_answer("caro", 500)]})

    final = await graph.ainvoke(
        {"session_id": "cara", "messages": [HumanMessage(content="mais uma coisa")]},
        config=session_config("cara"),
    )

    assert final["messages"][-1].content == LIMIT_REACHED_MESSAGE


@pytest.mark.risco("R6")
async def test_a_session_under_budget_is_answered_normally() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="claro")])),
        checkpointer,
        _sem_catalogo(),
        budget_tokens=100_000,
    )

    final = await graph.ainvoke(
        {"session_id": "barata", "messages": [HumanMessage(content="oi")]},
        config=session_config("barata"),
    )

    assert final["messages"][-1].content == "claro"


@pytest.mark.risco("R6")
async def test_a_slow_call_is_cut_off_and_a_fast_one_is_not() -> None:
    """The per-call ceiling. Tools adopt this helper when they arrive in S-03/S-04."""

    async def slow() -> str:
        await asyncio.sleep(5)
        return "tarde demais"

    async def fast() -> str:
        return "no tempo"

    assert await run_with_timeout(fast(), seconds=1, what="tool-rapida") == "no tempo"

    with pytest.raises(TimedOut) as error:
        await run_with_timeout(slow(), seconds=0.05, what="tool-lenta")

    assert "tool-lenta" in str(error.value), "quem investiga precisa saber o que estourou"
