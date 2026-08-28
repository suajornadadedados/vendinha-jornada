"""R1 — quem decide se um dado é válido é o schema, e a recusa é legível pelo modelo.

O `golden-008` é o caso deste arquivo, e ele tem duas armadilhas: o dígito errado,
em que um modelo prestativo "conserta" o documento, e o *"põe qualquer um aí que
depois eu corrijo"*, que pede para gravar lixo num campo que sai impresso numa nota.
As duas são recusadas aqui, em código, e nenhuma das recusas depende de o prompt ter
pedido com educação (RF-2.2, RF-3.4).

A revalidação da composição — o REQ-7 — não está neste arquivo. Ela é invariante de
fronteira e mora em `tests/security/test_composicao_invariants.py`: a pergunta lá não
é *"a função recusa?"*, é *"existe caminho até um pedido persistido inválido?"*
(`docs/testes.md` §1, ADR-011).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from vendinha.catalogo import CatalogoEmMemoria, Produto, carregar_seed
from vendinha.composicao import TipoDeEvento
from vendinha.documentos import cnpj_valido, formatar_cnpj, mascarar_cnpj, normalizar_cnpj
from vendinha.fiscal import Aprovacao, Decisao, FiscalEmMemoria, StatusDaNota, emitir
from vendinha.nota import MockNFAdapter
from vendinha.pagamento import (
    GatewayIndisponivel,
    LinkDePagamento,
    MockPaymentAdapter,
    Pagamento,
)
from vendinha.pedidos import Pedido, PedidosEmMemoria, StatusDoPedido
from vendinha.tools.checkout import ComposicaoProposta, ferramentas_de_checkout

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0
BASE_URL = "http://localhost:8000"

CAFE_DA_MANHA = ComposicaoProposta(
    tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
    pessoas=20,
    produto_ids=[
        "cafe-moido-tradicional",
        "requeijao-de-corte",
        "doce-de-leite-cremoso",
        "pao-de-queijo-congelado",
    ],
)

Chamar = Callable[..., Awaitable[dict[str, Any]]]


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture
def gravados() -> PedidosEmMemoria:
    return PedidosEmMemoria()


@pytest.fixture
def fiscal() -> FiscalEmMemoria:
    return FiscalEmMemoria()


@pytest.fixture
def tools(
    seed: tuple[Produto, ...], gravados: PedidosEmMemoria, fiscal: FiscalEmMemoria
) -> dict[str, BaseTool]:
    return {
        tool.name: tool
        for tool in ferramentas_de_checkout(
            CatalogoEmMemoria(seed),
            gravados,
            MockPaymentAdapter(BASE_URL),
            SEM_TIMEOUT,
            fiscal,
            BASE_URL,
        )
    }


# ------------------------------------------------------------------- o documento


@pytest.mark.risco("R1")
@pytest.mark.parametrize(
    ("documento", "valido"),
    [
        ("11.222.333/0001-81", True),  # o do golden-003: dígitos fecham, empresa não existe
        ("11222333000181", True),  # o mesmo documento, sem pontuação
        ("11.222.333/0001-99", False),  # o do golden-008: dígito verificador errado
        ("11.222.333/0001-8", False),  # curto
        ("11111111111111", False),  # o que sai de um "põe qualquer um aí"
        ("00000000000000", False),
        ("", False),
        ("nao sei de cabeca", False),
    ],
)
def test_the_check_digits_decide_what_a_valid_cnpj_is(documento: str, valido: bool) -> None:
    """R1, RF-2.2 — a validação é o algoritmo, não a opinião do modelo.

    Os dígitos repetidos estão na lista de propósito: eles passam no módulo 11 por
    acidente aritmético, e são exatamente o número que um placeholder produz.
    """
    assert cnpj_valido(documento) is valido


@pytest.mark.risco("R5")
def test_a_document_that_leaves_the_code_leaves_masked() -> None:
    """R5, ADR-007 — o retorno de tool não é lugar de CNPJ em claro.

    O retorno vira trace, e o trace sai da infra desde o ADR-010. Mais perto ainda:
    é de onde o modelo copia números para a resposta, e `golden-003` reprova a
    execução que repete o documento.
    """
    assert mascarar_cnpj("11.222.333/0001-81") == "**.***.***/0001-81"
    assert mascarar_cnpj("nao e um cnpj") == "[CNPJ]"
    assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
    assert normalizar_cnpj("11.222.333/0001-81") == "11222333000181"


# ------------------------------------------------------- validar_dados_cliente


@pytest.mark.risco("R1")
async def test_valid_company_data_comes_back_confirmed_and_never_in_the_clear(
    tools: dict[str, BaseTool], empresa_valida: dict[str, Any], chamar: Chamar
) -> None:
    """R1, R5, RF-2.2 — `cnpj_valido` é o fato ancorado do `golden-008`."""
    resposta = await chamar(tools["validar_dados_cliente"], empresa=empresa_valida)

    (veredito,) = resposta["encontrados"]
    assert veredito["cnpj_valido"] is True
    assert veredito["dados_completos"] is True
    assert veredito["cnpj"] == "**.***.***/0001-81"
    assert "11222333000181" not in str(resposta)
    assert "11.222.333/0001-81" not in str(resposta)


@pytest.mark.risco("R1")
@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("cnpj", "11.222.333/0001-99"),
        ("cnpj", "11111111111111"),
        ("contato_email", "marta arroba exemplo"),
        ("razao_social", ""),
    ],
)
async def test_bad_company_data_is_refused_with_a_reason_the_agent_can_relay(
    tools: dict[str, BaseTool],
    empresa_valida: dict[str, Any],
    chamar: Chamar,
    campo: str,
    valor: str,
) -> None:
    """R1, RF-2.2 — a recusa volta como dado, não como exceção.

    Como exceção, o modelo receberia uma mensagem técnica e o caminho de conserto —
    perguntar de novo ao cliente — ficaria fora do alcance dele. E `adversarial-006`
    reprova a execução que deixa vazar mensagem de erro interna.

    A asserção é sobre `dados_completos`, e não sobre `cnpj_valido`: um e-mail
    malformado não torna o CNPJ inválido. Confundir os dois fazia o agente dizer ao
    cliente que o documento dele não conferia por causa de outro campo.
    """
    resposta = await chamar(
        tools["validar_dados_cliente"], empresa={**empresa_valida, campo: valor}
    )

    (veredito,) = resposta["encontrados"]
    assert veredito["dados_completos"] is False
    assert veredito["cnpj_valido"] is (campo != "cnpj")
    assert veredito["problemas"], "a recusa tem que dizer o que está errado"
    assert "provisório" in resposta["observacao"]


@pytest.mark.risco("R1")
@pytest.mark.parametrize(
    ("campo", "valor"), [("uf", "MJ"), ("cep", "3014"), ("cidade", ""), ("logradouro", "")]
)
async def test_an_incomplete_delivery_address_is_refused(
    tools: dict[str, BaseTool],
    empresa_valida: dict[str, Any],
    chamar: Chamar,
    campo: str,
    valor: str,
) -> None:
    """R1, RF-2.2 — endereço é campo da DANFE modelo 55, não detalhe de cadastro.

    O B2C não coletava endereço nenhum, e o ADR-013 registra isso como furo que o
    pivô fechou. UF inexistente e CEP curto produzem uma nota que a transportadora
    não consegue usar.
    """
    empresa = {**empresa_valida, "endereco": {**empresa_valida["endereco"], campo: valor}}

    resposta = await chamar(tools["validar_dados_cliente"], empresa=empresa)

    (veredito,) = resposta["encontrados"]
    assert veredito["dados_completos"] is False


# ------------------------------------------------------------------ criar_pedido


@pytest.mark.risco("R1")
async def test_no_order_is_created_when_the_company_data_does_not_validate(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.2 — a composição pode estar perfeita; sem dado válido não há pedido.

    É o *"poe qualquer um ai que depois eu corrijo"* do `golden-008`: não existe
    "depois eu corrijo" quando o dado atravessa uma emissão.
    """
    resposta = await chamar(
        tools["criar_pedido"],
        empresa={**empresa_valida, "cnpj": "11111111111111"},
        composicoes=[CAFE_DA_MANHA],
    )

    assert gravados.gravados == {}
    assert resposta["encontrados"][0]["cnpj_valido"] is False
    assert "nenhum pedido foi criado" in resposta["observacao"]


@pytest.mark.risco("R1")
async def test_an_unknown_product_id_creates_nothing_and_says_which(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1 — id inexistente não vira um pedido menor.

    Gravar a parte que existe devolveria um total exato para uma composição que
    ninguém pediu, e o modelo leria isso como sucesso — a mesma decisão que
    `validar_composicao` já tinha tomado na S-11.
    """
    proposta = CAFE_DA_MANHA.model_copy(
        update={"produto_ids": [*CAFE_DA_MANHA.produto_ids, "queijo-que-nao-existe"]}
    )

    resposta = await chamar(tools["criar_pedido"], empresa=empresa_valida, composicoes=[proposta])

    assert gravados.gravados == {}
    assert resposta["nao_encontrados"] == ["queijo-que-nao-existe"]


@pytest.mark.risco("R1")
async def test_the_created_order_starts_waiting_for_payment_and_has_no_link_yet(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.4 — criar o pedido não cobra ninguém; o link é o passo seguinte."""
    resposta = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )

    (pedido,) = resposta["encontrados"]
    assert pedido["status_pedido"] == StatusDoPedido.AGUARDANDO_PAGAMENTO.value
    assert "url_pagamento" not in pedido
    assert gravados.gravados[pedido["pedido_id"]].url_pagamento is None


# --------------------------------------------------------------- consultar_pedido


@pytest.mark.risco("R1")
async def test_the_agent_answers_about_an_order_by_reading_it(
    tools: dict[str, BaseTool],
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.5 — `status_pedido` é o fato ancorado do `golden-010`.

    "Pode ficar tranquilo, não houve cobrança dupla" sem consulta é fato inventado
    com cara de gentileza, e do outro lado tem um financeiro conferindo extrato.
    """
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    pedido_id = criado["encontrados"][0]["pedido_id"]

    lido = await chamar(tools["consultar_pedido"], pedido_id=pedido_id)

    assert lido["encontrados"][0]["pedido_id"] == pedido_id
    assert lido["encontrados"][0]["status_pedido"] == StatusDoPedido.AGUARDANDO_PAGAMENTO.value
    assert lido["encontrados"][0]["cnpj"] == "**.***.***/0001-81"


@pytest.mark.risco("R1")
async def test_an_unknown_order_id_is_an_absence_the_agent_has_to_handle(
    tools: dict[str, BaseTool], chamar: Chamar
) -> None:
    """R1 — id que não existe volta em `nao_encontrados`, não como lista vazia."""
    resposta = await chamar(tools["consultar_pedido"], pedido_id="nao-existe")

    assert resposta["nao_encontrados"] == ["nao-existe"]
    assert "encontrados" not in resposta or resposta["encontrados"] == []


# ------------------------------------------------------------------ a persistência


@pytest.mark.risco("R8")
async def test_the_same_payment_event_only_produces_an_effect_once(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R8, RF-2.5 — a idempotência é da porta, e o webhook só a usa.

    Aqui se prova a metade de baixo: `registrar_pagamento` responde `True` uma vez
    e `False` para o mesmo evento, e o estado não anda duas vezes. A rota que a
    chama é da task 6.
    """
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    pedido_id = criado["encontrados"][0]["pedido_id"]

    assert await gravados.registrar_pagamento(pedido_id, "evento-1") is True
    assert gravados.gravados[pedido_id].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF

    assert await gravados.registrar_pagamento(pedido_id, "evento-1") is False
    assert gravados.gravados[pedido_id].status is StatusDoPedido.AGUARDANDO_APROVACAO_NF


@pytest.mark.risco("R1")
async def test_partial_company_data_is_accepted_by_the_tool_and_refused_by_the_code(
    tools: dict[str, BaseTool], chamar: Chamar
) -> None:
    """R1, RF-2.2 — quem decide se o cadastro está completo é o código, não o modelo.

    O schema de entrada aceita a empresa pela metade **de propósito**. Com os campos
    obrigatórios, o agente não conseguia chamar a tool antes de ter tudo — então
    coletava em prosa e decidia sozinho quando o cadastro estava completo, que é
    exatamente o julgamento que esta tool existe para tirar dele. A recusa nomeia
    campo a campo, para o agente saber o que pedir.
    """
    resposta = await chamar(
        tools["validar_dados_cliente"],
        empresa={"razao_social": "Aurora Servicos Digitais LTDA", "cnpj": "11.222.333/0001-81"},
    )

    (veredito,) = resposta["encontrados"]
    assert veredito["dados_completos"] is False
    # E o documento continua válido: cadastro incompleto não torna um CNPJ errado.
    assert veredito["cnpj_valido"] is True
    assert "contato_email: ainda não informado pelo cliente" in veredito["problemas"]
    assert "endereco.cep: ainda não informado pelo cliente" in veredito["problemas"]
    # Faltar não é o mesmo que estar errado, e a mensagem tem que diferenciar: um é
    # pedido ao cliente, o outro é recusa.
    assert not any("não fecham" in problema for problema in veredito["problemas"])


@pytest.mark.risco("R1")
async def test_a_missing_field_and_an_invalid_one_are_different_problems(
    tools: dict[str, BaseTool], empresa_valida: dict[str, Any], chamar: Chamar
) -> None:
    """R1 — CNPJ com dígito errado é recusa; CEP ausente é pedido.

    Um agente que recebe as duas com a mesma cara trata as duas do mesmo jeito — e
    aí ou ele pede um documento que o cliente já deu, ou aceita um que não fecha.
    """
    resposta = await chamar(
        tools["validar_dados_cliente"],
        empresa={**empresa_valida, "cnpj": "11.222.333/0001-99"},
    )

    (veredito,) = resposta["encontrados"]
    assert veredito["cnpj_valido"] is False
    assert any("dígitos verificadores" in problema for problema in veredito["problemas"])
    assert not any("ainda não informado" in problema for problema in veredito["problemas"])


class GatewayQueContaChamadas:
    """Um gateway que devolve um link DIFERENTE a cada chamada.

    Ressalva A-2 da verificação independente. O `MockPaymentAdapter` deriva a URL do
    id do pedido, então com ele a segunda chamada devolve a mesma string de qualquer
    jeito — a quebra da idempotência é **invisível por construção**. Com o adapter do
    Mercado Pago, um segundo `POST /checkout/preferences` é um segundo link vivo, e é
    esse cenário que este duplo reproduz.
    """

    nome = "conta-chamadas"

    def __init__(self) -> None:
        self.chamadas = 0

    async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento:
        self.chamadas += 1
        return LinkDePagamento(
            url=f"https://sandbox.exemplo/checkout/{pedido.id}/{self.chamadas}",
            referencia=f"pref-{self.chamadas}",
            gateway=self.nome,
        )

    async def consultar_pagamento(self, referencia: str) -> Pagamento:
        raise AssertionError(f"não deveria consultar pagamento aqui: {referencia}")


@pytest.mark.risco("R8")
async def test_asking_for_the_payment_link_twice_never_opens_a_second_one(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R8, RF-2.4 — dois links vivos para um pedido é uma conciliação quebrada.

    O cliente paga um e o financeiro dele vê o outro em aberto. A invariante estava
    escrita no docstring do módulo, na `description` que o **modelo lê** — *"chamar
    duas vezes para o mesmo pedido devolve o MESMO link"* — e em lugar nenhum da
    suíte: a falsificação M23 desligava a guarda e nada ficava vermelho.
    """
    gateway = GatewayQueContaChamadas()
    tools = {
        tool.name: tool
        for tool in ferramentas_de_checkout(CatalogoEmMemoria(seed), gravados, gateway, SEM_TIMEOUT)
    }
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    pedido_id = criado["encontrados"][0]["pedido_id"]

    primeiro = await chamar(tools["gerar_link_pagamento"], pedido_id=pedido_id)
    segundo = await chamar(tools["gerar_link_pagamento"], pedido_id=pedido_id)

    assert gateway.chamadas == 1, "a segunda chamada abriu uma segunda preferência no gateway"
    assert primeiro["encontrados"][0]["url_pagamento"] == segundo["encontrados"][0]["url_pagamento"]
    assert gravados.gravados[pedido_id].url_pagamento == primeiro["encontrados"][0]["url_pagamento"]


@pytest.mark.risco("R8")
async def test_a_gateway_that_is_down_leaves_the_order_valid_and_asks_for_a_retry(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R8, ADR-004 — degradação graciosa: o pedido está gravado, falta o link.

    O que não pode acontecer é o cliente receber traceback, nome de fornecedor ou
    código de status (`adversarial-006`) — nem o pedido ser perdido, porque ele
    continua válido e o que falta é uma segunda tentativa.
    """

    class ForaDoAr:
        nome = "fora-do-ar"

        async def criar_preferencia(self, pedido: Pedido) -> LinkDePagamento:
            del pedido
            raise GatewayIndisponivel("o Mercado Pago não respondeu como esperado: ReadTimeout")

        async def consultar_pagamento(self, referencia: str) -> Pagamento:
            raise AssertionError(referencia)

    tools = {
        tool.name: tool
        for tool in ferramentas_de_checkout(
            CatalogoEmMemoria(seed), gravados, ForaDoAr(), SEM_TIMEOUT
        )
    }
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    pedido_id = criado["encontrados"][0]["pedido_id"]

    resposta = await chamar(tools["gerar_link_pagamento"], pedido_id=pedido_id)

    assert gravados.gravados[pedido_id].url_pagamento is None
    assert "tente de novo" in resposta["observacao"]
    assert "Mercado Pago" not in str(resposta)
    assert "ReadTimeout" not in str(resposta)


# ---------------------------------------------- a nota, do jeito que o cliente lê
#
# O chat é puxado: o servidor não empurra mensagem. Então "o cliente recebe a
# confirmação no chat com acesso à DANFE/XML" (REQ-6, RF-3.6) acontece quando ele
# pergunta e o agente **consulta** — e é por isso que `golden-011` ancora
# `motivo_rejeicao` e `golden-012` pede o XML, os dois em `tool:consultar_pedido`.
#
# Nenhum destes campos é opinião do modelo, e é isso que estes testes afirmam.


async def _pedido_pago(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> str:
    """Um pedido criado pelo agente e levado até `aguardando_aprovacao_nf`.

    Pelo caminho de produção: `criar_pedido` e depois `registrar_pagamento`, que é o
    que o webhook chama. Escrever o status à mão faria o teste medir um estado que
    o sistema pode nunca produzir.
    """
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    pedido_id: str = criado["encontrados"][0]["pedido_id"]
    await gravados.registrar_pagamento(pedido_id, "evento-de-teste")
    return pedido_id


@pytest.mark.risco("R3")
async def test_before_payment_the_invoice_is_not_pending_it_is_not_applicable(
    tools: dict[str, BaseTool], empresa_valida: dict[str, Any], chamar: Chamar
) -> None:
    """RF-3.1 — a nota só entra na fila depois do pagamento confirmado.

    A diferença entre `nao_aplicavel` e `aguardando_aprovacao` é o que separa "ainda
    não começou" de "está em conferência". Dizer a segunda antes do pagamento
    prometeria ao cliente uma etapa que nem existe ainda.
    """
    criado = await chamar(
        tools["criar_pedido"], empresa=empresa_valida, composicoes=[CAFE_DA_MANHA]
    )
    lido = await chamar(tools["consultar_pedido"], pedido_id=criado["encontrados"][0]["pedido_id"])

    resumo = lido["encontrados"][0]
    assert resumo["status_nf"] == StatusDaNota.NAO_APLICAVEL.value
    assert "numero_nota" not in resumo
    assert "url_danfe" not in resumo


@pytest.mark.risco("R3")
async def test_a_paid_order_reports_the_invoice_as_awaiting_a_person(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R3, RF-3.1 — pago, a nota fica em conferência, e não há link para oferecer.

    A ausência das URLs importa tanto quanto a presença do status: um link de DANFE
    antes da emissão daria ao modelo um fato para repetir e ao cliente um endereço
    que responde 404 — a mesma falha que a D-6 da S-04 corrigiu no pagamento.
    """
    pedido_id = await _pedido_pago(tools, gravados, empresa_valida, chamar)

    resumo = (await chamar(tools["consultar_pedido"], pedido_id=pedido_id))["encontrados"][0]

    assert resumo["status_pedido"] == StatusDoPedido.AGUARDANDO_APROVACAO_NF.value
    assert resumo["status_nf"] == StatusDaNota.AGUARDANDO_APROVACAO.value
    assert "url_danfe" not in resumo
    assert "url_xml" not in resumo


@pytest.mark.risco("R3")
async def test_after_the_invoice_is_issued_the_agent_can_hand_over_both_documents(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    fiscal: FiscalEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R3, RF-3.6, REQ-6, `golden-012` — o número e os dois links saem por tool.

    O contador da empresa compradora é destinatário real do XML, e é ele que o
    `golden-012` tem em mente. O número da nota vem de `numero_nota`, que a régua de
    groundedness passou a reconhecer nesta spec: um número de nota fiscal afirmado
    sem retorno de tool é fato inventado com consequência fiscal.
    """
    pedido_id = await _pedido_pago(tools, gravados, empresa_valida, chamar)
    await fiscal.registrar_decisao(
        Aprovacao(pedido_id=pedido_id, decisao=Decisao.APROVADA, operador="ana.souza")
    )
    emitida = await emitir(pedido_id, pedidos=gravados, fiscal=fiscal, emissor=MockNFAdapter())

    resumo = (await chamar(tools["consultar_pedido"], pedido_id=pedido_id))["encontrados"][0]

    assert resumo["status_nf"] == StatusDaNota.EMITIDA.value
    assert resumo["numero_nota"] == emitida.nota.numero
    assert resumo["url_danfe"] == f"{BASE_URL}/pedidos/{pedido_id}/nota.pdf"
    assert resumo["url_xml"] == f"{BASE_URL}/pedidos/{pedido_id}/nota.xml"
    # E nenhum motivo de rejeição pendurado num pedido que foi aprovado.
    assert "motivo_rejeicao" not in resumo


@pytest.mark.risco("R3")
async def test_a_rejected_invoice_gives_the_agent_the_reason_to_relay(
    tools: dict[str, BaseTool],
    gravados: PedidosEmMemoria,
    fiscal: FiscalEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """RF-4.2, `golden-011` — o motivo chega ao cliente pelo mesmo caminho de sempre.

    *"Registrar a rejeição com quem, quando e motivo"* é da API do operador; o que
    este teste fecha é a outra metade — *"comunicar ao cliente o motivo em linguagem
    útil, pedindo o dado que falta"*. Sem o motivo aqui, a rejeição viraria silêncio
    para quem pagou, e a única saída do agente seria inventar uma explicação.
    """
    motivo = "inscricao estadual da empresa nao confere com o CNPJ informado"
    pedido_id = await _pedido_pago(tools, gravados, empresa_valida, chamar)
    await fiscal.registrar_decisao(
        Aprovacao(
            pedido_id=pedido_id,
            decisao=Decisao.REJEITADA,
            operador="ana.souza",
            motivo=motivo,
        )
    )
    await gravados.registrar_rejeicao(pedido_id)

    resumo = (await chamar(tools["consultar_pedido"], pedido_id=pedido_id))["encontrados"][0]

    assert resumo["status_nf"] == StatusDaNota.REJEITADA.value
    assert resumo["motivo_rejeicao"] == motivo
    assert "numero_nota" not in resumo
    assert "url_danfe" not in resumo
