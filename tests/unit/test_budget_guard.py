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
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.budget import (
    LIMIT_REACHED_MESSAGE,
    NO_ROOM_TO_ACT_MESSAGE,
    TimedOut,
    run_with_timeout,
    tokens_spent,
    tools_still_affordable,
    within_budget,
)
from vendinha.catalogo import BuscaEmMemoria, CatalogoEmMemoria, Produto, carregar_seed
from vendinha.config import Settings
from vendinha.evals.caso import carregar_casos
from vendinha.evals.runner import EVALS, _monta_o_grafo
from vendinha.fiscal import FiscalEmMemoria
from vendinha.graph import DEFAULT_BUDGET_TOKENS, build_graph, session_config
from vendinha.pagamento import MockPaymentAdapter
from vendinha.pedidos import PedidosEmMemoria
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Ferramenta,
    Subagent,
    registrar,
)
from vendinha.supervisor import Rota


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
async def test_a_turn_that_ran_out_of_room_mid_flight_delivers_what_it_fetched() -> None:
    """R6 — a falha que este desenho existe para impedir: gastar tudo e não entregar.

    Antes, o teto era conferido só na entrada da fala, então o turno podia buscar,
    detalhar, validar — o código aprovar a composição — e só então descobrir que
    não tinha orçamento para contar a ninguém. Tudo pago, nada entregue.

    **A conversa cruza a linha macia NO MEIO do turno**, com retorno de tool já em
    mãos: entra com 790 de 1.000, o modelo pede tool duas vezes, e na volta da
    segunda os 810 gastos já passaram dos 800 da linha. O esperado é uma resposta de
    verdade, feita sem tools, e não a frase de limite — o cliente recebe o pior dos
    dois atendimentos possíveis, não nenhum.

    A versão anterior deste teste dizia isso no docstring e montava outra coisa: o
    estado não tinha `ToolMessage` nenhum, então o que ele media era a entrada do
    turno, que é o caso do teste seguinte e tem resposta oposta.
    """
    subagent = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=_tool_de_leitura(), escreve=False)]
    )
    graph = build_graph(
        ModeloComEsemTools(messages=iter([])), InMemorySaver(), subagent, budget_tokens=1_000
    )

    await graph.aupdate_state(session_config("apertada"), {"messages": [_answer("trabalho", 790)]})

    final = await graph.ainvoke(
        {"session_id": "apertada", "messages": [HumanMessage(content="e aí?")]},
        config=session_config("apertada"),
    )

    assert final["messages"][-1].content == "fecha assim, olha só"
    assert final["messages"][-1].content != LIMIT_REACHED_MESSAGE


@pytest.mark.risco("R6")
async def test_a_turn_that_starts_with_no_room_says_so_instead_of_improvising() -> None:
    """R6 — sem tool e sem nada buscado neste turno, quem responde é o código.

    Esta é a outra metade da linha macia, e ela foi escrita a partir de uma falha
    real. A sessão `5ac8c0a9` cruzou os 200k da linha no turno que entregou os dados
    da empresa; os quatro turnos seguintes rodaram sem tool nenhuma. O modelo não tem
    como perceber que ficou sem mãos, então respondeu como se não tivesse: coletou o
    resto dos dados, disse *"agora vou fechar o pedido para você"*, e `criar_pedido`
    não estava ligada. Zero pedido no banco, zero item na fila de aprovação, zero
    nota — e nada na tela que parecesse falha.

    Num turno que COMEÇA sem folga não há retorno de tool para entregar: o que sobra
    é o modelo improvisando sobre o histórico, que é onde ele inventa. Então a
    resposta é de código, e ela não afirma nada sobre o que já aconteceu na conversa
    — um pedido criado antes tornaria "nenhum pedido foi criado" mentira.
    """
    subagent = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=_tool_de_leitura(), escreve=False)]
    )
    graph = build_graph(
        ModeloComEsemTools(messages=iter([])), InMemorySaver(), subagent, budget_tokens=1_000
    )

    await graph.aupdate_state(session_config("sem-folga"), {"messages": [_answer("trabalho", 850)]})

    final = await graph.ainvoke(
        {"session_id": "sem-folga", "messages": [HumanMessage(content="e agora?")]},
        config=session_config("sem-folga"),
    )

    dito = final["messages"][-1].content
    assert dito == NO_ROOM_TO_ACT_MESSAGE
    assert dito != LIMIT_REACHED_MESSAGE, "o teto duro é a outra linha, e ela ainda não chegou"
    # `adversarial-006`: a frase é honesta sobre o resultado e muda sobre a máquina.
    for vazamento in ("token", "limite", "orçamento interno", "ferramenta", "tool"):
        assert vazamento not in dito.lower(), f"a frase de corte vazou {vazamento!r}"


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


CATALOGO_DO_SEED = Path(__file__).resolve().parents[2] / "data" / "catalogo"


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO_DO_SEED)


class ModeloComRoteador(GenericFakeChatModel):
    """Um duplo que aceita `bind_tools` e `with_structured_output`.

    O grafo supervisionado monta o roteador na **construção** — `with_structured_output`
    é chamado ali, e não na primeira rota. É deliberado: um modelo que não sabe devolver
    saída estruturada tem que quebrar ao montar o grafo, e não silenciosamente na
    primeira vez que alguém tentar fechar um pedido.
    """

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        del tools, tool_choice, kwargs
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        del schema, kwargs
        return RunnableLambda(lambda _: Rota(destino="recomendacao"))


@pytest.mark.risco("R6")
def test_the_graph_fallback_ceiling_is_the_same_number_the_settings_declare() -> None:
    """R6, RNF-3 — o fallback do grafo tem que andar junto com o `Settings`.

    Ressalva M-2 da verificação independente. A S-04 descobriu isto do jeito caro: o
    runner de evals construía o grafo **sem** passar o teto, então caía no fallback de
    `graph.py`, que estava parado num número anterior. A régua media um agente com
    outro orçamento que o de produção, o guarda tirava as tools no meio da conversa, e
    o caso reprovava parecendo um modelo que desistiu.

    A conferência é contra o **default declarado**, e não contra o valor resolvido do
    ambiente: o `.env` da máquina pode legitimamente sobrescrever o teto, e o que este
    teste protege é os dois lugares do repositório não divergirem. Era um comentário
    pedindo que alguém lembrasse; agora é uma linha vermelha.
    """
    declarado = Settings.model_fields["session_budget_tokens"].default

    assert DEFAULT_BUDGET_TOKENS == declarado


@pytest.mark.risco("R6")
async def test_the_eval_runner_hands_the_configured_ceiling_to_the_graph_it_builds(
    seed: tuple[Produto, ...],
) -> None:
    """R6 — o eval roda com o teto de produção, e não com o default do grafo.

    A asserção acima cobre os dois números baterem; esta cobre o teto **chegar** ao
    grafo que o runner monta. Sem ela, os dois valores poderiam estar sincronizados e
    o runner continuar ignorando a configuração — que foi exatamente o defeito.

    Um eval que roda com outra configuração mede outro sistema.
    """
    caso = next(c for c in carregar_casos(EVALS) if c.spec == "S-04")

    grafo = _monta_o_grafo(
        caso,
        ModeloComRoteador(messages=iter([AIMessage(content="não deveria falar")])),
        BuscaEmMemoria(seed),
        CatalogoEmMemoria(seed),
        PedidosEmMemoria(),
        MockPaymentAdapter("http://localhost:8000"),
        30.0,
        budget_tokens=0,
        fiscal=FiscalEmMemoria(),
    )
    gastou = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 1},
    )

    final = await grafo.ainvoke(
        {"session_id": "s", "messages": [gastou, HumanMessage(content="oi")]},
        config=session_config("s"),
    )

    # Teto zero: o nó de conversa devolve a mensagem de limite sem falar com o modelo
    # — que é o duplo que levantaria se fosse chamado.
    assert final["messages"][-1].content == LIMIT_REACHED_MESSAGE
