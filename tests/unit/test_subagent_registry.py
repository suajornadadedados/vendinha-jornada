"""R1 — o subagent de recomendação lê o catálogo, e o registro recusa dar-lhe escrita.

Dois assuntos, e vale dizer por que estão no mesmo arquivo: são as duas metades da
mesma decisão. O registro diz o que o subagent **consegue** fazer; o grafo é o que
efetivamente executa o que ele pediu. Um teste do registro sem o laço de tools
provaria que a lista está certa e não que ela é usada.

**Sobre a camada.** A invariante "o subagent de recomendação não escreve" é o R2, e
`docs/testes.md` a coloca em `tests/security/test_permission_boundary.py`, na S-04.
Ela não está aqui — e não é esquecimento. Hoje não existe nenhuma tool de escrita
no repositório: `criar_pedido` e `emitir_nf` chegam na S-04 e na S-05. Um teste de
`security` afirmando a invariante passaria por vacuidade, e `docs/testes.md` §3.3
recusa exatamente isso ("teste que nasceu verde não provou nada").

O que dá para provar hoje é que o **mecanismo recusa**, e é isso que este arquivo
faz, com uma tool de escrita construída aqui dentro. Quando as de verdade
existirem, a camada `security` afirma sobre elas.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.catalogo import BuscaEmMemoria, CatalogoEmMemoria, Produto, carregar_seed
from vendinha.graph import ConversationState, build_graph, session_config
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    SOMENTE_LEITURA,
    Ferramenta,
    FronteiraDePermissaoViolada,
    recomendacao,
    registrar,
)

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


def _tool_de_escrita() -> BaseTool:
    """A tool que a S-04 vai trazer, construída aqui para o registro ter o que recusar.

    Ela precisa existir para este teste não ser vacuoso: sem nenhuma tool de
    escrita no repositório, "recomendacao não tem tool de escrita" é verdade por
    acidente.
    """

    async def criar_pedido(_produto_id: str) -> str:
        raise AssertionError("esta tool nunca deveria ser executada")

    return StructuredTool.from_function(
        coroutine=criar_pedido, name="criar_pedido", description="Cria um pedido."
    )


class ModeloComTools(GenericFakeChatModel):
    """Um duplo de modelo que aceita `bind_tools`.

    Os fakes do LangChain não implementam `bind_tools` — a chamada levanta
    `NotImplementedError`. Aceitar o bind e ignorá-lo é o suficiente: o que este
    arquivo mede é o que o **grafo** faz com uma resposta que pede tool, não como o
    modelo decidiu pedi-la.
    """

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:
        del tools, tool_choice, kwargs
        return self


# ------------------------------------------------------------------ o registro


@pytest.mark.risco("R1")
def test_the_recommendation_subagent_is_registered_with_read_only_tools_only(
    seed: tuple[Produto, ...],
) -> None:
    """R1, RF-1.5 — o subagent existe, e o que ele tem é leitura e validação.

    `validar_composicao` entrou na S-11 e não move a fronteira: propor uma
    composição é ler o catálogo e somar. O veredito não autoriza venda — quem
    autoriza é `criar_pedido`, na S-04, e ele revalida do zero (ADR-013, RF-2.7).
    """
    subagent = recomendacao(BuscaEmMemoria(seed), CatalogoEmMemoria(seed), SEM_TIMEOUT)

    assert subagent.nome == RECOMENDACAO
    assert {tool.name for tool in subagent.tools} == {
        "buscar_produtos",
        "detalhar_produto",
        "consultar_preco",
        "validar_composicao",
    }
    assert subagent.escritoras == ()
    assert all(not ferramenta.escreve for ferramenta in subagent.ferramentas)


@pytest.mark.risco("R1")
def test_registering_a_write_tool_on_the_recommendation_subagent_is_refused() -> None:
    """R1, ADR-002 — a fronteira é estrutural: o subagent errado não chega a existir.

    A recusa é na construção, e não numa checagem que alguém roda depois. Entre
    "foi montado errado" e "alguém percebeu" não pode existir uma janela.
    """
    with pytest.raises(FronteiraDePermissaoViolada, match="criar_pedido"):
        registrar(
            RECOMENDACAO,
            PROMPT_RECOMENDACAO,
            [Ferramenta(tool=_tool_de_escrita(), escreve=True)],
        )


@pytest.mark.risco("R1")
def test_the_refusal_is_scoped_to_the_subagents_declared_read_only() -> None:
    """R1 — a regra não é "ninguém escreve": é "este aqui não escreve".

    Sem esta metade, o teste acima passaria também com um registro que recusa
    qualquer tool de escrita em qualquer subagent — o que quebraria a S-04 inteira
    e não teria nada a ver com o ADR-002.
    """
    assert "checkout" not in SOMENTE_LEITURA

    subagent = registrar(
        "checkout", "prompt do checkout", [Ferramenta(tool=_tool_de_escrita(), escreve=True)]
    )

    assert subagent.escritoras == ("criar_pedido",)


@pytest.mark.risco("R1")
def test_a_write_tool_declared_read_only_is_the_registrys_blind_spot() -> None:
    """R1 — `escreve` é declarado por quem registra, e o registro confia nisso.

    Está escrito assim de propósito: inferir por convenção de nome ("começa com
    criar_, então escreve") seria a mesma segurança comportamental que o ADR-002
    recusou, só que dentro do nosso código. O teste existe para que o limite fique
    documentado e não seja descoberto como surpresa — quem registra uma tool nova
    é quem responde por essa linha, e é isso que o CODEOWNERS e a revisão cobrem.
    """
    subagent = registrar(
        RECOMENDACAO, PROMPT_RECOMENDACAO, [Ferramenta(tool=_tool_de_escrita(), escreve=False)]
    )

    assert subagent.escritoras == ()
    assert [tool.name for tool in subagent.tools] == ["criar_pedido"]


# ----------------------------------------------------------------- o laço no grafo


@pytest.mark.risco("R1")
async def test_a_tool_call_is_executed_and_its_return_comes_back_as_a_tool_message(
    seed: tuple[Produto, ...],
) -> None:
    """R1 — o fato entra na conversa como retorno de tool, e não como texto do modelo.

    É a propriedade de que o eval de groundedness depende: se a tool não fosse de
    fato executada, o preço na resposta final não teria origem nenhuma a apontar.
    """
    pedido = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "consultar_preco",
                "args": {"produto_ids": ["queijo-canastra-meia-cura"]},
                "id": "chamada-1",
            }
        ],
    )
    resposta = AIMessage(content="O Canastra meia-cura sai por R$ 89,90.")
    subagent = recomendacao(BuscaEmMemoria(seed), CatalogoEmMemoria(seed), SEM_TIMEOUT)

    graph = build_graph(
        ModeloComTools(messages=iter([pedido, resposta])), InMemorySaver(), subagent
    )
    final = await graph.ainvoke(
        {"session_id": "s", "messages": [HumanMessage(content="quanto custa o Canastra?")]},
        config=session_config("s"),
    )

    retornos = [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert len(retornos) == 1, "a chamada de tool não foi executada pelo grafo"

    devolvido = json.loads(str(retornos[0].content))["encontrados"][0]
    esperado = next(p for p in seed if p.id == "queijo-canastra-meia-cura")
    assert devolvido["preco"] == str(esperado.preco)
    assert final["messages"][-1].content == resposta.content


@pytest.mark.risco("R9")
async def test_a_tool_round_does_not_widen_the_checkpointed_state(
    seed: tuple[Produto, ...],
) -> None:
    """R9, RNF-6 — pointer-not-payload: o laço de tools não acrescentou chave nenhuma.

    O caminho fácil, quando a recomendação chega, é guardar "o último produto
    consultado" no estado. Isso começaria a segunda cópia do catálogo que
    `catalogo.py` existe para evitar — e ninguém migra nem invalida um checkpoint.
    """
    pedido = AIMessage(
        content="",
        tool_calls=[
            {"name": "buscar_produtos", "args": {"necessidade": "queijo"}, "id": "chamada-1"}
        ],
    )
    subagent = recomendacao(BuscaEmMemoria(seed), CatalogoEmMemoria(seed), SEM_TIMEOUT)
    checkpointer = InMemorySaver()

    graph = build_graph(
        ModeloComTools(messages=iter([pedido, AIMessage(content="temos estes")])),
        checkpointer,
        subagent,
    )
    await graph.ainvoke(
        {"session_id": "s", "messages": [HumanMessage(content="que queijos vocês têm?")]},
        config=session_config("s"),
    )

    gravado = (await graph.aget_state(session_config("s"))).values
    assert set(gravado) == set(ConversationState.__annotations__)
    assert set(gravado) == {"session_id", "messages"}


@pytest.mark.risco("R1")
async def test_a_subagent_with_no_tools_still_answers_in_a_single_pass() -> None:
    """R1 — o grafo sem tool continua com a forma de uma volta só.

    É a forma que `test_session_resume.py` e `test_budget_guard.py` descrevem, e
    ela precisa continuar existindo: um `add_conditional_edges` incondicional
    faria o grafo de S-02 depender de um nó de tools que ele não tem.
    """
    subagent = registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])

    graph = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="pois nao")])),
        InMemorySaver(),
        subagent,
    )
    final = await graph.ainvoke(
        {"session_id": "s", "messages": [HumanMessage(content="oi")]},
        config=session_config("s"),
    )

    assert not [m for m in final["messages"] if isinstance(m, ToolMessage)]
    assert final["messages"][-1].content == "pois nao"
