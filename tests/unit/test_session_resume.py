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

from decimal import Decimal
from typing import Any, cast

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.composicao import TipoDeEvento
from vendinha.fiscal import (
    Aprovacao,
    Decisao,
    EmissaoState,
    FiscalEmMemoria,
    abrir_fila_da_nota,
    build_emissao_graph,
    decidir,
    thread_da_nota,
)
from vendinha.graph import ConversationState, build_graph, session_config
from vendinha.nota import MockNFAdapter
from vendinha.pedidos import (
    ComposicaoDoPedido,
    Empresa,
    Endereco,
    ItemDoPedido,
    Pedido,
    PedidosEmMemoria,
    StatusDoPedido,
)
from vendinha.subagents import (
    PROMPT_RECOMENDACAO,
    RECOMENDACAO,
    Subagent,
    registrar,
)

pytestmark = pytest.mark.requires_backend


def _sem_catalogo() -> Subagent:
    """O subagent da recomendação sem nenhuma tool.

    Este arquivo não mede recomendação — mede a retomada a partir do checkpoint. Um subagent sem tool
    mantém o grafo no formato de uma volta só, que é o que estas asserções
    descrevem, e deixa o laço de tools para quem o testa.
    """
    return registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, [])


def _model(*answers: str) -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content=a) for a in answers]))


async def _say(graph: Any, session_id: str, text: str) -> dict[str, Any]:
    state: dict[str, Any] = await graph.ainvoke(
        {"session_id": session_id, "messages": [HumanMessage(content=text)]},
        config=session_config(session_id),
    )
    return state


@pytest.mark.risco("R9")
async def test_conversation_resumes_with_the_same_session_id() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(_model("bom dia", "claro", "anotado"), checkpointer, _sem_catalogo())

    await _say(graph, "sessao-1", "oi, tudo bem?")
    await _say(graph, "sessao-1", "queria um presente")
    final = await _say(graph, "sessao-1", "para minha mae")

    said = [m.content for m in final["messages"]]
    assert "oi, tudo bem?" in said, "the first turn vanished from the resumed state"
    assert "queria um presente" in said
    assert len(final["messages"]) == 6, "three turns are three questions and three answers"


@pytest.mark.risco("R9")
async def test_a_new_graph_reads_what_the_previous_one_wrote() -> None:
    """The closest a unit test gets to a restart: nothing survives but the checkpointer."""
    checkpointer = InMemorySaver()

    before = build_graph(_model("ola", "ainda aqui"), checkpointer, _sem_catalogo())
    await _say(before, "sessao-2", "meu nome ficou registrado?")
    del before

    after = build_graph(_model("ainda aqui"), checkpointer, _sem_catalogo())
    resumed = await _say(after, "sessao-2", "e agora?")

    said = [m.content for m in resumed["messages"]]
    assert "meu nome ficou registrado?" in said, (
        "the new graph did not read the previous checkpoint"
    )


@pytest.mark.risco("R9")
async def test_two_sessions_do_not_share_state() -> None:
    checkpointer = InMemorySaver()
    graph = build_graph(_model("a", "b"), checkpointer, _sem_catalogo())

    await _say(graph, "sessao-a", "segredo da sessao a")
    other = await _say(graph, "sessao-b", "nada a ver")

    said = [m.content for m in other["messages"]]
    assert "segredo da sessao a" not in said, "thread_id is not isolating the sessions"


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
    allowed = {"session_id", "messages"}
    assert set(ConversationState.__annotations__) == allowed


# ---------------------------------------------------- a pausa da nota (S-05)
#
# A mesma pergunta da R9, sobre o outro grafo: o que sobrevive ao processo? A
# emissão só é HITL de verdade se a pausa aguentar um restart — o `golden-004`
# reprova quem perde o estado durante a espera, e a espera aqui dura o tempo de
# uma pessoa abrir a fila, que é ordem de grandeza de horas.
#
# A metade que ESTE arquivo não prova continua sendo a mesma: restart real do
# processo contra o Postgres de verdade, verificado à mão no `/fechar-spec`
# (`docs/testes.md` §1). O que dá para provar sem contêiner é que um grafo
# construído do zero, compartilhando com o anterior **só o checkpointer**, retoma
# a pausa que o outro deixou.


def _pedido_pago() -> tuple[PedidosEmMemoria, str]:
    """Um pedido no estado em que o webhook o deixa: pago, esperando a nota."""
    pedidos = PedidosEmMemoria()
    pedido = Pedido(
        id="pedido-em-espera",
        empresa=Empresa(
            razao_social="Aurora Servicos Digitais LTDA",
            cnpj="11.222.333/0001-81",
            contato_nome="Marta Ribeiro",
            contato_email="marta@exemplo.com.br",
            endereco=Endereco(
                logradouro="Rua das Acacias",
                numero="240",
                bairro="Savassi",
                cidade="Belo Horizonte",
                uf="MG",
                cep="30140-071",
            ),
        ),
        composicoes=(
            ComposicaoDoPedido(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                itens=(
                    ItemDoPedido(
                        produto_id="cafe-moido-tradicional",
                        nome="Cafe moido tradicional",
                        tipo="cafe",
                        rendimento=40,
                        quantidade=1,
                        preco_unitario=Decimal("39.00"),
                        subtotal=Decimal("39.00"),
                    ),
                ),
                total=Decimal("39.00"),
                valor_por_pessoa=Decimal("1.95"),
            ),
        ),
        total=Decimal("39.00"),
        status=StatusDoPedido.AGUARDANDO_APROVACAO_NF,
    )
    pedidos.gravados[pedido.id] = pedido
    return pedidos, pedido.id


def _grafo_da_nota(
    pedidos: PedidosEmMemoria, fiscal: FiscalEmMemoria, checkpointer: InMemorySaver
) -> Any:
    return build_emissao_graph(pedidos, fiscal, MockNFAdapter(), checkpointer)


@pytest.mark.risco("R3")
async def test_the_invoice_graph_pauses_with_its_state_in_the_checkpointer() -> None:
    """R3, RF-3.1 — pagamento confirmado põe o pedido numa pausa persistida.

    Duas asserções, e as duas importam: que ele **parou** (`next` aponta para o nó
    que ainda vai rodar) e que o que ficou guardado é o identificador do pedido. Um
    grafo que tivesse corrido até o fim teria `next` vazio — e teria emitido.
    """
    pedidos, pedido_id = _pedido_pago()
    fiscal = FiscalEmMemoria()
    checkpointer = InMemorySaver()
    grafo = _grafo_da_nota(pedidos, fiscal, checkpointer)

    await abrir_fila_da_nota(grafo, pedido_id)

    estado = await grafo.aget_state(thread_da_nota(pedido_id))
    assert estado.next, "o grafo não parou: sem interrupt não há HITL"
    assert estado.values == {"pedido_id": pedido_id}
    assert await fiscal.nota_de(pedido_id) is None, "nada foi emitido durante a pausa"


@pytest.mark.risco("R9")
async def test_a_new_invoice_graph_resumes_the_pause_the_previous_one_left() -> None:
    """R9, R3 — o mais perto que um teste unitário chega de um restart.

    O segundo grafo não compartilha nada com o primeiro além do checkpointer: ports
    novas não, porque a decisão e a nota precisam sobreviver junto; mas o objeto do
    grafo, os nós e as closures são outros. É o que separa "o estado estava na
    memória do processo" de "o estado estava no checkpointer".
    """
    pedidos, pedido_id = _pedido_pago()
    fiscal = FiscalEmMemoria()
    checkpointer = InMemorySaver()

    antes = _grafo_da_nota(pedidos, fiscal, checkpointer)
    await abrir_fila_da_nota(antes, pedido_id)
    del antes

    depois = _grafo_da_nota(pedidos, fiscal, checkpointer)
    await decidir(
        depois,
        Aprovacao(pedido_id=pedido_id, decisao=Decisao.APROVADA, operador="ana.souza"),
        fiscal=fiscal,
    )

    emitida = await fiscal.nota_de(pedido_id)
    assert emitida is not None, "o grafo novo não retomou a pausa do anterior"
    assert emitida.nota.aprovada_por == "ana.souza"
    assert pedidos.gravados[pedido_id].status is StatusDoPedido.NOTA_EMITIDA


@pytest.mark.risco("R9")
async def test_the_queue_survives_a_thread_that_was_never_opened() -> None:
    """R9, R3 — a fila é derivada do banco, então a aprovação nunca fica sem caminho.

    O cenário é o webhook que confirmou o pagamento e falhou ao abrir a pausa: a
    thread não existe. O pedido continua na fila pelo status, e `decidir` conduz o
    grafo do começo. Sem isto, um `ainvoke` que falhasse uma vez deixaria um pedido
    pago sem nota para sempre — e sem ninguém notando, que é o pior lado.
    """
    pedidos, pedido_id = _pedido_pago()
    fiscal = FiscalEmMemoria()
    grafo = _grafo_da_nota(pedidos, fiscal, InMemorySaver())

    assert not (await grafo.aget_state(thread_da_nota(pedido_id))).values
    assert await pedidos.aguardando_aprovacao_de_nf()

    await decidir(
        grafo,
        Aprovacao(pedido_id=pedido_id, decisao=Decisao.APROVADA, operador="ana.souza"),
        fiscal=fiscal,
    )

    assert await fiscal.nota_de(pedido_id) is not None


@pytest.mark.risco("R9")
def test_the_invoice_graph_state_carries_one_identifier_and_no_payload() -> None:
    """RNF-6, R9 — pointer-not-payload, e este teste é chato pelo mesmo motivo.

    O pedido, a empresa, os itens e a nota emitida **não** entram no estado. O
    checkpointer guardaria uma cópia que ninguém migra e ninguém invalida, e no dia
    em que ela divergisse do banco a nota sairia com a versão errada de um documento
    fiscal. Alargar este conjunto tem que ser um ato deliberado, com revisor olhando.
    """
    assert set(EmissaoState.__annotations__) == {"pedido_id"}


@pytest.mark.risco("R9")
async def test_a_conversation_and_an_invoice_with_the_same_id_do_not_share_a_thread() -> None:
    """R9, RNF-6 — o namespace `nf:` separa as duas máquinas de estado.

    `fiscal.py` defende em dois lugares que o prefixo impede a thread da nota de
    colidir com um `session_id` no mesmo checkpointer. Era prosa: apagar o prefixo
    deixava a suíte verde (ressalva B-1 da verificação da S-05).

    O teste força a colisão que na prática é improvável — os dois são `uuid4` — usando
    **o mesmo identificador** como sessão e como pedido. Sem o prefixo, o grafo da
    conversa e o da emissão passariam a ler e escrever o mesmo histórico, e o segundo
    encontraria `messages` onde espera `pedido_id`.
    """
    mesmo_id = "identificador-em-comum"
    checkpointer = InMemorySaver()
    pedidos, _ = _pedido_pago()
    pedidos.gravados[mesmo_id] = pedidos.gravados.pop("pedido-em-espera").model_copy(
        update={"id": mesmo_id}
    )

    conversa = build_graph(_model("oi"), checkpointer, _sem_catalogo())
    await _say(conversa, mesmo_id, "uma mensagem qualquer")

    nota = _grafo_da_nota(pedidos, FiscalEmMemoria(), checkpointer)
    await abrir_fila_da_nota(nota, mesmo_id)

    # A asserção é sobre o **checkpointer**, e não sobre o estado que cada grafo
    # devolve. Uma primeira versão deste teste comparava `aget_state` dos dois e
    # passava mesmo com o prefixo apagado: o LangGraph filtra os valores pelos canais
    # do grafo que pergunta, então a colisão fica invisível de dentro. Perguntando
    # direto ao checkpointer, ela aparece — com um prefixo vazio os dois `config`
    # endereçam a MESMA thread, e os dois checkpoints passam a ser o mesmo.
    da_conversa = await checkpointer.aget_tuple(session_config(mesmo_id))
    da_nota = await checkpointer.aget_tuple(cast(RunnableConfig, thread_da_nota(mesmo_id)))
    assert da_conversa is not None and da_nota is not None

    assert (
        da_conversa.config["configurable"]["thread_id"]
        != (da_nota.config["configurable"]["thread_id"])
    ), "a conversa e a nota do mesmo id caíram na mesma thread"
    assert "messages" in da_conversa.checkpoint["channel_values"]
    assert "pedido_id" in da_nota.checkpoint["channel_values"]
    assert "messages" not in da_nota.checkpoint["channel_values"]
