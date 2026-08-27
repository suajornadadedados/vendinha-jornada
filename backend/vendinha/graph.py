"""O grafo: conversa, chama tool, conversa de novo — e continua sem guardar payload.

Duas coisas mudaram na S-03, e as duas são sobre o que o grafo *continua* não
fazendo.

**Ganhou um laço de tools e nenhuma chave de estado.** `ConversationState` segue
com duas chaves, e `tests/unit/test_session_resume.py` trava esse conjunto de
propósito. As chamadas de tool e os retornos viajam dentro de `messages`, que é
para onde o LangGraph já os manda — guardar "o último produto consultado" no
estado seria começar a segunda cópia do catálogo que o `catalogo.py` existe para
evitar (RNF-6, R9).

**O prompt e as tools vêm de fora, do registro de `subagents.py`.** O grafo não
sabe quais tools existem nem escolhe entre elas: recebe um `Subagent` montado e
faz o bind. É o que mantém a fronteira do ADR-002 num lugar só — se ela morasse
aqui, cada mudança no grafo seria uma mudança na fronteira de permissão.

**O teto de tokens continua sendo checado antes de cada chamada**, e agora isso
inclui as chamadas *depois* de uma tool. É também o que limita o laço: cada volta
acrescenta tokens de resposta, então um modelo preso pedindo tool para sempre bate
no teto e para com uma frase que o cliente entende, em vez de girar (R6).

**O modelo é injetado, nunca construído aqui.** `BaseChatModel` é a porta
(ADR-012), que é o que permite ao módulo não conhecer Anthropic nem OpenAI, e aos
testes colocarem um duplo no mesmo lugar.
"""

from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from vendinha.budget import LIMIT_REACHED_MESSAGE, tools_still_affordable, within_budget
from vendinha.subagents import Subagent

# Only a fallback: the real value comes from `SESSION_BUDGET_TOKENS` through the
# settings, and the endpoint passes it in. It exists so a test — or a script — can
# build a graph without assembling configuration first.
DEFAULT_BUDGET_TOKENS = 60_000


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
    subagent: Subagent,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> CompiledStateGraph[ConversationState, Any, Any, Any]:
    """Compile the conversation graph against an injected model, checkpointer and subagent."""

    tools = subagent.tools
    # `bind_tools` only when there are tools: a subagent with an empty list is a
    # valid shape (it is what the budget and resume tests build), and binding an
    # empty list would demand `bind_tools` support from every fake model.
    falante = model.bind_tools(tools) if tools else model

    async def conversa(state: ConversationState) -> dict[str, list[AnyMessage]]:
        if not within_budget(state["messages"], budget_tokens):
            # No call, no cost, and an answer the customer can act on. The message
            # says nothing about tokens, caps or configuration — adversarial-006
            # fails a run that leaks any of it.
            return {"messages": [AIMessage(content=LIMIT_REACHED_MESSAGE)]}

        # Past the soft line the tools come off, which ends the loop: with nothing
        # to call, `tools_condition` routes to END and the model has to answer from
        # what the conversation already holds. It is a worse answer than the one it
        # was building, and it is infinitely better than the turn that fetched
        # everything and said nothing (see `budget.tools_still_affordable`).
        pode_chamar_tools = tools and tools_still_affordable(state["messages"], budget_tokens)
        quem_fala = falante if pode_chamar_tools else model

        # The system prompt is prepended for the call and never stored in state:
        # storing it would append a copy on every turn, and the checkpoint would
        # grow a prompt per message.
        answer = await quem_fala.ainvoke(
            [SystemMessage(content=subagent.prompt), *state["messages"]]
        )
        return {"messages": [answer]}

    builder: StateGraph[ConversationState, Any, Any, Any] = StateGraph(ConversationState)
    builder.add_node("conversa", conversa)
    builder.add_edge(START, "conversa")

    if not tools:
        builder.add_edge("conversa", END)
        return builder.compile(checkpointer=checkpointer)

    builder.add_node("ferramentas", ToolNode(tools))
    # `tools_condition` reads the last message: tool calls go to the tool node,
    # anything else ends the turn. The edge back into `conversa` is what closes
    # the loop — and what makes the budget check above run again on the way in.
    builder.add_conditional_edges("conversa", tools_condition, {"tools": "ferramentas", END: END})
    builder.add_edge("ferramentas", "conversa")
    return builder.compile(checkpointer=checkpointer)
