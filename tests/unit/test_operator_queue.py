"""R3 — a fila do operador: quem vê, quem decide, e o que fica gravado (REQ-2, REQ-3).

Este arquivo é sobre a **API** da fila, e mora em `unit` pelo mesmo motivo que o
webhook: são rotas, um `hmac` e duas transações. A pergunta da camada `security` —
*existe caminho até a emissão sem aprovação registrada?* — é de
`tests/security/test_hitl_invariant.py`, e as duas não se substituem: uma fila
correta atrás de uma porta que aceita qualquer POST não fecha nada, e uma porta
correta na frente de uma fila que perde pedido também não.

O que se prova aqui:

1. **a porta existe.** Sem `OPERADOR_API_TOKEN`, as três rotas respondem 401 — e
   isso inclui o caso em que a variável não foi configurada, que é o lado seguro;
2. **a fila mostra o que a nota vai ler**, destinatário PJ e composição item a item
   (RF-3.2), e não uma segunda projeção que possa divergir;
3. **a decisão fica gravada com quem, quando e — na rejeição — por quê** (RF-3.3,
   RF-4.2), e a primeira decisão vence;
4. **aprovar retoma o grafo e a nota sai**; rejeitar tira o pedido do caminho de
   emissão (`golden-011`);
5. **um pedido não pago não pode ser decidido**, porque emitir nota do que ninguém
   pagou é o erro mais caro que esta rota poderia cometer.

Nada é mockado a não ser a fronteira de port: `PedidosEmMemoria`, `FiscalEmMemoria`
e `MockNFAdapter` são implementações de primeira classe das próprias portas
(ADR-004, `docs/testes.md` §4). O grafo da emissão é o de produção.
"""

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from vendinha.app import create_app
from vendinha.catalogo import CatalogoEmMemoria, carregar_seed
from vendinha.composicao import TipoDeEvento
from vendinha.config import get_settings
from vendinha.config_store import InMemoryConfigStore
from vendinha.documentos import formatar_cnpj
from vendinha.fiscal import Decisao, FiscalEmMemoria
from vendinha.graph import build_graph
from vendinha.nota import ISENTO, TARJA, MockNFAdapter
from vendinha.pedidos import (
    ComposicaoDoPedido,
    Empresa,
    Endereco,
    ItemDoPedido,
    Pedido,
    PedidosEmMemoria,
    StatusDoPedido,
)
from vendinha.subagents import PROMPT_RECOMENDACAO, RECOMENDACAO, registrar

pytestmark = pytest.mark.requires_backend

CATALOGO_DO_SEED = Path(__file__).resolve().parents[2] / "data" / "catalogo"

# Fabricado, como toda credencial deste repositório (RNF-7).
TOKEN = "token-de-operador-de-teste"  # noqa: S105
PEDIDO_ID = "pedido-na-fila"
OPERADOR = "ana.souza"
MOTIVO = "inscricao estadual da empresa nao confere com o CNPJ informado"

# Os números do pedido de teste, escritos aqui e em nenhum outro lugar. É contra
# eles que as asserções comparam — recalcular a partir do que a rota devolveu seria
# o teste tautológico que `docs/testes.md` §4 recusa.
CNPJ = "11.222.333/0001-81"
RAZAO_SOCIAL = "Aurora Servicos Digitais LTDA"
PRECO = Decimal("39.00")
QUANTIDADE = 2
TOTAL = Decimal("78.00")
PESSOAS = 20


def _pedido(status: StatusDoPedido = StatusDoPedido.AGUARDANDO_APROVACAO_NF) -> Pedido:
    return Pedido(
        id=PEDIDO_ID,
        empresa=Empresa(
            razao_social=RAZAO_SOCIAL,
            cnpj=CNPJ,
            contato_nome="Marta Ribeiro",
            contato_email="marta@exemplo.com.br",
            endereco=Endereco(
                logradouro="Rua das Acacias",
                numero="240",
                complemento="sala 12",
                bairro="Savassi",
                cidade="Belo Horizonte",
                uf="MG",
                cep="30140-071",
            ),
        ),
        composicoes=(
            ComposicaoDoPedido(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=PESSOAS,
                itens=(
                    ItemDoPedido(
                        produto_id="cafe-moido-tradicional",
                        nome="Cafe moido tradicional para coador",
                        tipo="cafe",
                        rendimento=40,
                        quantidade=QUANTIDADE,
                        preco_unitario=PRECO,
                        subtotal=TOTAL,
                    ),
                ),
                total=TOTAL,
                valor_por_pessoa=Decimal("3.90"),
            ),
        ),
        total=TOTAL,
        status=status,
    )


@pytest.fixture
def gravados() -> PedidosEmMemoria:
    pedidos = PedidosEmMemoria()
    pedidos.gravados[PEDIDO_ID] = _pedido()
    return pedidos


@pytest.fixture
def fiscal() -> FiscalEmMemoria:
    return FiscalEmMemoria()


@pytest.fixture
def com_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """O token do operador, configurado como em produção.

    Via `Settings` e não por variável de ambiente porque `get_settings` é cacheado —
    a mesma razão do `com_segredo` de `test_payment_webhook.py`.
    """
    monkeypatch.setattr(get_settings(), "operador_api_token", TOKEN)


@pytest.fixture
def sem_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum token configurado, explicitamente.

    Sem esta fixture o teste da ausência dependeria de o `.env` da máquina não ter a
    variável, e passaria por acidente em quem nunca configurou a fila.
    """
    monkeypatch.setattr(get_settings(), "operador_api_token", None)


@pytest.fixture
def client(gravados: PedidosEmMemoria, fiscal: FiscalEmMemoria) -> Iterator[TestClient]:
    conversa = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="oi")])),
        InMemorySaver(),
        registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, []),
    )
    app = create_app(
        graph=conversa,
        store=InMemoryConfigStore(),
        catalogo=CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED)),
        pedidos=gravados,
        fiscal=fiscal,
        emissor=MockNFAdapter(),
        checkpointer=InMemorySaver(),
    )
    with TestClient(app) as test_client:
        yield test_client


AUTORIZADO = {"X-Operador-Token": TOKEN}


# ------------------------------------------------------------------- a porta


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", "/operador/fila"),
        ("post", f"/operador/pedidos/{PEDIDO_ID}/aprovar"),
        ("post", f"/operador/pedidos/{PEDIDO_ID}/rejeitar"),
    ],
)
def test_no_operator_route_answers_without_the_token(
    client: TestClient, fiscal: FiscalEmMemoria, metodo: str, caminho: str
) -> None:
    """R3, REQ-2 — a fila lista PII e autoriza emissão; ela não pode ficar aberta.

    Parametrizado sobre as três rotas de propósito: uma rota nova que esquecesse a
    verificação entraria nesta lista e reprovaria, em vez de nascer aberta.
    """
    resposta = client.request(metodo, caminho, json={"operador": OPERADOR, "motivo": MOTIVO})

    assert resposta.status_code == 401
    assert not fiscal.decisoes, "uma requisição recusada não pode ter gravado decisão"


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("sem_token")
def test_with_no_token_configured_nothing_authenticates(client: TestClient) -> None:
    """R3 — o lado seguro: sem `OPERADOR_API_TOKEN`, ninguém entra.

    O oposto — "sem token, aceita tudo" — transformaria esquecer uma variável de
    ambiente num endpoint aberto que emite documento fiscal. É a mesma escolha que
    `assinatura_confere` faz para o webhook do gateway.
    """
    assert client.get("/operador/fila", headers=AUTORIZADO).status_code == 401
    assert client.get("/operador/fila", headers={"X-Operador-Token": ""}).status_code == 401


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_a_wrong_token_is_refused_without_saying_what_was_wrong(client: TestClient) -> None:
    """R3 — 401 sem detalhe: quem errou o token não precisa saber o que errou."""
    resposta = client.get("/operador/fila", headers={"X-Operador-Token": TOKEN + "x"})

    assert resposta.status_code == 401
    assert TOKEN not in resposta.text


# -------------------------------------------------------------------- a fila


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_the_queue_shows_the_pj_recipient_and_the_composition_line_by_line(
    client: TestClient,
) -> None:
    """R3, RF-3.2 — o operador decide sobre o que vai sair, não sobre um resumo.

    Cada campo é conferido contra as constantes do topo. Mostrar só razão social e
    total pediria uma decisão às cegas — e o `golden-011` rejeita uma nota
    justamente por um dado do destinatário que precisa estar visível.
    """
    fila = client.get("/operador/fila", headers=AUTORIZADO).json()["pendentes"]

    assert len(fila) == 1
    pedido = fila[0]
    assert pedido["pedido_id"] == PEDIDO_ID
    assert Decimal(pedido["total"]) == TOTAL

    destinatario = pedido["destinatario"]
    assert destinatario["razao_social"] == RAZAO_SOCIAL
    # Em claro e formatado: aqui quem lê é a pessoa que vai conferir o documento.
    # É o oposto do retorno de tool, onde o CNPJ é mascarado porque o leitor é o
    # modelo (ADR-007, R5).
    assert destinatario["cnpj"] == formatar_cnpj("11222333000181")
    assert destinatario["inscricao_estadual"] == ISENTO
    assert destinatario["contato_email"] == "marta@exemplo.com.br"
    assert destinatario["endereco"]["cep"] == "30140-071"
    assert destinatario["endereco"]["uf"] == "MG"

    (composicao,) = pedido["composicoes"]
    assert composicao["pessoas"] == PESSOAS
    (item,) = composicao["itens"]
    assert item["produto_id"] == "cafe-moido-tradicional"
    assert item["quantidade"] == QUANTIDADE
    assert Decimal(item["preco_unitario"]) == PRECO
    assert Decimal(item["subtotal"]) == TOTAL


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_an_order_that_is_not_paid_yet_is_not_in_the_queue(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R3, RF-3.1 — a fila começa depois do pagamento confirmado, nunca antes."""
    gravados.gravados[PEDIDO_ID] = _pedido(StatusDoPedido.AGUARDANDO_PAGAMENTO)

    assert client.get("/operador/fila", headers=AUTORIZADO).json()["pendentes"] == []


# ---------------------------------------------------------------- a aprovação


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_approving_records_who_and_when_and_only_then_the_invoice_exists(
    client: TestClient, fiscal: FiscalEmMemoria, gravados: PedidosEmMemoria
) -> None:
    """R3, RF-3.3 — aprovar grava a decisão, retoma o grafo, e a nota sai.

    A ordem importa e está afirmada por consequência: antes da chamada não existe
    nota, depois existe — e o operador que a autorizou está dentro dela. Se a rota
    emitisse direto, sem registro, esta asserção passaria igual; é
    `tests/security/test_hitl_invariant.py` que fecha esse lado.
    """
    assert fiscal.notas == {}

    resposta = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["decisao"] == Decisao.APROVADA.value
    assert corpo["operador"] == OPERADOR
    assert corpo["decidido_em"]
    assert corpo["numero_nota"] == 1
    assert len(corpo["chave_da_nota"]) == 44

    gravada = fiscal.decisoes[PEDIDO_ID]
    assert gravada.decisao is Decisao.APROVADA
    assert gravada.operador == OPERADOR

    emitida = fiscal.notas[PEDIDO_ID]
    assert emitida.nota.aprovada_por == OPERADOR
    assert emitida.nota.total == TOTAL
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.NOTA_EMITIDA


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_an_approved_order_leaves_the_queue(client: TestClient) -> None:
    """R3 — decidido é decidido: o pedido some da fila, e ninguém decide de novo."""
    client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    )

    assert client.get("/operador/fila", headers=AUTORIZADO).json()["pendentes"] == []


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_approving_twice_issues_one_invoice_and_not_two(
    client: TestClient, fiscal: FiscalEmMemoria
) -> None:
    """R3 — duplo clique no botão do operador não produz duas notas.

    Duas notas para um pedido é um problema fiscal de verdade, e o botão é a fonte
    mais provável: uma pessoa clica de novo quando a página demora. A garantia não é
    o botão — é a chave primária de `nota_fiscal` e a de `aprovacao_de_nf`.
    """
    primeiro = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    )
    segundo = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": "outro.operador"},
        headers=AUTORIZADO,
    )

    assert primeiro.status_code == segundo.status_code == 200
    assert primeiro.json()["numero_nota"] == segundo.json()["numero_nota"]
    assert primeiro.json()["chave_da_nota"] == segundo.json()["chave_da_nota"]
    # A PRIMEIRA decisão vence, e a resposta diz a verdade sobre quem autorizou.
    assert segundo.json()["operador"] == OPERADOR
    assert len(fiscal.notas) == 1


# ---------------------------------------------------------------- a rejeição


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_rejecting_requires_a_reason_and_changes_nothing_without_one(
    client: TestClient, fiscal: FiscalEmMemoria, gravados: PedidosEmMemoria
) -> None:
    """RF-4.2 — rejeição sem motivo é recusada, e nada acontece.

    O motivo é o que o cliente lê no chat quando pergunta pela nota. Sem ele a
    rejeição vira silêncio para quem pagou — e a defesa não é a rota lembrar de
    checar: é `fiscal.Aprovacao` não conseguir existir sem motivo.
    """
    for corpo in ({"operador": OPERADOR}, {"operador": OPERADOR, "motivo": "   "}):
        resposta = client.post(
            f"/operador/pedidos/{PEDIDO_ID}/rejeitar", json=corpo, headers=AUTORIZADO
        )

        assert resposta.status_code == 422
        assert fiscal.decisoes == {}
        assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_rejecting_records_the_reason_and_takes_the_order_off_the_emission_path(
    client: TestClient, fiscal: FiscalEmMemoria, gravados: PedidosEmMemoria
) -> None:
    """R3, RF-4.2, `golden-011` — a rejeição é um desfecho, e ela é gravada.

    O `nao_deve` central daquele caso é *reapresentar o pedido para aprovação
    automaticamente*. O que impede isso não é o prompt: é o pedido sair de
    `aguardando_aprovacao_nf`, então não existe mais fila em que ele possa ser
    aprovado por engano.
    """
    resposta = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/rejeitar",
        json={"operador": OPERADOR, "motivo": MOTIVO},
        headers=AUTORIZADO,
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["decisao"] == Decisao.REJEITADA.value
    assert corpo["motivo"] == MOTIVO
    assert corpo["numero_nota"] is None

    assert fiscal.notas == {}, "uma rejeição não pode ter emitido nada"
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.NOTA_REJEITADA
    assert client.get("/operador/fila", headers=AUTORIZADO).json()["pendentes"] == []


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_a_rejected_order_cannot_be_approved_afterwards(
    client: TestClient, fiscal: FiscalEmMemoria, gravados: PedidosEmMemoria
) -> None:
    """R3 — a primeira decisão vence, e a segunda recebe a verdade de volta.

    Um 200 anunciando aprovação sobre um pedido rejeitado seria pior do que um erro:
    o operador acreditaria ter aprovado, e a nota nunca sairia. A resposta devolve a
    rejeição, com quem, quando e por quê.
    """
    client.post(
        f"/operador/pedidos/{PEDIDO_ID}/rejeitar",
        json={"operador": OPERADOR, "motivo": MOTIVO},
        headers=AUTORIZADO,
    )

    depois = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": "outro.operador"},
        headers=AUTORIZADO,
    )

    assert depois.status_code == 200
    assert depois.json()["decisao"] == Decisao.REJEITADA.value
    assert depois.json()["motivo"] == MOTIVO
    assert fiscal.notas == {}
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.NOTA_REJEITADA


# ---------------------------------------------------------- o que não se decide


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_an_unpaid_order_cannot_be_decided_at_all(
    client: TestClient, fiscal: FiscalEmMemoria, gravados: PedidosEmMemoria
) -> None:
    """R3, RF-3.1 — emitir nota do que ninguém pagou é o erro mais caro desta rota.

    A fila nasce da confirmação do pagamento. Um pedido em `aguardando_pagamento`
    não está nela, e chamar a rota direto com o id dele é recusado — porque a fila
    ser derivada do status protege a listagem, não a rota.
    """
    gravados.gravados[PEDIDO_ID] = _pedido(StatusDoPedido.AGUARDANDO_PAGAMENTO)

    resposta = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    )

    assert resposta.status_code == 409
    assert fiscal.decisoes == {}
    assert fiscal.notas == {}


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_deciding_an_order_that_does_not_exist_is_a_404(
    client: TestClient, fiscal: FiscalEmMemoria
) -> None:
    """R3 — id inventado não vira decisão pendurada num pedido inexistente."""
    resposta = client.post(
        "/operador/pedidos/nao-existe/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    )

    assert resposta.status_code == 404
    assert fiscal.decisoes == {}


# -------------------------------------------------------- do webhook até a fila


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_a_payment_confirmed_on_the_mock_page_puts_the_order_in_the_queue(
    client: TestClient, gravados: PedidosEmMemoria, fiscal: FiscalEmMemoria
) -> None:
    """R3, RF-3.1 — o caminho inteiro: pagou, entrou na fila, ninguém emitiu ainda.

    Percorre a página de checkout do mock, que é o caminho default do quickstart
    (RNF-1, D-6 da S-04). O pedido começa em `aguardando_pagamento`, e é a
    confirmação que o move — não este teste.
    """
    gravados.gravados[PEDIDO_ID] = _pedido(StatusDoPedido.AGUARDANDO_PAGAMENTO)
    assert client.get("/operador/fila", headers=AUTORIZADO).json()["pendentes"] == []

    confirmou = client.post(f"/pagamento/mock/{PEDIDO_ID}/confirmar")

    assert confirmou.status_code == 200
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF
    fila: list[dict[str, Any]] = client.get("/operador/fila", headers=AUTORIZADO).json()[
        "pendentes"
    ]
    assert [pedido["pedido_id"] for pedido in fila] == [PEDIDO_ID]
    assert fiscal.notas == {}, "o pagamento não emite nada; ele só põe na fila"


# ------------------------------------------------- os documentos, para o cliente


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_the_documents_do_not_exist_before_the_operator_approves(client: TestClient) -> None:
    """R3, RF-3.5 — não há DANFE nem XML de uma nota que não saiu.

    Um 404 e não um 409: de fora, "este pedido não existe" e "a nota dele ainda não
    saiu" têm que ser a mesma resposta. As rotas são abertas por link, e distinguir
    os dois casos transformaria a rota num oráculo que diz quais ids de pedido
    existem.
    """
    for caminho in (f"/pedidos/{PEDIDO_ID}/nota.pdf", f"/pedidos/{PEDIDO_ID}/nota.xml"):
        assert client.get(caminho).status_code == 404

    assert client.get("/pedidos/nao-existe/nota.pdf").status_code == 404


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_after_approval_the_customer_can_fetch_the_danfe_and_the_xml(
    client: TestClient,
) -> None:
    """R3, RF-3.6, REQ-6 — os dois artefatos ficam disponíveis, e são os de verdade.

    O XML parseia e o PDF abre; a tarja está nos dois. É o que separa "a rota
    responde 200" de "o contador da empresa compradora consegue usar o arquivo" — a
    mesma diferença que a D-6 da S-04 nomeou no link de pagamento que terminava em
    404.
    """
    aprovado = client.post(
        f"/operador/pedidos/{PEDIDO_ID}/aprovar",
        json={"operador": OPERADOR},
        headers=AUTORIZADO,
    ).json()

    pdf = client.get(f"/pedidos/{PEDIDO_ID}/nota.pdf")
    xml = client.get(f"/pedidos/{PEDIDO_ID}/nota.xml")

    assert pdf.status_code == xml.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert xml.headers["content-type"] == "application/xml"
    assert pdf.content.startswith(b"%PDF-")
    assert xml.text.startswith("<?xml")
    assert TARJA in xml.text
    assert TARJA.encode() in pdf.content
    # É a nota DESTE pedido, e não uma qualquer: a chave que a decisão anunciou é a
    # que está dentro do XML.
    assert aprovado["chave_da_nota"] in xml.text


@pytest.mark.risco("R3")
@pytest.mark.usefixtures("com_token")
def test_a_rejected_order_never_produces_a_document(client: TestClient) -> None:
    """R3, `golden-011` — rejeitado é rejeitado: não há documento a servir."""
    client.post(
        f"/operador/pedidos/{PEDIDO_ID}/rejeitar",
        json={"operador": OPERADOR, "motivo": MOTIVO},
        headers=AUTORIZADO,
    )

    assert client.get(f"/pedidos/{PEDIDO_ID}/nota.pdf").status_code == 404
    assert client.get(f"/pedidos/{PEDIDO_ID}/nota.xml").status_code == 404
