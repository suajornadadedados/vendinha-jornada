"""R10 — o validador de composição recusa estouro, slot faltando e restrição violada.

`docs/testes.md` §2 põe o R10 aqui, na camada `unit`, e só na S-04 em
`security`. A razão está na §3.3: nesta spec ainda não existe `criar_pedido`, e um
teste de `security` afirmando *"nenhum pedido viola restrição declarada"* passaria
por **vacuidade** — não há caminho até pedido para ele observar. O que dá para
provar hoje é que o validador **recusa**, e é isso que este arquivo prova.

**Os valores esperados vêm do seed**, nunca de uma conta refeita aqui. Um teste que
recalcula a mesma soma que o código faz passa por construção e nunca discorda dele
(`docs/testes.md` §4). Onde precisamos de um total, ele é escrito à mão a partir do
preço que `data/catalogo/` declara.

As fixtures locais existem porque `tests/unit/conftest.py` ainda expõe `produto` e
`catalogo` num formato da S-00 (`sku`, `preco_unitario`) que nenhum teste atual usa
e que não é um `Produto`.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from vendinha.catalogo import Produto, carregar_seed
from vendinha.composicao import Motivo, TipoDeEvento, validar

pytestmark = pytest.mark.requires_backend

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"


@pytest.fixture(scope="module")
def seed() -> tuple[Produto, ...]:
    return carregar_seed(CATALOGO)


@pytest.fixture(scope="module")
def por_id(seed: tuple[Produto, ...]) -> dict[str, Produto]:
    return {produto.id: produto for produto in seed}


def _cafe_da_manha_completo(por_id: dict[str, Produto]) -> tuple[Produto, ...]:
    """Um item de cada slot do café da manhã, todos disponíveis e sem glúten."""
    return (
        por_id["cafe-cerrado-torra-media"],
        por_id["queijo-minas-padrao"],
        por_id["doce-de-leite-cremoso"],
        por_id["biscoito-de-polvilho"],
    )


@pytest.mark.risco("R10")
def test_a_composition_that_meets_every_slot_and_the_budget_is_approved(
    por_id: dict[str, Produto],
) -> None:
    """R10 — o caminho feliz existe, senão "recusa" não provaria nada.

    Sem este teste, um validador que reprovasse tudo passaria nos outros três.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produtos=_cafe_da_manha_completo(por_id),
        orcamento_por_pessoa=Decimal("60.00"),
    )

    assert veredito.aprovada
    assert veredito.problemas == ()


@pytest.mark.risco("R10")
def test_a_composition_over_the_budget_is_refused_and_says_by_how_much(
    por_id: dict[str, Produto],
) -> None:
    """R10, RF-1.7 — teto aprovado por um financeiro não é sugestão.

    É o cenário do `golden-007`: o modelo puxa o item caro, e o código recusa. O
    veredito precisa dizer **de quanto** foi o estouro, senão o modelo não tem o
    que corrigir e devolve o problema ao cliente como pedido de "esticar um
    pouquinho" — que é `nao_deve` naquele caso.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=25,
        produtos=(
            por_id["cafe-microlote-premiado"],
            por_id["queijo-canastra-premiado-mundial"],
            por_id["doce-de-leite-cremoso"],
            por_id["biscoito-de-polvilho"],
        ),
        orcamento_por_pessoa=Decimal("30.00"),
    )

    assert not veredito.aprovada
    estouro = [p for p in veredito.problemas if p.motivo is Motivo.ORCAMENTO]
    assert len(estouro) == 1
    assert veredito.excedente_por_pessoa is not None
    assert veredito.excedente_por_pessoa > 0
    assert str(veredito.excedente_por_pessoa) in estouro[0].mensagem


@pytest.mark.risco("R10")
def test_a_missing_slot_is_refused_as_a_slot_and_never_as_a_price(
    por_id: dict[str, Produto],
) -> None:
    """R10 — "café da manhã sem café é inválido" precisa ser executável.

    O `golden-014` é explícito: explicar a reprovação como se fosse questão de
    preço é `nao_deve`. O pedido do cliente é razoável — o escritório já tem
    máquina de café — e a composição reprova assim mesmo, dentro do orçamento.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produtos=(
            por_id["queijo-minas-padrao"],
            por_id["doce-de-leite-cremoso"],
            por_id["biscoito-de-polvilho"],
        ),
        orcamento_por_pessoa=Decimal("200.00"),
    )

    assert not veredito.aprovada
    assert [p.motivo for p in veredito.problemas] == [Motivo.SLOT]
    assert "bebida quente" in veredito.problemas[0].mensagem


@pytest.mark.risco("R10")
def test_a_declared_restriction_cuts_the_item_by_the_field_and_not_by_the_text(
    por_id: dict[str, Produto],
) -> None:
    """R10, RF-1.7 — o corte é `contem`, não o que a descrição do produto menciona.

    A broa de fubá é o item que o seed guarda para isto: ela declara glúten, e
    nada no nome dela avisa. O veredito nomeia o produto e a restrição — sem isso
    o modelo não sabe qual item trocar, e é o cenário do `adversarial-007`.
    """
    broa = por_id["broa-de-fuba-com-erva-doce"]
    assert "gluten" in broa.contem, "o seed mudou e este teste perdeu o objeto"
    assert "glúten" not in broa.descricao.lower(), "o corte tem que vir do campo"

    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=20,
        produtos=(
            por_id["cafe-cerrado-torra-media"],
            por_id["queijo-minas-padrao"],
            por_id["doce-de-leite-cremoso"],
            broa,
        ),
        orcamento_por_pessoa=Decimal("200.00"),
        restricoes=("gluten",),
    )

    assert not veredito.aprovada
    violacao = [p for p in veredito.problemas if p.motivo is Motivo.RESTRICAO]
    assert [p.produto_id for p in violacao] == [broa.id]
    assert "gluten" in violacao[0].mensagem


@pytest.mark.risco("R1")
def test_the_quantity_comes_from_the_declared_yield(por_id: dict[str, Produto]) -> None:
    """R1, RF-1.6 — quem divide "40 pessoas" pelo rendimento é o código.

    O café do Cerrado declara `rendimento: 20` no seed. Para 40 pessoas são dois
    pacotes; para 41, três — e a sobra é do código, não de um arredondamento que o
    modelo fez de cabeça.
    """
    cafe = por_id["cafe-cerrado-torra-media"]
    assert cafe.rendimento == 20, "o seed mudou e os números abaixo saíram do lugar"

    for pessoas, esperado in ((40, 2), (41, 3), (1, 1), (20, 1)):
        veredito = validar(
            tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS,
            pessoas=pessoas,
            produtos=(cafe, por_id["doce-de-leite-cremoso"]),
        )
        item = next(i for i in veredito.itens if i.produto_id == cafe.id)
        assert item.quantidade == esperado, f"{pessoas} pessoas"


@pytest.mark.risco("R1")
def test_the_total_is_decimal_and_agrees_with_the_seed(por_id: dict[str, Produto]) -> None:
    """R1 — dinheiro é `Decimal`, e o total esperado vem do seed, não da mesma soma.

    Para 40 pessoas: o café rende 20, então são 2 pacotes a R$42,00 = R$84,00; o
    doce rende 15, então são 3 potes a R$32,00 = R$96,00. Total R$180,00, R$4,50
    por pessoa. Os preços e os rendimentos estão em `data/catalogo/cafes.json` e
    `doces.json`; a conta está escrita aqui à mão.
    """
    cafe = por_id["cafe-cerrado-torra-media"]
    doce = por_id["doce-de-leite-cremoso"]
    assert (cafe.preco, cafe.rendimento) == (Decimal("42.00"), 20)
    assert (doce.preco, doce.rendimento) == (Decimal("32.00"), 15)

    veredito = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS, pessoas=40, produtos=(cafe, doce)
    )

    assert veredito.total == Decimal("180.00")
    assert isinstance(veredito.total, Decimal)
    assert veredito.valor_por_pessoa == Decimal("4.50")


@pytest.mark.risco("R10")
def test_the_per_person_value_never_rounds_down_into_the_budget(
    por_id: dict[str, Produto],
) -> None:
    """R10 — "arredondar o valor por pessoa para baixo para caber no teto" é `nao_deve`.

    Três pessoas levam um café de R$42,00 e um doce de R$32,00 — R$74,00, que dá
    R$24,666... por cabeça. O veredito diz R$24,67. Arredondar para baixo mostraria
    R$24,66 e faria a composição parecer mais barata do que ela é, que é exatamente
    a manobra que o `golden-007` proíbe.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS,
        pessoas=3,
        produtos=(por_id["cafe-cerrado-torra-media"], por_id["doce-de-leite-cremoso"]),
    )

    assert veredito.total == Decimal("74.00")
    assert veredito.valor_por_pessoa == Decimal("24.67")


@pytest.mark.risco("R10")
def test_how_many_people_the_composition_serves_is_the_binding_item(
    por_id: dict[str, Produto],
) -> None:
    """R10, REQ-4 — o veredito diz quantas pessoas a composição atende.

    Não é o número que o cliente pediu: é o do item que rende menos. Para 40
    pessoas, dois cafés de rendimento 20 cobrem 40 e um doce de rendimento 40
    cobre 40 — o menor deles é a resposta honesta.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS,
        pessoas=40,
        produtos=(por_id["cafe-cerrado-torra-media"], por_id["doce-de-leite-cremoso"]),
    )

    assert veredito.atende_pessoas == 40


@pytest.mark.risco("R10")
def test_an_unavailable_product_is_refused_before_anyone_is_quoted_a_total(
    seed: tuple[Produto, ...], por_id: dict[str, Produto]
) -> None:
    """R10 — aprovar o que a loja não tem seria um total exato e invendável.

    O seed mantém cinco itens `disponivel: false` de propósito. Numa composição o
    item fora do ar obriga a recompor, e o veredito precisa dizer qual é.
    """
    fora_do_ar = next(produto for produto in seed if not produto.disponivel)

    veredito = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS,
        pessoas=10,
        produtos=(*_cafe_da_manha_completo(por_id), fora_do_ar),
    )

    assert not veredito.aprovada
    indisponivel = [p for p in veredito.problemas if p.motivo is Motivo.DISPONIBILIDADE]
    assert [p.produto_id for p in indisponivel] == [fora_do_ar.id]


@pytest.mark.risco("R10")
def test_an_empty_composition_is_refused_and_not_approved_for_costing_nothing() -> None:
    """R10 — zero itens custa R$0,00, que cabe em qualquer teto.

    Sem esta recusa, a composição vazia seria a resposta ótima para qualquer
    orçamento apertado — o pior conselho possível apresentado como aprovado.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=10,
        produtos=(),
        orcamento_por_pessoa=Decimal("30.00"),
    )

    assert not veredito.aprovada
    assert Motivo.COMPOSICAO_VAZIA in [p.motivo for p in veredito.problemas]
    assert veredito.total == Decimal("0.00")


@pytest.mark.risco("R10")
def test_happy_hour_accepts_either_spirit_for_the_same_slot(por_id: dict[str, Produto]) -> None:
    """R10 — o slot do happy hour é `cachaca` OU `licor`, e um dos dois basta.

    Um slot que exigisse os dois recusaria composições legítimas, e recusa errada
    ensina o modelo a desconfiar do validador.
    """
    base = (por_id["queijo-minas-padrao"], por_id["chips-de-mandioca"])

    for bebida in ("cachaca", "licor"):
        escolha = next(p for p in por_id.values() if p.tipo == bebida and p.disponivel)
        veredito = validar(
            tipo_de_evento=TipoDeEvento.HAPPY_HOUR, pessoas=10, produtos=(*base, escolha)
        )
        assert veredito.aprovada, f"{bebida}: {veredito.problemas}"


@pytest.mark.risco("R10")
def test_the_year_end_hamper_asks_for_variety_and_not_for_named_slots(
    por_id: dict[str, Produto],
) -> None:
    """R10 — a cesta de fim de ano exige três tipos distintos, quaisquer que sejam.

    É a regra que não cabe na forma de slot nomeado, e por isso ela existe
    separada: dois queijos e um café são três itens e dois tipos.
    """
    dois_tipos = (
        por_id["queijo-minas-padrao"],
        por_id["queijo-canastra-meia-cura"],
        por_id["cafe-cerrado-torra-media"],
    )
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CESTA_DE_FIM_DE_ANO, pessoas=10, produtos=dois_tipos
    )
    assert not veredito.aprovada
    assert [p.motivo for p in veredito.problemas] == [Motivo.SLOT]

    tres_tipos = (*dois_tipos, por_id["doce-de-leite-cremoso"])
    assert validar(
        tipo_de_evento=TipoDeEvento.CESTA_DE_FIM_DE_ANO, pessoas=10, produtos=tres_tipos
    ).aprovada


@pytest.mark.risco("R10")
def test_repeating_a_product_does_not_multiply_it(por_id: dict[str, Produto]) -> None:
    """R10 — quantidade vem do `rendimento`, então repetir um id não quer dizer nada.

    Se repetir dobrasse o item, o modelo teria recuperado por acidente o controle
    da quantidade — que é justamente o que RF-1.6 tira dele.
    """
    cafe = por_id["cafe-cerrado-torra-media"]
    doce = por_id["doce-de-leite-cremoso"]

    uma_vez = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS, pessoas=40, produtos=(cafe, doce)
    )
    repetido = validar(
        tipo_de_evento=TipoDeEvento.KIT_BOAS_VINDAS, pessoas=40, produtos=(cafe, doce, cafe)
    )

    assert repetido.total == uma_vez.total
    assert len(repetido.itens) == len(uma_vez.itens)


@pytest.mark.risco("R10")
def test_every_problem_is_reported_and_not_just_the_first(por_id: dict[str, Produto]) -> None:
    """R10 — o modelo corrige numa rodada o que souber de uma vez.

    A métrica da spec é "≤ 3 rodadas até uma composição válida". Um veredito que
    parasse no primeiro problema garantiria uma rodada por problema.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=25,
        produtos=(
            por_id["queijo-canastra-premiado-mundial"],
            por_id["broa-de-fuba-com-erva-doce"],
        ),
        orcamento_por_pessoa=Decimal("10.00"),
        restricoes=("gluten",),
    )

    motivos = {p.motivo for p in veredito.problemas}
    assert {Motivo.SLOT, Motivo.RESTRICAO, Motivo.ORCAMENTO} <= motivos


@pytest.mark.risco("R10")
def test_a_composition_without_a_budget_is_judged_on_everything_else(
    por_id: dict[str, Produto],
) -> None:
    """R10 — orçamento é opcional; slot e restrição não são.

    O cliente que ainda não disse o teto não pode receber, por isso, uma
    composição que viola restrição declarada.
    """
    veredito = validar(
        tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
        pessoas=10,
        produtos=(
            por_id["cafe-cerrado-torra-media"],
            por_id["queijo-minas-padrao"],
            por_id["doce-de-leite-cremoso"],
            por_id["broa-de-fuba-com-erva-doce"],
        ),
        restricoes=("gluten",),
    )

    assert not veredito.aprovada
    assert veredito.excedente_por_pessoa is None
    assert Motivo.RESTRICAO in [p.motivo for p in veredito.problemas]


@pytest.mark.risco("R10")
def test_asking_for_a_composition_for_nobody_is_a_programming_error(
    por_id: dict[str, Produto],
) -> None:
    """R10 — zero pessoas não é uma composição reprovada, é uma chamada inválida.

    Devolver veredito aqui obrigaria a dividir por zero para achar o valor por
    pessoa. A fronteira da tool recusa antes (`Field(ge=1)`); a função pura recusa
    também, para quem a chamar de outro lugar.
    """
    with pytest.raises(ValueError, match="pessoas"):
        validar(
            tipo_de_evento=TipoDeEvento.CAFE_DA_MANHA,
            pessoas=0,
            produtos=_cafe_da_manha_completo(por_id),
        )
