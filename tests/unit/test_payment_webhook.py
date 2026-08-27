"""R8 — o webhook de pagamento: origem verificada, efeito uma vez só (RF-2.5).

Zero IA neste caminho, e é por isso que ele cabe inteiro em `unit`: são bytes,
HMAC e uma transação. O que a camada `security` responderia — *existe caminho até a
ação proibida?* — aqui não tem sujeito: o webhook não chama tool nenhuma, não fala
com o modelo e não decide nada sobre composição.

O que ele decide é sobre **dinheiro**, e as três asserções que importam são:

1. sem assinatura válida, 401 e nada acontece — inclusive sem segredo configurado;
2. o mesmo evento duas vezes produz um efeito só, e o segundo responde 200;
3. quem afirma que foi pago é o **gateway**, consultado por referência — nunca o
   corpo da requisição.

`docs/testes.md` §2 aponta a R8 para `test_ports.py`; este arquivo é a segunda
metade da mesma linha, e as duas tabelas normativas foram atualizadas para dizê-lo.
"""

import hashlib
import hmac
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
from vendinha.graph import build_graph
from vendinha.pagamento import GatewayIndisponivel, LinkDePagamento, Pagamento
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

SEGREDO = "segredo-de-webhook-de-teste"
PEDIDO_ID = "pedido-de-teste"
PAGAMENTO_ID = "1234567890"


def _pedido() -> Pedido:
    return Pedido(
        id=PEDIDO_ID,
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
                        nome="Café moído tradicional para coador",
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
    )


class GatewayDeTeste:
    """Um gateway com o contrato do port e um veredito escolhido pelo teste.

    Mock só na fronteira de port (ADR-004): o que se substitui é o que o Mercado
    Pago responderia, nunca um colaborador interno.
    """

    nome = "mercadopago"

    def __init__(self, *, aprovado: bool = True, fora_do_ar: bool = False) -> None:
        self._aprovado = aprovado
        self._fora_do_ar = fora_do_ar
        self.consultas: list[str] = []

    async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento:
        del pedido  # a referência do gateway é dele, não derivada do pedido
        return LinkDePagamento(
            url="https://sandbox.mercadopago.com.br/checkout",
            referencia=PAGAMENTO_ID,
            gateway=self.nome,
        )

    async def consultar_pagamento(self, referencia: str) -> Pagamento:
        self.consultas.append(referencia)
        if self._fora_do_ar:
            raise GatewayIndisponivel("indisponível")
        return Pagamento(pedido_id=PEDIDO_ID, aprovado=self._aprovado, referencia=referencia)


def _assinado(data_id: str = PAGAMENTO_ID, request_id: str = "req-1") -> dict[str, str]:
    """Os cabeçalhos que o Mercado Pago manda, com uma assinatura que fecha."""
    ts = "1700000000"
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(SEGREDO.encode(), manifesto.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


@pytest.fixture
def gravados() -> PedidosEmMemoria:
    pedidos = PedidosEmMemoria()
    pedidos.gravados[PEDIDO_ID] = _pedido()
    return pedidos


@pytest.fixture
def gateway() -> GatewayDeTeste:
    return GatewayDeTeste()


@pytest.fixture
def com_segredo(monkeypatch: pytest.MonkeyPatch) -> None:
    """O segredo do webhook, configurado como em produção.

    Via `Settings` e não por variável de ambiente porque `get_settings` é cacheado:
    mexer no ambiente depois do primeiro `import` não mudaria nada, e o teste
    passaria a medir o cache.
    """
    monkeypatch.setattr(get_settings(), "mercadopago_webhook_secret", SEGREDO)


@pytest.fixture
def sem_segredo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum segredo configurado — explicitamente, e não por acaso do ambiente.

    Sem esta fixture o teste da ausência dependeria de o `.env` da máquina não ter
    a variável, e passaria por acidente em quem nunca configurou o gateway.
    """
    monkeypatch.setattr(get_settings(), "mercadopago_webhook_secret", None)


def _client(gravados: PedidosEmMemoria, gateway: Any) -> TestClient:
    graph = build_graph(
        GenericFakeChatModel(messages=iter([AIMessage(content="oi")])),
        InMemorySaver(),
        registrar(RECOMENDACAO, PROMPT_RECOMENDACAO, []),
    )
    return TestClient(
        create_app(
            graph=graph,
            store=InMemoryConfigStore(),
            catalogo=CatalogoEmMemoria(carregar_seed(CATALOGO_DO_SEED)),
            pedidos=gravados,
            gateway=gateway,
        )
    )


@pytest.fixture
def client(gravados: PedidosEmMemoria, gateway: GatewayDeTeste) -> Iterator[TestClient]:
    with _client(gravados, gateway) as test_client:
        yield test_client


CORPO = {"type": "payment", "action": "payment.updated", "data": {"id": PAGAMENTO_ID}}


# --------------------------------------------------------------- a origem (R8)


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_notification_without_a_valid_signature_changes_nothing(
    client: TestClient, gravados: PedidosEmMemoria, gateway: GatewayDeTeste
) -> None:
    """R8, RF-2.5 — 401, e o pedido não anda.

    A asserção que importa é a segunda: recusar com o status certo e mesmo assim
    ter mexido no pedido seria a pior das duas falhas.
    """
    resposta = client.post(
        "/webhooks/pagamento",
        json=CORPO,
        headers={"x-signature": "ts=1,v1=deadbeef", "x-request-id": "req-1"},
    )

    assert resposta.status_code == 401
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO
    assert gateway.consultas == [], "o gateway nem devia ter sido consultado"


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("sem_segredo")
def test_with_no_secret_configured_no_signature_verifies(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R8 — sem segredo, o webhook recusa tudo. É o lado seguro, e é deliberado.

    A alternativa — "sem segredo, aceita" — transformaria esquecer uma variável de
    ambiente num endpoint aberto que muda o estado de um pedido pago. Note que a
    ausência é declarada pela fixture `sem_segredo`, e não herdada do `.env` da
    máquina — teste que passa por acaso do ambiente não prova nada.
    """
    resposta = client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert resposta.status_code == 401
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_signature_for_a_different_event_does_not_verify(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R8 — a assinatura cobre o id do evento: reusá-la em outro não vale.

    Sem isso, uma assinatura capturada de um evento legítimo autorizaria qualquer
    outro — é a diferença entre assinar a mensagem e assinar o remetente.
    """
    resposta = client.post(
        "/webhooks/pagamento",
        json={**CORPO, "data": {"id": "outro-pagamento"}},
        headers=_assinado(),
    )

    assert resposta.status_code == 401
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO


# ---------------------------------------------------------- a idempotência (R8)


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_the_same_event_twice_produces_one_effect(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R8, RF-2.5 — o cenário do BDD: evento duplicado não duplica efeito.

    O segundo responde **200**, e não um erro: gateway que recebe 4xx ou 5xx
    reenvia para sempre o evento que já teve efeito.
    """
    primeiro = client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())
    segundo = client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert primeiro.status_code == 200
    assert primeiro.json()["resultado"] == "registrado"
    assert segundo.status_code == 200
    assert segundo.json()["resultado"] == "duplicado"

    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF
    assert gravados.eventos == {PAGAMENTO_ID}


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_confirmed_payment_moves_the_order_to_the_operator_queue(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R8, RF-3.1 — o estado é `aguardando_aprovacao_nf`, que `golden-010` cita.

    É onde o pedido para: pago, e à espera da aprovação humana que a S-05 vai
    implementar. Emitir daqui seria pular o único ponto de HITL do produto.
    """
    client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF


# ------------------------------------------------- quem afirma que foi pago (R8)


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_pending_payment_is_acknowledged_and_ignored(
    gravados: PedidosEmMemoria,
) -> None:
    """R8 — `pending` e `in_process` também notificam, e não são pagamento.

    Tratá-los como pago liberaria a fila da nota antes de o dinheiro existir. O
    200 é para o gateway parar de reenviar um evento que foi processado — e
    "processado" aqui significa "olhado e descartado".
    """
    with _client(gravados, GatewayDeTeste(aprovado=False)) as client:
        resposta = client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "ignorado"
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_the_order_is_not_marked_paid_because_a_post_arrived(
    client: TestClient, gateway: GatewayDeTeste
) -> None:
    """R8 — a notificação diz "olhe o pagamento 123", não "o pedido X foi pago".

    O corpo do webhook nem carrega o id do pedido: quem o devolve é o gateway, e é
    ele quem afirma que houve aprovação. Confiar no corpo seria deixar o mensageiro
    decidir sobre dinheiro.
    """
    client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert gateway.consultas == [PAGAMENTO_ID]


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_gateway_that_is_down_asks_the_notification_to_come_back(
    gravados: PedidosEmMemoria,
) -> None:
    """R8, ADR-004 — 503, porque aqui o reenvio é exatamente o que queremos.

    Responder 200 sem ter conseguido consultar faria o gateway parar de tentar, e
    o pedido ficaria pago lá fora e pendente aqui — a divergência mais cara que
    este endpoint pode produzir.
    """
    with _client(gravados, GatewayDeTeste(fora_do_ar=True)) as client:
        resposta = client.post("/webhooks/pagamento", json=CORPO, headers=_assinado())

    assert resposta.status_code == 503
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_a_notification_that_is_not_about_a_payment_is_ignored(
    client: TestClient, gravados: PedidosEmMemoria, gateway: GatewayDeTeste
) -> None:
    """R8 — o Mercado Pago notifica outras coisas, e elas não movem pedido."""
    resposta = client.post(
        "/webhooks/pagamento",
        json={**CORPO, "type": "plan"},
        headers=_assinado(),
    )

    assert resposta.status_code == 200
    assert resposta.json()["resultado"] == "ignorado"
    assert gateway.consultas == []
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_PAGAMENTO


@pytest.mark.risco("R8")
@pytest.mark.usefixtures("com_segredo")
def test_an_unknown_field_in_the_notification_does_not_break_it(
    client: TestClient, gravados: PedidosEmMemoria
) -> None:
    """R8 — o gateway acrescenta campos com o tempo, e isso não pode custar dinheiro.

    Uma notificação recusada por um campo novo é um pagamento sem efeito por um
    motivo que nada tem a ver com pagamento.
    """
    resposta = client.post(
        "/webhooks/pagamento",
        json={**CORPO, "campo_que_nao_existia": 1, "live_mode": False},
        headers=_assinado(),
    )

    assert resposta.status_code == 200
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF


# ----------------------------------------------- a página de checkout do mock


@pytest.mark.risco("R8")
def test_the_mock_checkout_page_only_exists_when_the_mock_gateway_is_live(
    client: TestClient,
) -> None:
    """R8 — com gateway de verdade configurado, a página falsa não existe.

    Uma rota que confirma pagamento sem assinatura não pode estar de pé num
    ambiente com credencial real. A fixture `gateway` é o adapter do Mercado Pago,
    então aqui a resposta certa é 404.
    """
    assert client.get(f"/pagamento/mock/{PEDIDO_ID}").status_code == 404
    assert client.post(f"/pagamento/mock/{PEDIDO_ID}/confirmar").status_code == 404


@pytest.mark.risco("R8")
def test_the_mock_page_confirms_through_the_same_idempotent_path(
    gravados: PedidosEmMemoria,
) -> None:
    """R8, RNF-1 — o quickstart fecha o ciclo sem conta externa, e sem atalho.

    A confirmação do mock não passa pelo webhook (a assinatura exige um segredo que
    não pode ir para o navegador), mas chama a MESMA `registrar_pagamento`, com a
    MESMA idempotência. Muda quem avisa, nunca o que acontece.
    """
    from vendinha.pagamento import MockPaymentAdapter

    with _client(gravados, MockPaymentAdapter("http://localhost:8000")) as client:
        pagina = client.get(f"/pagamento/mock/{PEDIDO_ID}")
        primeiro = client.post(f"/pagamento/mock/{PEDIDO_ID}/confirmar")
        segundo = client.post(f"/pagamento/mock/{PEDIDO_ID}/confirmar")

    assert pagina.status_code == 200
    assert "SEM VALOR FINANCEIRO" in pagina.text
    # A página é aberta por link, sem autenticação: nada de PII nela (ADR-007, R5).
    assert "11.222.333" not in pagina.text
    assert "marta@exemplo.com.br" not in pagina.text

    assert primeiro.json()["resultado"] == "registrado"
    assert segundo.json()["resultado"] == "duplicado"
    assert gravados.gravados[PEDIDO_ID].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF
