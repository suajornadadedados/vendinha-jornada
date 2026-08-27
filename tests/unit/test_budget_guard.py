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
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.budget import (
    LIMIT_REACHED_MESSAGE,
    TimedOut,
    run_with_timeout,
    tokens_spent,
    tools_still_affordable,
    within_budget,
)
from vendinha.graph import build_graph, session_config
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Ferramenta,
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


# ------------------------------------------- a linha macia: degradar antes de cortar


def _tool_de_leitura() -> BaseTool:
    """Uma tool de leitura qualquer, só para o grafo ter laço."""

    async def consultar_preco(produto_ids: list[str]) -> str:
        del produto_ids
        return '{"encontrados": [{"id": "x", "preco": "10.00"}]}'

    return StructuredTool.from_function(
        coroutine=consultar_preco, name="consultar_preco", description="Preço."
    )


class ModeloComEsemTools(GenericFakeChatModel):
    """Um duplo que pede tool quando tem tool, e responde quando não tem.

    A distinção é o teste inteiro. Com as tools no bind ele nunca termina o turno
    sozinho — é o modelo preso no laço, que era exatamente o caminho até o teto
    duro. Sem elas, ele fala. Um duplo que respondesse igual nos dois casos passaria
    com o código antigo e não provaria nada.
    """

    com_tools: bool = False

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        del tool_choice, kwargs
        gemeo = ModeloComEsemTools(messages=iter([]))
        object.__setattr__(gemeo, "com_tools", bool(list(tools)))
        return gemeo

    async def ainvoke(self, *_: Any, **__: Any) -> Any:
        if self.com_tools:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "consultar_preco", "args": {"produto_ids": ["x"]}, "id": "t1"}
                ],
                usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
            )
        return AIMessage(content="fecha assim, olha só")


@pytest.mark.risco("R6")
def test_the_soft_line_comes_before_the_hard_one() -> None:
    """R6 — há duas linhas, e a macia é atingida primeiro.

    Se a reserva fosse zero as duas coincidiriam, e o turno voltaria a gastar tudo
    buscando e nada respondendo. Se fosse um, nenhuma tool jamais seria chamada.
    """
    cap = 1_000
    quase_no_teto = [_answer("caro", 850)]

    assert within_budget(quase_no_teto, cap), "ainda dentro do teto duro"
    assert not tools_still_affordable(quase_no_teto, cap), "e já sem folga para outra rodada"

    barato = [_answer("ok", 100)]
    assert within_budget(barato, cap)
    assert tools_still_affordable(barato, cap)


@pytest.mark.risco("R6")
async def test_a_turn_that_ran_out_of_room_answers_with_what_it_already_fetched() -> None:
    """R6 — a falha que este desenho existe para impedir: gastar tudo e não entregar.

    Antes, o teto era conferido só na entrada da fala, então o turno podia buscar,
    detalhar, validar — o código aprovar a composição — e só então descobrir que
    não tinha orçamento para contar a ninguém. Tudo pago, nada entregue.

    Aqui a conversa chega perto do teto com um retorno de tool já em mãos. O
    esperado é uma resposta de verdade, feita sem tools, e **não** a frase de
    limite: o cliente recebe o pior dos dois atendimentos possíveis, não nenhum.
    """
    subagent = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=_tool_de_leitura(), escreve=False)]
    )
    graph = build_graph(
        ModeloComEsemTools(messages=iter([])), InMemorySaver(), subagent, budget_tokens=1_000
    )

    await graph.aupdate_state(session_config("apertada"), {"messages": [_answer("trabalho", 850)]})

    final = await graph.ainvoke(
        {"session_id": "apertada", "messages": [HumanMessage(content="e aí?")]},
        config=session_config("apertada"),
    )

    assert final["messages"][-1].content == "fecha assim, olha só"
    assert final["messages"][-1].content != LIMIT_REACHED_MESSAGE


@pytest.mark.risco("R6")
async def test_past_the_hard_cap_there_is_still_no_answer_and_no_call() -> None:
    """R6 — degradar não removeu o fundo do poço.

    `adversarial-006` é um laço construído para queimar dinheiro. Se a linha macia
    tivesse substituído o teto duro em vez de vir antes dele, aquele ataque teria
    ganhado uma resposta a cada volta e o teto nunca fecharia.
    """

    class ModeloProibido(GenericFakeChatModel):
        def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
            del tools, tool_choice, kwargs
            return self

        async def ainvoke(self, *_: Any, **__: Any) -> Any:
            raise AssertionError("o modelo foi chamado com a sessao ja no teto duro")

    subagent = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=_tool_de_leitura(), escreve=False)]
    )
    graph = build_graph(
        ModeloProibido(messages=iter([])), InMemorySaver(), subagent, budget_tokens=100
    )

    await graph.aupdate_state(session_config("abusiva"), {"messages": [_answer("caro", 500)]})

    final = await graph.ainvoke(
        {"session_id": "abusiva", "messages": [HumanMessage(content="de novo")]},
        config=session_config("abusiva"),
    )

    assert final["messages"][-1].content == LIMIT_REACHED_MESSAGE
