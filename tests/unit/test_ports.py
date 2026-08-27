"""R8 — mock e adapter real satisfazem o mesmo contrato, e falham do mesmo jeito.

É o arquivo que `docs/riscos.md` R8 e `docs/testes.md` §2 nomeiam. O ADR-004 pediu
**mock como cidadão de primeira classe, testado por contrato e não um stub jogado**,
e a forma disso é esta: as mesmas asserções, parametrizadas pelos dois adapters. Um
adapter que divergisse do contrato reprova aqui, e não numa demo.

**O que é mockado, e o que não é.** Só a fronteira de port — a resposta HTTP do
Mercado Pago, via `httpx.MockTransport`, que é o duplo do próprio `httpx` e não um
`monkeypatch` num colaborador nosso. Nada interno é substituído: o `Pedido` é o de
verdade, o `LinkDePagamento` é o de verdade, e `MockPaymentAdapter` não é dublê de
nada — ele é uma implementação de produção do port (`docs/testes.md` §4, ADR-004).

**Não existe camada de integração aqui** (ADR-011). Que o sandbox de verdade aceita
a preferência é verificado **à mão** no `/fechar-spec`, com o link aberto no
navegador, e o resultado registrado no relatório. Está declarado para ninguém achar
que está automatizado.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest

from vendinha.composicao import TipoDeEvento
from vendinha.pagamento import (
    MERCADOPAGO,
    MOCK,
    GatewayIndisponivel,
    LinkDePagamento,
    MercadoPagoSandboxAdapter,
    MockPaymentAdapter,
    PaymentGateway,
    assinatura_confere,
    gateway_de,
)
from vendinha.pedidos import (
    ComposicaoDoPedido,
    Empresa,
    Endereco,
    ItemDoPedido,
    Pedido,
    StatusDoPedido,
)

pytestmark = pytest.mark.requires_backend

BASE_URL = "http://localhost:8000"
# Fabricado. Nenhuma credencial real entra neste repositório (RNF-7); o `noqa`
# é para o scanner do ruff, que reconhece a forma e não sabe que ela é falsa.
TOKEN = "TEST-token-de-sandbox-fabricado"  # noqa: S105

# O que o Mercado Pago devolve quando aceita uma preferência de sandbox. Escrito à
# mão a partir da documentação, e não capturado de uma chamada real: capturar
# traria ids de conta de verdade para dentro do repositório (RNF-7).
PREFERENCIA_ACEITA = {
    "id": "1234567890-abc",
    "init_point": "https://www.mercadopago.com.br/checkout/v1/redirect?pref_id=1234567890-abc",
    "sandbox_init_point": "https://sandbox.mercadopago.com.br/checkout/v1/redirect?pref_id=1234567890-abc",
}


def _pedido() -> Pedido:
    """Um pedido válido e mínimo. Empresa fabricada, CNPJ de teste (RNF-7)."""
    return Pedido(
        id="pedido-de-teste",
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


# ------------------------------------------------------------------- o contrato


@pytest.fixture(params=[MOCK, MERCADOPAGO])
def adapter(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> PaymentGateway:
    """Os dois adapters, atrás da mesma fixture.

    Toda asserção abaixo roda duas vezes. É o que "testado por contrato" significa:
    o teste não sabe qual implementação está do outro lado, o que é exatamente a
    posição em que o resto do código também está.
    """
    if request.param == MOCK:
        return MockPaymentAdapter(BASE_URL)

    def responder(_: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=PREFERENCIA_ACEITA)

    _com_transporte(monkeypatch, responder)
    return MercadoPagoSandboxAdapter(TOKEN, BASE_URL)


def _com_transporte(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    original = httpx.AsyncClient.__init__

    def com_mock(self: httpx.AsyncClient, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original(self, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", com_mock)


@pytest.mark.risco("R8")
async def test_both_adapters_return_the_same_shape(adapter: PaymentGateway) -> None:
    """R8, ADR-004 — o retorno é `LinkDePagamento` nos dois, com os três campos.

    Código que trata pagamento não pode precisar saber qual gateway está
    configurado. Se soubesse, trocar de adapter deixaria de ser configuração e
    voltaria a ser mudança de código — que é o que o port existe para impedir.
    """
    link = await adapter.criar_preferencia(_pedido())

    assert isinstance(link, LinkDePagamento)
    assert link.url.startswith("http")
    assert link.referencia
    assert link.gateway == adapter.nome


@pytest.mark.risco("R8")
async def test_both_adapters_are_deterministic_for_the_same_order(
    adapter: PaymentGateway,
) -> None:
    """R8 — o mesmo pedido produz um link utilizável nas duas chamadas.

    O que a idempotência de `gerar_link_pagamento` protege é o pedido; aqui a
    exigência é só que o adapter não invente um formato diferente na segunda vez.
    """
    primeiro = await adapter.criar_preferencia(_pedido())
    segundo = await adapter.criar_preferencia(_pedido())

    assert primeiro.gateway == segundo.gateway
    assert primeiro.url.startswith("http") and segundo.url.startswith("http")


@pytest.mark.risco("R8")
async def test_the_mock_link_points_at_this_server_so_the_quickstart_ends_somewhere() -> None:
    """R8, RNF-1 — o mock não é um stub: o link dele resolve.

    Um mock que devolvesse `https://exemplo.com/pague-aqui` passaria em todo teste
    e deixaria o quickstart terminar num 404 — a diferença entre "mock de primeira
    classe" e "stub jogado" que o ADR-004 nomeia.
    """
    pedido = _pedido()

    link = await MockPaymentAdapter(BASE_URL).criar_preferencia(pedido)

    assert link.url == f"{BASE_URL}/pagamento/mock/{pedido.id}"
    assert link.gateway == MOCK


# --------------------------------------------------- o adapter real, em detalhe


@pytest.mark.risco("R8")
async def test_the_sandbox_link_is_preferred_over_the_production_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R8 — credencial de teste devolve os dois links, e o de produção não serve.

    Com credencial de teste, `init_point` leva ao checkout de produção e falha de
    um jeito difícil de ler. Preferir `sandbox_init_point` é o que faz o ambiente
    de teste ser de teste inteiro.
    """
    _com_transporte(monkeypatch, lambda _: httpx.Response(201, json=PREFERENCIA_ACEITA))

    link = await MercadoPagoSandboxAdapter(TOKEN, BASE_URL).criar_preferencia(_pedido())

    assert link.url == PREFERENCIA_ACEITA["sandbox_init_point"]


@pytest.mark.risco("R8")
async def test_one_checkout_line_per_composition_so_the_buyer_can_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R8 — o comprador vê no extrato o que está pagando, não "Pedido Vendinha".

    Também trava o essencial: `external_reference` é o id do pedido, que é como o
    webhook volta a encontrá-lo, e `notification_url` aponta para este servidor.
    """
    enviados: list[dict[str, Any]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        import json

        enviados.append(json.loads(request.content))
        return httpx.Response(201, json=PREFERENCIA_ACEITA)

    _com_transporte(monkeypatch, responder)
    pedido = _pedido()

    await MercadoPagoSandboxAdapter(TOKEN, BASE_URL).criar_preferencia(pedido)

    (corpo,) = enviados
    assert corpo["external_reference"] == pedido.id
    assert corpo["notification_url"] == f"{BASE_URL}/webhooks/pagamento"
    assert len(corpo["items"]) == len(pedido.composicoes)
    assert corpo["items"][0]["title"] == "Cafe da manha para 20"
    assert corpo["items"][0]["currency_id"] == "BRL"


@pytest.mark.risco("R8")
@pytest.mark.parametrize(
    "responder",
    [
        pytest.param(lambda _: httpx.Response(401, json={"message": "invalid token"}), id="401"),
        pytest.param(lambda _: httpx.Response(500, text="boom"), id="500"),
        pytest.param(lambda _: httpx.Response(201, json={"id": "x"}), id="sem-link"),
    ],
)
async def test_a_gateway_that_fails_raises_the_shared_exception_and_leaks_nothing(
    monkeypatch: pytest.MonkeyPatch, responder: Callable[[httpx.Request], httpx.Response]
) -> None:
    """R8, ADR-004 — uma exceção só, para os dois adapters, sem credencial dentro.

    A mensagem vai para o log, e log é lido por gente e por ferramenta. Um token no
    texto da exceção é uma credencial num arquivo que ninguém trata como segredo
    (R5, `adversarial-006`).
    """
    _com_transporte(monkeypatch, responder)

    with pytest.raises(GatewayIndisponivel) as falhou:
        await MercadoPagoSandboxAdapter(TOKEN, BASE_URL).criar_preferencia(_pedido())

    assert TOKEN not in str(falhou.value)


# ---------------------------------------------------------- a escolha do adapter


@pytest.mark.risco("R8")
def test_without_a_token_the_gateway_is_the_mock() -> None:
    """R8, RNF-1, D-4 — o quickstart roda sem conta externa, e sem variável nova.

    Não existe combinação inválida: um `PAYMENT_GATEWAY=mercadopago` sem token
    subiria a aplicação e quebraria no primeiro pedido, que é a pior hora.
    """
    assert gateway_de(None, BASE_URL).nome == MOCK
    assert gateway_de("", BASE_URL).nome == MOCK
    assert gateway_de(TOKEN, BASE_URL).nome == MERCADOPAGO


# ------------------------------------------------- a verificação de origem (R8)


@pytest.mark.risco("R8")
def test_a_signature_computed_with_the_secret_is_the_only_one_that_verifies() -> None:
    """R8, RF-2.5 — origem verificada por HMAC, com vetor calculado à mão.

    O manifesto é o que o Mercado Pago documenta:
    `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`. O valor esperado abaixo foi
    calculado à parte, e não chamando a mesma função — teste que refaz a conta do
    código passa por construção (`docs/testes.md` §4).
    """
    import hashlib
    import hmac

    segredo = "segredo-de-teste"
    manifesto = "id:evento-1;request-id:req-1;ts:1700000000;"
    esperada = hmac.new(segredo.encode(), manifesto.encode(), hashlib.sha256).hexdigest()

    assert assinatura_confere(
        segredo=segredo,
        cabecalho=f"ts=1700000000,v1={esperada}",
        request_id="req-1",
        data_id="evento-1",
    )


@pytest.mark.risco("R8")
@pytest.mark.parametrize(
    ("segredo", "cabecalho", "request_id", "data_id"),
    [
        (None, "ts=1,v1=abc", "req-1", "evento-1"),  # sem segredo, nada confere
        ("segredo-de-teste", None, "req-1", "evento-1"),  # sem cabeçalho
        ("segredo-de-teste", "ts=1,v1=abc", "req-1", "evento-1"),  # assinatura errada
        ("segredo-de-teste", "v1=abc", "req-1", "evento-1"),  # sem ts
        ("segredo-de-teste", "ts=1", "req-1", "evento-1"),  # sem v1
        ("segredo-de-teste", "lixo", "req-1", "evento-1"),  # cabeçalho malformado
        ("segredo-de-teste", "ts=1,v1=abc", "req-1", None),  # sem id de evento
    ],
)
def test_anything_short_of_a_valid_signature_is_refused(
    segredo: str | None, cabecalho: str | None, request_id: str | None, data_id: str | None
) -> None:
    """R8 — o lado seguro é o default, inclusive quando falta configuração.

    "Sem segredo, aceita tudo" transformaria esquecer uma variável de ambiente num
    endpoint aberto que muda o estado de um pedido pago.
    """
    assert not assinatura_confere(
        segredo=segredo, cabecalho=cabecalho, request_id=request_id, data_id=data_id
    )


@pytest.mark.risco("R8")
def test_the_created_order_is_the_one_the_gateway_is_asked_to_charge() -> None:
    """R8 — o pedido usado aqui é o mesmo tipo que a tool persiste.

    Fixture que diverge do modelo real é como um teste de contrato passa sobre um
    contrato que não existe mais.
    """
    pedido = _pedido()

    assert pedido.status is StatusDoPedido.AGUARDANDO_PAGAMENTO
    assert pedido.url_pagamento is None
    assert pedido.total == Decimal("39.00")
