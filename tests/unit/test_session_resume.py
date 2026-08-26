"""R9 — the conversation survives the process, and the state carries no payload.

Two halves of the same risk, and only one of them can be automated here:

* **This file** proves that a graph rebuilt from scratch, sharing nothing with the
  previous one but the checkpointer, reads back the turns the previous one wrote —
  and that two sessions never see each other.
* **The other half** is a real process restart against a real Postgres, and it is
  verified by hand in `/verificar-spec`. `docs/testes.md` §1 says so out loud
  because there is no integration tier in this repository.

The checkpointer here is `InMemorySaver`, not a mock. It is a second implementation
of the same LangGraph interface that `AsyncPostgresSaver` implements, which is what
makes the swap legitimate under `docs/testes.md` §4 — nothing internal is faked.
The model is `GenericFakeChatModel` for the same reason: `BaseChatModel` is the
port (ADR-012), so it is exactly where a test is allowed to stand in.
"""

from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.graph import ConversationState, build_graph, session_config


def _model(*answers: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=a) for a in answers]))


async def _say(graph: Any, session_id: str, text: str) -> dict[str, Any]:
    return await graph.ainvoke(
        {"session_id": session_id, "messages": [HumanMessage(content=text)]},
        config=session_config(session_id),
    )


@pytest.mark.risco("R9")
async def test_conversation_resumes_with_the_same_session_id() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(_model("bom dia", "claro", "anotado"), checkpointer)

    await _say(graph, "sessao-1", "oi, tudo bem?")
    await _say(graph, "sessao-1", "queria um presente")
    final = await _say(graph, "sessao-1", "para minha mae")

    ditos = [m.content for m in final["messages"]]
    assert "oi, tudo bem?" in ditos, "o primeiro turno sumiu do estado retomado"
    assert "queria um presente" in ditos
    assert len(final["messages"]) == 6, "tres turnos sao tres perguntas e tres respostas"


@pytest.mark.risco("R9")
async def test_a_new_graph_reads_what_the_previous_one_wrote() -> None:
    """The closest a unit test gets to a restart: nothing survives but the checkpointer."""
    checkpointer = InMemorySaver()

    antes = build_graph(_model("ola", "ainda aqui"), checkpointer)
    await _say(antes, "sessao-2", "meu nome ficou registrado?")
    del antes

    depois = build_graph(_model("ainda aqui"), checkpointer)
    retomada = await _say(depois, "sessao-2", "e agora?")

    ditos = [m.content for m in retomada["messages"]]
    assert "meu nome ficou registrado?" in ditos, "o grafo novo nao leu o checkpoint do anterior"


@pytest.mark.risco("R9")
async def test_two_sessions_do_not_share_state() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(_model("a", "b"), checkpointer)

    await _say(graph, "sessao-a", "segredo da sessao a")
    outra = await _say(graph, "sessao-b", "nada a ver")

    ditos = [m.content for m in outra["messages"]]
    assert "segredo da sessao a" not in ditos, "o thread_id nao esta isolando as sessoes"


@pytest.mark.risco("R9")
def test_graph_state_carries_identifiers_not_payloads() -> None:
    """RNF-6, pointer-not-payload — and this test is meant to be annoying.

    Adding a business object to the graph state (the order, the customer, the
    catalogue rows) is how a checkpointer turns into a second database that nobody
    migrates and nobody invalidates. When a future spec needs the order in state,
    the correct move is `pedido_id: str` and a read through a tool, which keeps this
    assertion green. If a spec genuinely needs to widen the state, widening this set
    is a deliberate act with a reviewer looking at it — not a side effect.
    """
    permitidos = {"session_id", "messages"}
    assert set(ConversationState.__annotations__) == permitidos
