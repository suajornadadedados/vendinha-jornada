"""R1 — o total de um pedido sai do banco e do código, nunca do texto do modelo.

É a metade da linha R1 de `docs/riscos.md` que a S-04 fecha. A outra — *nenhum fato
chega ao cliente sem ter vindo de tool* — é da S-03, e nenhuma das duas sozinha
fecha o risco.

**Os valores esperados foram lidos do seed e escritos à mão aqui.** Não são
recalculados chamando `composicao.validar`: teste que refaz a mesma conta que o
código faz passa por construção e nunca discorda dele (`docs/testes.md` §4). Se
alguém mudar um preço em `data/catalogo/`, este arquivo tem que ser atualizado por
uma pessoa — e é esse o ponto.

    cafe-moido-tradicional     R$ 39,00   rende 40
    requeijao-de-corte         R$ 44,00   rende 14
    doce-de-leite-cremoso      R$ 32,00   rende 15
    pao-de-queijo-congelado    R$ 46,00   rende 20
    queijo-canastra-meia-cura  R$ 89,90   rende 14
    torresmo-de-rolo           R$ 38,00   rende 10
"""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from vendinha.catalogo import CatalogoEmMemoria, Produto, carregar_seed
from vendinha.composicao import TipoDeEvento
from vendinha.pagamento import MockPaymentAdapter
from vendinha.pedidos import PedidosEmMemoria
from vendinha.tools.checkout import ComposicaoProposta, EmpresaEntrada, ferramentas_de_checkout

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0
BASE_URL = "http://localhost:8000"

# Café da manhã para 20 pessoas. Quantidade = teto de 20 dividido pelo rendimento.
#   café     40 rende -> 1 x 39,00 =  39,00
#   requeijão 14 rende -> 2 x 44,00 =  88,00
#   doce      15 rende -> 2 x 32,00 =  64,00
#   pão       20 rende -> 1 x 46,00 =  46,00
CAFE_DA_MANHA = (
    "cafe-moido-tradicional",
    "requeijao-de-corte",
    "doce-de-leite-cremoso",
    "pao-de-queijo-congelado",
)
TOTAL_DO_CAFE = Decimal("237.00")
POR_PESSOA_DO_CAFE = Decimal("11.85")

# Duas cestas de fim de ano sem álcool. Três tipos distintos, um de cada.
#   queijo   14 rende -> 1 x 89,90 = 89,90
#   doce     15 rende -> 1 x 32,00 = 32,00
#   torresmo 10 rende -> 1 x 38,00 = 38,00
CESTA_SEM_ALCOOL = ("queijo-canastra-meia-cura", "doce-de-leite-cremoso", "torresmo-de-rolo")
TOTAL_DA_CESTA = Decimal("159.90")

TOTAL_DO_PEDIDO = Decimal("396.90")


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture
def gravados() -> PedidosEmMemoria:
    return PedidosEmMemoria()


def _criar_pedido(seed: tuple[Produto, ...], pedidos: PedidosEmMemoria) -> BaseTool:
    tools = {
        tool.name: tool
        for tool in ferramentas_de_checkout(
            CatalogoEmMemoria(seed), pedidos, MockPaymentAdapter(BASE_URL), SEM_TIMEOUT
        )
    }
    return tools["criar_pedido"]


Chamar = Callable[..., Awaitable[dict[str, Any]]]


@pytest.mark.risco("R1")
async def test_the_order_total_is_the_sum_the_code_computed_from_catalogue_prices(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.3 — total e valor por pessoa vêm do banco, e são `Decimal`.

    O número esperado está no topo deste arquivo, derivado do seed à mão. O que
    este teste recusa é a única alternativa: um total que o modelo escreveu.
    """
    resposta = await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                produto_ids=list(CAFE_DA_MANHA),
            )
        ],
    )

    pedido = resposta["encontrados"][0]
    assert Decimal(pedido["total_pedido"]) == TOTAL_DO_CAFE
    assert Decimal(pedido["composicoes"][0]["total_composicao"]) == TOTAL_DO_CAFE
    assert Decimal(pedido["composicoes"][0]["valor_por_pessoa"]) == POR_PESSOA_DO_CAFE


@pytest.mark.risco("R1")
async def test_money_survives_the_round_trip_as_decimal_never_as_float(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1 — o dinheiro persistido é `Decimal` do começo ao fim.

    `89.90` que passe por `float` em qualquer ponto volta como
    `89.90000000000000568...`, e a diferença aparece no total de um pedido de doze
    cestas (`docs/testes.md` §4).
    """
    await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CESTA_DE_FIM_DE_ANO,
                pessoas=2,
                produto_ids=list(CESTA_SEM_ALCOOL),
            )
        ],
    )

    (pedido,) = gravados.gravados.values()
    assert isinstance(pedido.total, Decimal)
    assert pedido.total == TOTAL_DA_CESTA
    for item in pedido.composicoes[0].itens:
        assert isinstance(item.preco_unitario, Decimal)
        assert isinstance(item.subtotal, Decimal)


@pytest.mark.risco("R1")
async def test_two_compositions_in_one_order_sum_into_one_total(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.3 — "12 cestas, 2 sem álcool" é um pedido com duas composições.

    O total do pedido é a soma dos totais que o código calculou para cada uma —
    não um número escrito na resposta, e não a média entre elas (`golden-015`).
    """
    resposta = await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                produto_ids=list(CAFE_DA_MANHA),
            ),
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CESTA_DE_FIM_DE_ANO,
                pessoas=2,
                produto_ids=list(CESTA_SEM_ALCOOL),
                restricoes=["alcool"],
            ),
        ],
    )

    pedido = resposta["encontrados"][0]
    assert Decimal(pedido["total_pedido"]) == TOTAL_DO_PEDIDO

    (gravado,) = gravados.gravados.values()
    assert [c.total for c in gravado.composicoes] == [TOTAL_DO_CAFE, TOTAL_DA_CESTA]
    assert gravado.total == TOTAL_DO_PEDIDO


@pytest.mark.risco("R1")
async def test_the_persisted_price_is_frozen_at_creation_not_a_reference(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1 — o pedido guarda o preço que valia, não um ponteiro para o catálogo.

    Um pedido que consultasse `produto.preco` mudaria de valor sozinho no próximo
    `make seed`: o cliente teria pago um número e a nota sairia com outro.
    """
    await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                produto_ids=list(CAFE_DA_MANHA),
            )
        ],
    )

    (pedido,) = gravados.gravados.values()
    cafe = next(i for i in pedido.composicoes[0].itens if i.produto_id == "cafe-moido-tradicional")
    assert cafe.preco_unitario == Decimal("39.00")
    assert cafe.quantidade == 1
    assert cafe.subtotal == Decimal("39.00")


@pytest.mark.risco("R1")
def test_the_empresa_entry_model_is_what_the_model_fills_not_what_the_code_accepts(
    empresa_valida: dict[str, Any],
) -> None:
    """R1, RF-2.2 — os dois schemas são distintos de propósito.

    `EmpresaEntrada` aceita qualquer string, porque é o que o modelo transcreve do
    que o cliente falou. `pedidos.Empresa` é o que o código aceita, e é lá que o
    CNPJ tem que fechar. Fossem o mesmo, um dígito errado viraria exceção na
    fronteira da tool em vez de uma frase que o agente transforma em pergunta.
    """
    entrada = EmpresaEntrada.model_validate({**empresa_valida, "cnpj": "11.222.333/0001-99"})

    assert entrada.cnpj == "11.222.333/0001-99"


@pytest.mark.risco("R1")
async def test_every_field_of_the_persisted_line_is_the_one_the_invoice_will_read(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R1, RF-2.3 — a linha gravada é o insumo da DANFE, e ela é afirmada campo a campo.

    Ressalva A-1 da verificação independente: cinco quebras em `_para_o_banco` —
    `quantidade`, `subtotal`, `nome`, `rendimento` e `restricoes` — deixavam a suíte
    inteira verde. Dos sete campos que a função projeta do veredito para o banco, só
    `preco_unitario` era realmente afirmado.

    **O item escolhido tem quantidade 2, e essa é a correção que importa.** O teste
    anterior tocava a quantidade persistida num item cuja quantidade real é 1 — o
    valor esperado coincidia com o valor neutro da mutação, e `docs/testes.md` §4 é
    literal: *"valor esperado vem de fonte independente"*. Com `== 1` não há como
    distinguir o valor certo do degenerado.

    Os números vêm do seed, à mão, como o resto deste arquivo:
    requeijão de corte mineiro, R$ 44,00, rende 14 → para 20 pessoas são 2 unidades
    e R$ 88,00 de subtotal.
    """
    await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                produto_ids=list(CAFE_DA_MANHA),
            )
        ],
    )

    (pedido,) = gravados.gravados.values()
    (composicao,) = pedido.composicoes
    linha = next(i for i in composicao.itens if i.produto_id == "requeijao-de-corte")

    assert linha.quantidade == 2, "quantidade é obrigação declarada do REQ-3"
    assert linha.subtotal == Decimal("88.00")
    assert linha.preco_unitario == Decimal("44.00")
    assert linha.nome == "Requeijão de corte mineiro"
    assert linha.tipo == "queijo"
    assert linha.rendimento == 14
    # Uma linha internamente incoerente — "1 unidade a R$ 44,00, subtotal R$ 88,00" —
    # é uma nota fiscal errada que nenhum campo isolado denuncia.
    assert linha.preco_unitario * linha.quantidade == linha.subtotal


@pytest.mark.risco("R10")
async def test_the_declared_restriction_is_persisted_with_its_composition(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Chamar,
) -> None:
    """R10, RF-2.3 — sem `restricoes` no banco, o subgrupo depende de interpretação.

    É o pior dos cinco campos que a ressalva A-1 encontrou desprotegidos. *"12 cestas,
    2 sem álcool"* vira duas composições indistinguíveis a não ser pela lista de itens,
    e a RF-2.3 existe justamente para que o subgrupo **não** seja uma leitura de quem
    olha depois. Quem lê depois é a S-05, montando a nota.
    """
    await chamar(
        _criar_pedido(seed, gravados),
        empresa=empresa_valida,
        composicoes=[
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
                pessoas=20,
                produto_ids=list(CAFE_DA_MANHA),
            ),
            ComposicaoProposta(
                tipo_de_evento=TipoDeEvento.CESTA_DE_FIM_DE_ANO,
                pessoas=2,
                produto_ids=list(CESTA_SEM_ALCOOL),
                restricoes=["alcool"],
            ),
        ],
    )

    (pedido,) = gravados.gravados.values()
    com_alcool, sem_alcool = pedido.composicoes

    assert com_alcool.restricoes == ()
    assert sem_alcool.restricoes == ("alcool",)
    assert sem_alcool.pessoas == 2
