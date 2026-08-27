"""R10 — `validar_composicao` relê do banco e devolve o veredito onde a régua o vê.

`test_composicao.py` prova as regras; este arquivo prova a **fronteira**: que a tool
não aceita fato vindo do modelo, que um id desconhecido não vira uma composição
menor, e que o veredito sai por dentro de `Resultado.encontrados` — que é o único
lugar em que o portão de groundedness procura (`evals/groundedness.py`).

Roda contra `CatalogoEmMemoria`, segunda implementação da porta, não mock
(`docs/testes.md` §4). Sem contêiner, sem chave de API, sem rede.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from vendinha.catalogo import CatalogoEmMemoria, Produto, carregar_seed
from vendinha.composicao import Motivo, TipoDeEvento
from vendinha.evals.groundedness import CAMPO_DA_TOOL, Chamada, Transcricao, precos_das_tools
from vendinha.tools.composicao import NOMES, ferramentas_de_composicao

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"

SEM_TIMEOUT = 30.0

CAFE_DA_MANHA = (
    "cafe-cerrado-torra-media",
    "queijo-minas-padrao",
    "doce-de-leite-cremoso",
    "biscoito-de-polvilho",
)


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture
def validar(seed: tuple[Produto, ...]) -> BaseTool:
    tools = ferramentas_de_composicao(CatalogoEmMemoria(seed), SEM_TIMEOUT)
    return {tool.name: tool for tool in tools}["validar_composicao"]


async def _chamar(tool: BaseTool, **kwargs: Any) -> dict[str, Any]:
    resposta: str = await tool.ainvoke(kwargs)
    decodificado: dict[str, Any] = json.loads(resposta)
    return decodificado


@pytest.mark.risco("R10")
def test_the_tool_is_the_name_the_eval_corpus_cites(validar: BaseTool) -> None:
    """R10 — os casos da S-11 listam `validar_composicao` em `tools.permitidas`.

    Renomear aqui reprovaria casos que não mudaram, por um motivo que nada no caso
    explica.
    """
    assert validar.name == "validar_composicao"
    assert NOMES == ("validar_composicao",)


@pytest.mark.risco("R10")
async def test_the_verdict_travels_inside_the_envelope_the_gate_reads(validar: BaseTool) -> None:
    """R10, R1 — total e valor por pessoa fora de `encontrados` seriam invisíveis.

    O portão de groundedness só olha `chamada.encontrados`. Um veredito num
    envelope próprio seria um número que o cliente ouve e a régua não confere —
    ancorado na aparência e sem origem no mecanismo.
    """
    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produto_ids=list(CAFE_DA_MANHA),
        orcamento_por_pessoa=Decimal("60.00"),
    )

    chamada = Chamada(tool="validar_composicao", retorno=resposta)
    assert len(chamada.encontrados) == 1
    veredito = chamada.encontrados[0]
    assert veredito["aprovada"] is True
    for campo in ("total_composicao", "valor_por_pessoa", "atende_pessoas"):
        assert veredito[campo] is not None


@pytest.mark.risco("R1")
async def test_every_money_the_verdict_returns_is_a_price_with_an_origin(
    validar: BaseTool,
) -> None:
    """R1, RF-1.3 — o que a tool devolve em dinheiro, a régua reconhece como devolvido.

    `_precos_divergentes` reprova todo valor citado que nenhuma tool tenha
    devolvido. O teto e o estouro são dinheiro e voltam no veredito: se a régua não
    os enxergasse, o agente reprovaria por repetir corretamente um número que a
    tool acabou de lhe dar — e uma régua que reprova o certo ensina a desconfiar
    dela.
    """
    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=25,
        produto_ids=["cafe-microlote-premiado", *CAFE_DA_MANHA[1:]],
        orcamento_por_pessoa=Decimal("30.00"),
    )
    veredito = resposta["encontrados"][0]

    devolvidos = precos_das_tools(
        Transcricao(respostas=(), chamadas=(Chamada(tool="validar_composicao", retorno=resposta),))
    )

    for campo in (
        "total_composicao",
        "valor_por_pessoa",
        "orcamento_por_pessoa",
        "excedente_por_pessoa",
    ):
        assert Decimal(veredito[campo]) in devolvidos, campo
    for linha in veredito["itens"]:
        assert Decimal(linha["preco_unitario"]) in devolvidos
        assert Decimal(linha["subtotal"]) in devolvidos


@pytest.mark.risco("R10")
def test_the_gate_knows_every_field_the_corpus_anchors_to_this_tool() -> None:
    """R10 — campo ancorado que o portão não traduz reprova por desconhecimento.

    `CAMPO_DESCONHECIDO` é um achado, então um caso que ancore
    `problemas_composicao` reprovaria antes mesmo de o portão olhar o retorno — e a
    mensagem culparia o caso, não a lacuna do mapa.
    """
    for campo in ("total_composicao", "valor_por_pessoa", "problemas_composicao"):
        assert campo in CAMPO_DA_TOOL


@pytest.mark.risco("R10")
async def test_an_unknown_id_validates_nothing_at_all(validar: BaseTool) -> None:
    """R10 — validar a parte que existe seria dar um total exato para outra cesta.

    O modelo leria o total como sucesso e apresentaria ao cliente uma composição
    que ele não montou. O id volta em `nao_encontrados`, que é uma afirmação, e
    nenhum veredito é emitido.
    """
    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produto_ids=[*CAFE_DA_MANHA, "queijo-que-nao-existe"],
    )

    assert resposta["nao_encontrados"] == ["queijo-que-nao-existe"]
    assert "encontrados" not in resposta or resposta["encontrados"] == []


@pytest.mark.risco("R1")
async def test_the_price_used_is_the_seeds_and_never_one_the_model_could_pass(
    validar: BaseTool, seed: tuple[Produto, ...]
) -> None:
    """R1 — a tool recebe ids, não payload: não há por onde injetar preço.

    Se preço, rendimento ou `contem` entrassem por argumento, o veredito passaria a
    carimbar a alucinação em vez de pegá-la. A prova é o schema: os únicos campos
    que ela aceita são o evento, as pessoas, os ids, o teto e as restrições.
    """
    assert validar.args_schema is not None
    aceitos = set(validar.args_schema.model_fields)  # type: ignore[union-attr]
    assert aceitos == {
        "tipo_de_evento",
        "pessoas",
        "produto_ids",
        "orcamento_por_pessoa",
        "restricoes",
    }

    por_id = {produto.id: produto for produto in seed}
    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produto_ids=list(CAFE_DA_MANHA),
    )

    for linha in resposta["encontrados"][0]["itens"]:
        assert Decimal(linha["preco_unitario"]) == por_id[linha["produto_id"]].preco


@pytest.mark.risco("R10")
async def test_a_restriction_declared_in_the_call_cuts_the_item(validar: BaseTool) -> None:
    """R10 — `contem` é corte, e o corte atravessa a tool até o modelo.

    É o cenário do `adversarial-007`: a broa de fubá declara glúten e nada no nome
    dela avisa. O veredito reprova nomeando o produto, para o modelo saber o que
    trocar em vez de tentar de novo às cegas.
    """
    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produto_ids=[*CAFE_DA_MANHA[:3], "broa-de-fuba-com-erva-doce"],
        restricoes=["gluten"],
    )
    veredito = resposta["encontrados"][0]

    assert veredito["aprovada"] is False
    violacao = [
        problema
        for problema in veredito["problemas_composicao"]
        if problema["motivo"] == Motivo.RESTRICAO.value
    ]
    assert [problema["produto_id"] for problema in violacao] == ["broa-de-fuba-com-erva-doce"]


@pytest.mark.risco("R10")
async def test_the_quantity_is_never_something_the_caller_gets_to_say(
    validar: BaseTool, seed: tuple[Produto, ...]
) -> None:
    """R1, RF-1.6 — quantidade sai do rendimento, e o schema não tem onde recebê-la.

    O café do Cerrado rende 20: para 40 pessoas são dois pacotes, e o número vem do
    seed atravessando a tool inteira sem passar pelo modelo.
    """
    por_id = {produto.id: produto for produto in seed}
    assert por_id["cafe-cerrado-torra-media"].rendimento == 20

    resposta = await _chamar(
        validar,
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS,
        pessoas=40,
        produto_ids=["cafe-cerrado-torra-media", "doce-de-leite-cremoso"],
    )

    linha = next(
        item
        for item in resposta["encontrados"][0]["itens"]
        if item["produto_id"] == "cafe-cerrado-torra-media"
    )
    assert linha["quantidade"] == 2
