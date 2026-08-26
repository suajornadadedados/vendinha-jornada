"""The smallest graph that can hold a conversation — and remember it.

One node, one edge in, one edge out. Everything interesting about this file is in
what it refuses to hold rather than in what it does.

**Pointer, not payload (RNF-6).** `ConversationState` has two keys and is meant to
stay that way. A checkpointer that carries business objects becomes a second copy
of the database: nobody migrates it, nobody invalidates it, and it disagrees with
Postgres the first time a price changes. When a later spec needs the order in the
conversation, the shape is `pedido_id: str` plus a read through a tool.

**The model is injected, never constructed here.** `BaseChatModel` is the port
(ADR-012), which is what lets this module know nothing about Anthropic, OpenAI or
whatever comes third — and what lets the tests stand a fake in the same place.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

# Deliberately short, and deliberately fenced. This agent has no catalogue, no
# price and no tool until S-03/S-04 — so the one thing it must not do is sound
# like it has them. A friendly model with nothing to read invents a cheese.
SYSTEM_PROMPT = """Você é o atendente da Vendinha, um empório mineiro digital.

Fale como gente: cordial, direto, sem formalidade de robô e sem emoji.

Você ainda NÃO tem acesso ao catálogo, a preços, a estoque ou a prazos. Enquanto
for assim, você não afirma nada sobre produto — nem nome, nem preço, nem
disponibilidade, nem prazo de entrega. Se perguntarem, diga com naturalidade que
ainda não consegue consultar o catálogo, e ofereça continuar a conversa no que
estiver ao seu alcance. Inventar um produto para não decepcionar é o pior
resultado possível.

Nunca repita em texto o CPF, o e-mail ou o endereço que o cliente informar."""


class ConversationState(TypedDict):
    """What survives a restart. Two keys, and widening this is a deliberate act.

    `tests/unit/test_session_resume.py` asserts this exact set, so adding a field
    fails the suite on purpose — the point is that someone has to look at it.
    """

    session_id: str
    messages: Annotated[list[AnyMessage], add_messages]


def session_config(session_id: str) -> RunnableConfig:
    """The session id IS the checkpoint thread id.

    One concept, one identifier. Two ids that must be kept in sync is a bug waiting
    for the day they are not.
    """
    return {"configurable": {"thread_id": session_id}}


def build_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[ConversationState, Any, Any, Any]:
    """Compile the conversation graph against an injected model and checkpointer."""

    async def conversa(state: ConversationState) -> dict[str, list[AnyMessage]]:
        # The system prompt is prepended for the call and never stored in state:
        # storing it would append a copy on every turn, and the checkpoint would
        # grow a prompt per message.
        resposta = await model.ainvoke([SystemMessage(content=SYSTEM_PROMPT), *state["messages"]])
        return {"messages": [resposta]}

    builder: StateGraph[ConversationState, Any, Any, Any] = StateGraph(ConversationState)
    builder.add_node("conversa", conversa)
    builder.add_edge(START, "conversa")
    builder.add_edge("conversa", END)
    return builder.compile(checkpointer=checkpointer)
