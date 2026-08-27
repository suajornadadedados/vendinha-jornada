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
from vendinha.pagamento import MockPaymentAdapter
from vendinha.pedidos import PedidosEmMemoria, StatusDoPedido
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
def tools(seed: tuple[Produto, ...], gravados: PedidosEmMemoria) -> dict[str, BaseTool]:
    return {
        tool.name: tool
        for tool in ferramentas_de_checkout(
            CatalogoEmMemoria(seed), gravados, MockPaymentAdapter(BASE_URL), SEM_TIMEOUT
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
