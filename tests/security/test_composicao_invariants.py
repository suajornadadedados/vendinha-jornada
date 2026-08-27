"""R10 — não existe caminho até um pedido persistido com composição inválida.

`docs/testes.md` §2 diz que a R10 **nasce em `unit` e migra para `security`**, e este
é o arquivo do segundo endereço. A S-11 provou que o validador recusa
(`tests/unit/test_composicao.py`); o que faltava era o que só passa a existir quando
existe escrita: que a recusa não pode ser contornada.

**A pergunta aqui é sobre ausência.** Toda asserção termina em
`pedidos.gravados == {}` — não na mensagem de erro, não no motivo devolvido. Uma
recusa bem redigida que gravasse o pedido passaria num teste sobre texto e é
exatamente a falha que este arquivo existe para pegar.

**O cenário é o do BDD da spec, ao pé da letra.** A composição passa por
`validar_composicao` de verdade e é **aprovada**; então um item é trocado no caminho,
e `criar_pedido` recebe a versão adulterada. O ponto não é que o modelo seja
malicioso — é que entre um veredito e a chamada seguinte existe um caminho, e a
RF-2.7 diz que a validação que passou por ele nunca é a que autoriza.

Repare no que **não** é preciso mockar: nada. `CatalogoEmMemoria` e
`PedidosEmMemoria` são implementações de verdade das portas, e o motor de composição
é o mesmo do produto. Mock só na fronteira de port (ADR-004) — e aqui nem isso é
preciso.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from vendinha.catalogo import CatalogoEmMemoria, Produto, carregar_seed
from vendinha.composicao import Motivo, TipoDeEvento
from vendinha.pagamento import MockPaymentAdapter
from vendinha.pedidos import PedidosEmMemoria
from vendinha.tools.checkout import ComposicaoProposta, ferramentas_de_checkout
from vendinha.tools.composicao import ferramentas_de_composicao

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0
BASE_URL = "http://localhost:8000"

# Um café da manhã que passa: os quatro slots preenchidos, R$ 237,00 para 20 pessoas
# (R$ 11,85 por cabeça), nenhum item indisponível.
APROVADA = ComposicaoProposta(
    tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
    pessoas=20,
    produto_ids=[
        "cafe-moido-tradicional",
        "requeijao-de-corte",
        "doce-de-leite-cremoso",
        "pao-de-queijo-congelado",
    ],
    orcamento_por_pessoa=Decimal("15.00"),
)


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture
def gravados() -> PedidosEmMemoria:
    return PedidosEmMemoria()


@pytest.fixture
def criar_pedido(seed: tuple[Produto, ...], gravados: PedidosEmMemoria) -> BaseTool:
    return next(
        tool
        for tool in ferramentas_de_checkout(
            CatalogoEmMemoria(seed), gravados, MockPaymentAdapter(BASE_URL), SEM_TIMEOUT
        )
        if tool.name == "criar_pedido"
    )


@pytest.fixture
def validar_composicao(seed: tuple[Produto, ...]) -> BaseTool:
    (tool,) = ferramentas_de_composicao(CatalogoEmMemoria(seed), SEM_TIMEOUT)
    return tool


async def _validar(tool: BaseTool, proposta: ComposicaoProposta) -> dict[str, Any]:
    resposta: dict[str, Any] = json.loads(
        await tool.ainvoke(
            {
                "tipo_de_evento": proposta.tipo_de_evento,
                "pessoas": proposta.pessoas,
                "produto_ids": proposta.produto_ids,
                "orcamento_por_pessoa": proposta.orcamento_por_pessoa,
                "restricoes": proposta.restricoes,
            }
        )
    )
    return resposta


def _indisponivel(seed: tuple[Produto, ...]) -> str:
    """Um produto que a loja não tem. O seed mantém alguns fora do ar de propósito."""
    return next(produto.id for produto in seed if not produto.disponivel)


# ------------------------------------------------ o cenário do BDD, ao pé da letra


@pytest.mark.risco("R10")
async def test_a_composition_altered_after_approval_never_reaches_the_database(
    validar_composicao: BaseTool,
    criar_pedido: BaseTool,
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Any,
) -> None:
    """R10, RF-2.7 — a validação que passou pelo modelo não é a que autoriza.

    A composição é aprovada de verdade, e só então um item é trocado por um mais
    caro. O veredito anterior continua na conversa, correto e irrelevante:
    `criar_pedido` não o consulta, revalida do zero contra o catálogo, e recusa.
    """
    antes = await _validar(validar_composicao, APROVADA)
    assert antes["encontrados"][0]["aprovada"] is True

    adulterada = APROVADA.model_copy(
        update={
            "produto_ids": [
                "cafe-moido-tradicional",
                "queijo-canastra-meia-cura",  # R$ 89,90 no lugar de R$ 44,00
                "doce-de-leite-cremoso",
                "pao-de-queijo-congelado",
            ]
        }
    )

    resposta = await chamar(criar_pedido, empresa=empresa_valida, composicoes=[adulterada])

    assert gravados.gravados == {}
    (veredito,) = resposta["encontrados"]
    assert veredito["aprovada"] is False
    assert {p["motivo"] for p in veredito["problemas_composicao"]} == {Motivo.ORCAMENTO.value}


@pytest.mark.risco("R10")
@pytest.mark.parametrize("motivo", [Motivo.RESTRICAO, Motivo.SLOT, Motivo.DISPONIBILIDADE])
async def test_every_reason_the_validator_refuses_also_stops_the_write(
    criar_pedido: BaseTool,
    gravados: PedidosEmMemoria,
    seed: tuple[Produto, ...],
    empresa_valida: dict[str, Any],
    chamar: Any,
    motivo: Motivo,
) -> None:
    """R10 — nenhum motivo de recusa tem caminho até o banco.

    Parametrizado pelos motivos do enum, e não por um caso escolhido a dedo: um
    motivo novo em `composicao.Motivo` sem entrada aqui é uma lacuna que aparece
    na revisão do diff, e não um teste que continua verde sobre um conjunto menor.

    A restrição alimentar é a que mais importa: violá-la não é recomendação ruim,
    é alguém passar mal (R10, ADR-013).
    """
    adulteradas = {
        # `pao-de-queijo-congelado` declara ovos — o corte é o campo `contem` lido
        # do catálogo, nunca o nome nem a descrição.
        Motivo.RESTRICAO: APROVADA.model_copy(update={"restricoes": ["ovos"]}),
        # Café da manhã exige petisco; sem ele a recusa é falta de item, não preço.
        Motivo.SLOT: APROVADA.model_copy(update={"produto_ids": APROVADA.produto_ids[:3]}),
        Motivo.DISPONIBILIDADE: APROVADA.model_copy(
            update={
                "produto_ids": [*APROVADA.produto_ids, _indisponivel(seed)],
                "orcamento_por_pessoa": None,
            }
        ),
    }
    proposta = adulteradas[motivo]

    resposta = await chamar(criar_pedido, empresa=empresa_valida, composicoes=[proposta])

    assert gravados.gravados == {}
    (veredito,) = resposta["encontrados"]
    assert veredito["aprovada"] is False
    assert motivo.value in {p["motivo"] for p in veredito["problemas_composicao"]}


@pytest.mark.risco("R10")
async def test_one_bad_composition_takes_the_whole_order_down(
    criar_pedido: BaseTool,
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Any,
) -> None:
    """R10, RF-2.3 — "12 cestas, 2 sem álcool" é um pedido, não dois.

    Gravar a composição boa e recusar a ruim entregaria metade de um evento que
    ninguém pediu — e o cliente descobriria na entrega. A recusa devolve as duas,
    aprovada e reprovada, para o modelo saber qual quebrou.
    """
    ruim = APROVADA.model_copy(update={"restricoes": ["lactose"]})

    resposta = await chamar(criar_pedido, empresa=empresa_valida, composicoes=[APROVADA, ruim])

    assert gravados.gravados == {}
    aprovadas = [c["aprovada"] for c in resposta["encontrados"]]
    assert aprovadas == [True, False]


# ------------------------------------------------------- o que o schema não aceita


@pytest.mark.risco("R10")
def test_the_tool_has_no_argument_through_which_a_price_or_a_quantity_could_arrive() -> None:
    """R10, R1, RF-1.6 — a revalidação não tem como ser enganada pelo argumento.

    Esta é a metade estrutural do invariante, e é a mais forte: não existe recusa a
    escrever porque não existe campo por onde um preço, uma quantidade ou um total
    entrem. O veredito é montado sobre `Produto` lido do catálogo, e mais nada.

    Um campo `preco` aqui — mesmo "só para conferência" — devolveria ao modelo a
    aritmética que o ADR-013 tirou dele, e faria o veredito carimbar a alucinação
    em vez de pegá-la.
    """
    campos = set(ComposicaoProposta.model_fields)

    assert campos == {
        "tipo_de_evento",
        "pessoas",
        "produto_ids",
        "orcamento_por_pessoa",
        "restricoes",
    }
    assert not {c for c in campos if "preco" in c or "total" in c or "quantidade" in c}


@pytest.mark.risco("R10")
async def test_an_order_with_no_composition_is_refused_by_the_contract(
    criar_pedido: BaseTool, gravados: PedidosEmMemoria, empresa_valida: dict[str, Any]
) -> None:
    """R10 — pedido sem composição custa R$ 0,00, e R$ 0,00 cabe em qualquer teto.

    É a mesma recusa que `composicao._vazia` já fazia um andar acima, aqui feita
    pelo contrato: `min_length=1`. Sem ela, a composição vazia seria a resposta
    ótima para todo orçamento apertado, apresentada como aprovada.
    """
    with pytest.raises(Exception, match="composicoes"):
        await criar_pedido.ainvoke({"empresa": empresa_valida, "composicoes": []})

    assert gravados.gravados == {}


# ---------------------------------------------------------- a fonte dos números


@pytest.mark.risco("R10")
async def test_the_revalidation_reads_todays_catalogue_not_the_one_the_verdict_saw(
    seed: tuple[Produto, ...],
    gravados: PedidosEmMemoria,
    empresa_valida: dict[str, Any],
    chamar: Any,
) -> None:
    """R10, R1 — o preço que autoriza é o do banco no momento de gravar.

    O catálogo muda entre um veredito e a chamada seguinte — `make seed` roda, um
    produto sai do ar. Se `criar_pedido` confiasse no que o modelo carregou da
    conversa, ele gravaria um pedido pelo preço de ontem. Aqui o preço sobe e a
    composição que estava dentro do teto passa a estourá-lo.
    """
    mais_caro = tuple(
        produto.model_copy(update={"preco": Decimal("120.00")})
        if produto.id == "requeijao-de-corte"
        else produto
        for produto in seed
    )
    tool = next(
        t
        for t in ferramentas_de_checkout(
            CatalogoEmMemoria(mais_caro), gravados, MockPaymentAdapter(BASE_URL), SEM_TIMEOUT
        )
        if t.name == "criar_pedido"
    )

    resposta = await chamar(tool, empresa=empresa_valida, composicoes=[APROVADA])

    assert gravados.gravados == {}
    assert resposta["encontrados"][0]["aprovada"] is False
