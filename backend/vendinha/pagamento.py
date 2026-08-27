"""A porta de pagamento e os dois adapters — ADR-004, e o R8 inteiro.

O ADR-004 pediu **mock como cidadão de primeira classe**, testado por contrato e
não um stub jogado num `if`. O que isso significa aqui, concretamente:

- os dois adapters implementam o **mesmo** `PaymentGateway`, devolvem o **mesmo**
  `LinkDePagamento` e falham com a **mesma** exceção (`GatewayIndisponivel`);
- `tests/unit/test_ports.py` roda as mesmas asserções contra os dois, então um
  adapter que divergisse do contrato reprovaria antes de chegar numa demo;
- trocar de adapter não é mudar código.

**Como se troca, e por que não há variável nova.** Sem `MERCADOPAGO_ACCESS_TOKEN`,
o gateway é o mock. Com token, é o sandbox. Uma `PAYMENT_GATEWAY=mock|mercadopago`
seria simétrica ao `NF_EMITTER` e foi recusada por criar um estado impossível de
diagnosticar — `PAYMENT_GATEWAY=mercadopago` sem token —, em que a aplicação sobe
e só quebra no primeiro pedido. Aqui não existe combinação inválida. Em troca, a
escolha é implícita, e o preço disso é pago no log de subida: `gateway_de` diz em
voz alta qual adapter está valendo (S-04, D-4).

**Sandbox, sempre.** Credencial de produção não entra neste projeto — é requisito
do enunciado, e está no `.env.example`.

**A verificação de origem do webhook mora aqui, e não na rota.** É criptografia
sobre bytes, sem I/O e sem FastAPI: dá para testá-la com vetores fixos, que é o
único jeito honesto de testar um HMAC. A rota só pergunta "confere?" (RF-2.5, R8).
"""

import hashlib
import hmac
import logging
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from vendinha.pedidos import Pedido

logger = logging.getLogger(__name__)

MOCK = "mock"
MERCADOPAGO = "mercadopago"

PREFERENCIAS = "https://api.mercadopago.com/checkout/preferences"
PAGAMENTOS = "https://api.mercadopago.com/v1/payments"

# Um pedido tem um cliente esperando a resposta do outro lado. Mais generoso que o
# teto de tool porque um gateway lento não é um gateway travado — e menos generoso
# que "sem limite", que é como uma conversa fica pendurada para sempre.
TIMEOUT_SEGUNDOS = 15.0


class GatewayIndisponivel(RuntimeError):
    """O gateway não respondeu, ou respondeu o que não dá para usar.

    Uma exceção só para os dois adapters é parte do contrato: código que trata
    falha de pagamento não pode precisar saber qual gateway está configurado
    (ADR-004, R8).
    """


class LinkDePagamento(BaseModel):
    """O que qualquer gateway devolve. Nada específico de fornecedor aqui."""

    model_config = ConfigDict(frozen=True)

    url: str
    referencia: str
    gateway: str


class Pagamento(BaseModel):
    """O que o gateway diz sobre um pagamento — e a única fonte de "foi pago".

    O webhook chega dizendo *"olhe o pagamento 123"*, e não *"o pedido X foi
    pago"*. Marcar o pedido como pago porque um POST chegou seria confiar no
    mensageiro; quem afirma é o gateway, consultado por referência. É a regra de
    ouro aplicada ao dinheiro: o código decide o que pode ser feito.
    """

    model_config = ConfigDict(frozen=True)

    pedido_id: str
    aprovado: bool
    referencia: str


class PaymentGateway(Protocol):
    """A porta. Duas operações: cobrar, e perguntar se foi pago."""

    nome: str

    async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento: ...

    async def consultar_pagamento(self, referencia: str) -> Pagamento: ...


class MockPaymentAdapter:
    """O gateway do quickstart — e o default (RNF-1).

    Não é um stub: ele devolve um link que **funciona**, apontando para a página de
    checkout falsa que o `app.py` serve quando este adapter está ativo. Um mock que
    devolvesse `https://exemplo.com/pague-aqui` passaria em todo teste e deixaria o
    quickstart terminar num 404 — que é a diferença entre "mock de primeira classe"
    e "stub jogado" que o ADR-004 nomeia.

    O link é derivado do id do pedido, então é reproduzível: rodar o mesmo cenário
    duas vezes dá o mesmo link, e o eval não fica dependendo de sorteio.
    """

    nome = MOCK

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento:
        return LinkDePagamento(
            url=f"{self._base}/pagamento/{MOCK}/{pedido.id}",
            referencia=f"{MOCK}-{pedido.id}",
            gateway=self.nome,
        )

    async def consultar_pagamento(self, referencia: str) -> Pagamento:
        """A referência do mock carrega o id do pedido, e é só isso que ele sabe.

        Um pagamento que o mock não reconhece não vira "aprovado por padrão": ele
        volta `aprovado=False`, e o pedido não anda. Mock que aprova o que não
        conhece é o stub que faz o teste passar e a demo mentir.
        """
        prefixo = f"{MOCK}-"
        if not referencia.startswith(prefixo) or not referencia[len(prefixo) :]:
            return Pagamento(pedido_id="", aprovado=False, referencia=referencia)
        return Pagamento(pedido_id=referencia[len(prefixo) :], aprovado=True, referencia=referencia)


class MercadoPagoSandboxAdapter:
    """O sandbox do Mercado Pago. Uma preferência de checkout por pedido.

    **Uma linha por composição, e não uma linha só com o total.** O comprador vê no
    checkout o que ele está pagando, e o extrato do financeiro dele também. Um item
    genérico "Pedido Vendinha" transformaria a conferência do outro lado num
    telefonema.

    **`sandbox_init_point` na frente do `init_point`.** As credenciais de teste
    devolvem os dois, e o segundo leva ao checkout de produção — que com credencial
    de teste falha de um jeito difícil de ler. Preferir o primeiro é o que faz o
    ambiente de teste ser de teste inteiro.
    """

    nome = MERCADOPAGO

    def __init__(self, access_token: str, base_url: str) -> None:
        self._token = access_token
        self._base = base_url.rstrip("/")

    async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento:
        corpo = {
            "external_reference": pedido.id,
            "notification_url": f"{self._base}/webhooks/pagamento",
            "items": [
                {
                    "id": f"{pedido.id}-{posicao}",
                    "title": _titulo(composicao.tipo_de_evento.value, composicao.pessoas),
                    "quantity": 1,
                    "unit_price": float(composicao.total),
                    "currency_id": "BRL",
                }
                for posicao, composicao in enumerate(pedido.composicoes)
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as client:
                resposta = await client.post(
                    PREFERENCIAS,
                    json=corpo,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                resposta.raise_for_status()
                dados = resposta.json()
        except httpx.HTTPError as falhou:
            # A mensagem não carrega o token nem o corpo: ela vai para o log, e o
            # log é lido por gente e por ferramenta (`adversarial-006`, R5).
            raise GatewayIndisponivel(
                f"o Mercado Pago não respondeu como esperado: {type(falhou).__name__}"
            ) from falhou

        url = dados.get("sandbox_init_point") or dados.get("init_point")
        if not url:
            raise GatewayIndisponivel(
                "o Mercado Pago respondeu sem link de checkout; a credencial é de sandbox?"
            )
        return LinkDePagamento(url=str(url), referencia=str(dados.get("id", "")), gateway=self.nome)

    async def consultar_pagamento(self, referencia: str) -> Pagamento:
        """Pergunta ao Mercado Pago o que aconteceu com aquele pagamento.

        `external_reference` volta com o id do pedido — é o campo que a preferência
        levou na ida, e o que fecha o círculo sem uma tabela de tradução nossa. Só
        `approved` conta: `pending` e `in_process` também geram notificação, e
        tratá-los como pago liberaria a nota antes de o dinheiro existir.
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as client:
                resposta = await client.get(
                    f"{PAGAMENTOS}/{referencia}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                resposta.raise_for_status()
                dados = resposta.json()
        except httpx.HTTPError as falhou:
            raise GatewayIndisponivel(
                f"não consegui consultar o pagamento no Mercado Pago: {type(falhou).__name__}"
            ) from falhou

        return Pagamento(
            pedido_id=str(dados.get("external_reference") or ""),
            aprovado=dados.get("status") == "approved",
            referencia=referencia,
        )


def _titulo(tipo_de_evento: str, pessoas: int) -> str:
    """`cafe_da_manha`, 20 → `Café da manhã para 20`. O que o comprador vê no extrato."""
    legivel = tipo_de_evento.replace("_", " ")
    return f"{legivel[:1].upper()}{legivel[1:]} para {pessoas}"


def gateway_de(access_token: str | None, base_url: str) -> PaymentGateway:
    """O adapter que vale nesta instância. Sem token, mock (D-4).

    O log não é decoração: a escolha é implícita — derivada da presença de uma
    credencial —, e uma escolha implícita que ninguém anuncia é a que produz o
    "por que o link é falso?" três semanas depois.
    """
    if access_token:
        logger.info("pagamento: adapter do Mercado Pago (sandbox)")
        return MercadoPagoSandboxAdapter(access_token, base_url)
    logger.info(
        "pagamento: adapter MOCK — MERCADOPAGO_ACCESS_TOKEN não está definida. "
        "Os links de pagamento são falsos e confirmáveis pela página local."
    )
    return MockPaymentAdapter(base_url)


def assinatura_confere(
    *, segredo: str | None, cabecalho: str | None, request_id: str | None, data_id: str | None
) -> bool:
    """O webhook veio mesmo do Mercado Pago? (RF-2.5, R8)

    O manifesto é o que a documentação do Mercado Pago define:
    `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`, com HMAC-SHA256 sobre a
    chave secreta. A comparação é `compare_digest` — comparar assinatura com `==`
    vaza o prefixo correto pelo tempo de resposta.

    **Sem segredo configurado, nada confere.** É deliberado e é o lado seguro: a
    alternativa — "sem segredo, aceita tudo" — transforma esquecer uma variável de
    ambiente em endpoint aberto que muda estado de pedido. Quem roda o quickstart
    não precisa do webhook do gateway; quem configura o gateway configura os dois.
    """
    if not segredo or not cabecalho or not data_id:
        return False

    partes = dict(pedaco.split("=", 1) for pedaco in cabecalho.split(",") if "=" in pedaco)
    ts = partes.get("ts", "").strip()
    recebida = partes.get("v1", "").strip()
    if not ts or not recebida:
        return False

    manifesto = f"id:{data_id};request-id:{request_id or ''};ts:{ts};"
    esperada = hmac.new(
        segredo.encode("utf-8"), manifesto.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, recebida)


__all__ = [
    "MERCADOPAGO",
    "MOCK",
    "GatewayIndisponivel",
    "LinkDePagamento",
    "MercadoPagoSandboxAdapter",
    "MockPaymentAdapter",
    "Pagamento",
    "PaymentGateway",
    "assinatura_confere",
    "gateway_de",
]
