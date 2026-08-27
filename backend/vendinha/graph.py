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

Na S-04 o módulo ganhou uma segunda forma, e nenhuma chave de estado. `build_graph`
continua sendo uma lane só entrando direto do START; `build_supervised_graph` põe
duas lanes lado a lado e decide na porta qual atende o turno. O que as duas versões
compartilham é `_adicionar_lane`, e o que a segunda **não** compartilha é o nó de
tools: cada lane tem o seu. É a fronteira do ADR-002 dentro do grafo — enquanto o
turno corre na recomendação, as tools de escrita não estão ligadas no modelo que
fala. Um `ToolNode` só, com a união das tools, seria um vazamento que os dois
registros continuariam descrevendo como correto.
"""

from collections.abc import Hashable
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
from vendinha.supervisor import Supervisor

# Only a fallback: the real value comes from `SESSION_BUDGET_TOKENS` through the
# settings, and the endpoint passes it in. It exists so a test — or a script — can
# build a graph without assembling configuration first.
#
# It has to be kept in step with `config.Settings.session_budget_tokens`, and S-04
# found out why the hard way: the eval runner was building its graph without passing
# the setting, so the ruler measured an agent with a 150_000 ceiling while production
# ran on another number. The guard then unbound the tools mid-conversation and the
# case failed looking exactly like a model that gave up. The runner passes it now —
# a ruler that runs a different system than production measures the wrong system.
DEFAULT_BUDGET_TOKENS = 250_000


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


# The prefix of every node that speaks to the customer. `app.py` filters the token
# stream by it: `stream_mode="messages"` emits from every chat model called inside
# the graph, and the supervisor's router is one of them (S-04). Without the filter
# the router's JSON would arrive in the middle of a sentence — the same leak the
# `ToolMessage` filter already prevents on the other side (`adversarial-006`).
CONVERSA = "conversa"


def fala_com_o_cliente(no: str | None) -> bool:
    """Whether a node's output belongs in the customer's stream."""
    return bool(no) and str(no).startswith(CONVERSA)


def _adicionar_lane(
    builder: "StateGraph[ConversationState, Any, Any, Any]",
    model: BaseChatModel,
    subagent: Subagent,
    budget_tokens: int,
    sufixo: str = "",
) -> str:
    """Add one subagent's lane — speak, call tools, speak again — and return its entry node.

    A lane is `conversa[-nome]` plus its own `ferramentas[-nome]`, wired in a loop.
    Extracted in S-04 so the supervisor can hold two of them side by side without
    the two sharing a tool node: sharing one would bind both subagents' tools into
    the same `ToolNode`, and the permission boundary of ADR-002 would have leaked
    through the graph while both registries still looked correct.
    """
    conversa_no = f"{CONVERSA}{sufixo}"
    ferramentas_no = f"ferramentas{sufixo}"

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

    builder.add_node(conversa_no, conversa)

    if not tools:
        builder.add_edge(conversa_no, END)
        return conversa_no

    builder.add_node(ferramentas_no, ToolNode(tools))
    # `tools_condition` reads the last message: tool calls go to the tool node,
    # anything else ends the turn. The edge back into `conversa` is what closes
    # the loop — and what makes the budget check above run again on the way in.
    builder.add_conditional_edges(conversa_no, tools_condition, {"tools": ferramentas_no, END: END})
    builder.add_edge(ferramentas_no, conversa_no)
    return conversa_no


def build_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
    subagent: Subagent,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> CompiledStateGraph[ConversationState, Any, Any, Any]:
    """Compile the conversation graph against an injected model, checkpointer and subagent.

    One lane, entered straight from START. This is the shape S-02 and S-03 built and
    the one the eval runner still uses when a case exercises a single subagent.
    """
    builder: StateGraph[ConversationState, Any, Any, Any] = StateGraph(ConversationState)
    entrada = _adicionar_lane(builder, model, subagent, budget_tokens)
    builder.add_edge(START, entrada)
    return builder.compile(checkpointer=checkpointer)


def build_supervised_graph(
    model: BaseChatModel,
    checkpointer: BaseCheckpointSaver[Any],
    supervisor: Supervisor,
    budget_tokens: int = DEFAULT_BUDGET_TOKENS,
) -> CompiledStateGraph[ConversationState, Any, Any, Any]:
    """Two lanes, and a routing decision at the door — the S-04 shape (REQ-1).

    **The routing is a conditional edge from START, not a node.** A node would have
    to write its decision somewhere for the edge to read, and the only place is the
    state — which is how `ConversationState` would grow an `etapa` key holding a
    fact that `messages` already carries (RNF-6, R9). As an edge it decides and
    routes in one step, and the state stays the two keys
    `tests/unit/test_session_resume.py` pins.

    **Each lane owns its tool node.** That is the structural half of ADR-002 inside
    the graph: while the turn runs in the recommendation lane, the checkout tools
    are not bound to the model that is speaking — they are not denied, they are not
    there. See `tests/security/test_injection.py`.
    """
    builder: StateGraph[ConversationState, Any, Any, Any] = StateGraph(ConversationState)
    # `Hashable` e não `str` porque é o que `add_conditional_edges` declara, e um
    # dicionário é invariante na chave: `dict[str, str]` não é um `dict[Hashable, str]`.
    portas: dict[Hashable, str] = {
        subagent.nome: _adicionar_lane(
            builder, model, subagent, budget_tokens, sufixo=f"-{subagent.nome}"
        )
        for subagent in (supervisor.recomendacao, supervisor.checkout)
    }

    async def escolher_lane(state: ConversationState) -> str:
        return (await supervisor.rota(state["messages"], budget_tokens)).nome

    # `portas` é o mapa do que `escolher_lane` devolve para o nó de entrada da
    # lane. Declará-lo, em vez de devolver o nome do nó direto, é o que faz o
    # LangGraph conhecer os destinos possíveis — e o que faz um nome de subagent
    # sem lane virar erro de compilação em vez de aresta pendurada.
    builder.add_conditional_edges(START, escolher_lane, portas)
    return builder.compile(checkpointer=checkpointer)
