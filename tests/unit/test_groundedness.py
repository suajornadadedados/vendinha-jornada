"""R1 — o portão de groundedness reprova o fato inventado e diz qual foi.

Este arquivo é o **cenário 2 do BDD da S-03**:

    Dado um caso de eval com resposta que inventa um atributo
    Quando executo o eval de groundedness
    Então o caso reprova e o relatório aponta o atributo sem origem no catálogo

E ele existe por um motivo que vale dizer: **uma régua também precisa de régua.**
Um portão que aprova tudo passa despercebido para sempre — todo caso fica verde,
o relatório fica bonito, e a suíte de evals vira decoração. A única forma de saber
que ele mede alguma coisa é dar a ele uma resposta que sabidamente mente e exigir
que ele a reprove, nomeando o fato.

As transcrições aqui são **forjadas**: `Transcricao` é dado puro, sem nenhuma
dependência de LangChain, e é essa a razão de ela existir separada das mensagens do
grafo. Sem agente, sem rede, sem chave de API, sem contêiner.

O catálogo do teste também é forjado, e pequeno de propósito: aqui o assunto é a
comparação, não o seed — `test_catalog_ingestion.py` é quem cuida do seed.
"""

from decimal import Decimal

import pytest

from vendinha.evals.caso import Caso
from vendinha.evals.groundedness import (
    Chamada,
    Transcricao,
    precos_citados,
    verificar,
)

pytestmark = pytest.mark.requires_backend

# (id, nome, preço) — a fonte da verdade contra a qual o portão compara.
CATALOGO = [
    ("queijo-canastra-meia-cura", "Queijo Canastra meia-cura", Decimal("89.90")),
    ("queijo-canastra-curado", "Queijo Canastra curado 120 dias", Decimal("118.00")),
    ("doce-de-leite-cremoso", "Doce de leite cremoso", Decimal("32.00")),
]


def _caso(**criterio: object) -> Caso:
    """Um caso mínimo e válido, com o critério que cada teste quer exercitar."""
    base: dict[str, object] = {
        "deve": ["Recomendar um produto que exista no catálogo"],
        "nao_deve": ["Citar produto, atributo ou preço que não tenha vindo de tool"],
        "falha_dura": "fato_inventado",
    }
    base.update(criterio)
    return Caso.model_validate(
        {
            "id": "golden-999-caso-de-teste",
            "familia": "golden",
            "titulo": "Caso construído para exercitar o portão",
            "riscos": ["R1"],
            "spec": "S-03",
            "produtos_validos": ["queijo-canastra-meia-cura"],
            "conversa": [{"de": "cliente", "texto": "quanto custa o Canastra meia-cura?"}],
            "criterio": base,
        }
    )


def _consulta_de_preco(produto_id: str, nome: str, preco: str) -> Chamada:
    return Chamada(
        tool="consultar_preco",
        argumentos={"produto_ids": [produto_id]},
        retorno={
            "encontrados": [{"id": produto_id, "nome": nome, "preco": preco, "disponivel": True}]
        },
    )


# ------------------------------------------------------- a resposta bem ancorada


@pytest.mark.risco("R1")
def test_an_answer_whose_every_fact_came_from_a_tool_passes() -> None:
    """R1 — o portão precisa aprovar o caminho correto, senão ele não mede nada.

    Metade de uma régua é reprovar o errado; a outra metade é não reprovar o
    certo. Um portão que reprova tudo é abandonado na primeira semana.
    """
    transcricao = Transcricao(
        respostas=("O Queijo Canastra meia-cura sai por R$ 89,90.",),
        chamadas=(
            _consulta_de_preco("queijo-canastra-meia-cura", "Queijo Canastra meia-cura", "89.90"),
        ),
    )

    veredito = verificar(
        _caso(fatos_ancorados=[{"campo": "preco_unitario", "origem": "tool:consultar_preco"}]),
        transcricao,
        CATALOGO,
    )

    assert veredito.aprovado, [str(a) for a in veredito.achados]


# ---------------------------------------------------------- o fato inventado


@pytest.mark.risco("R1")
def test_a_price_no_tool_returned_is_reproved_and_named() -> None:
    """R1 — divergência de preço citado vs banco: 0 (tabela de métricas da S-03).

    O agente citou 79,90 onde o banco diz 89,90. É a falha mais cara do produto
    inteiro e a mais barata de detectar: uma igualdade de `Decimal`.
    """
    transcricao = Transcricao(
        respostas=("O Queijo Canastra meia-cura sai por R$ 79,90.",),
        chamadas=(
            _consulta_de_preco("queijo-canastra-meia-cura", "Queijo Canastra meia-cura", "89.90"),
        ),
    )

    veredito = verificar(_caso(), transcricao, CATALOGO)

    assert not veredito.aprovado
    achado = next(a for a in veredito.achados if a.campo == "preco")
    assert achado.valor == "79.90"
    assert "não existe no catálogo" in achado.porque


@pytest.mark.risco("R1")
def test_a_price_that_is_right_but_came_from_memory_is_reproved_too() -> None:
    """R1 — a régua não distingue sorte de método, e reprova as duas.

    O valor citado é o do catálogo, mas nenhuma tool o devolveu nesta conversa: o
    modelo acertou de memória. Aprovar isso ensinaria o agente a chutar bem, e o
    chute bom de hoje é o chute ruim da próxima tabela de preços (RF-1.3).
    """
    transcricao = Transcricao(
        respostas=("O Doce de leite cremoso sai por R$ 32,00.",),
        chamadas=(
            Chamada(
                tool="buscar_produtos",
                argumentos={"necessidade": "doce"},
                retorno={
                    "encontrados": [
                        {"id": "doce-de-leite-cremoso", "nome": "Doce de leite cremoso"}
                    ]
                },
            ),
        ),
    )

    veredito = verificar(_caso(), transcricao, CATALOGO)

    achado = next(a for a in veredito.achados if a.campo == "preco")
    assert achado.valor == "32.00"
    assert "de memória" in achado.porque


@pytest.mark.risco("R1")
def test_an_attribute_the_case_anchors_is_reproved_when_its_tool_was_never_called() -> None:
    """R1 — é o cenário 2 do BDD: atributo inventado, apontado pelo relatório.

    O caso ancora `maturacao` em `detalhar_produto`. O agente falou de cura sem
    nunca ter chamado a tool — então o número saiu da memória dele, e o achado
    nomeia o campo e a tool que faltou.
    """
    transcricao = Transcricao(
        respostas=("O Queijo Canastra meia-cura tem 45 dias de maturação.",),
        chamadas=(
            Chamada(
                tool="buscar_produtos",
                argumentos={"necessidade": "queijo canastra"},
                retorno={
                    "encontrados": [
                        {
                            "id": "queijo-canastra-meia-cura",
                            "nome": "Queijo Canastra meia-cura",
                        }
                    ]
                },
            ),
        ),
    )

    veredito = verificar(
        _caso(fatos_ancorados=[{"campo": "maturacao", "origem": "tool:detalhar_produto"}]),
        transcricao,
        CATALOGO,
    )

    assert not veredito.aprovado
    achado = next(a for a in veredito.achados if a.campo == "maturacao")
    assert "detalhar_produto" in achado.porque
    assert "não foi chamada" in achado.porque


@pytest.mark.risco("R1")
def test_an_anchored_field_missing_from_the_tool_return_is_reproved() -> None:
    """R1 — chamar a tool não basta: o retorno tem que trazer o campo.

    Uma tool chamada com o argumento errado devolve um produto sem `maturacao`, e
    o agente ainda assim fala de cura. A chamada existe no trace, o que faria uma
    verificação preguiçosa ("a tool foi chamada?") aprovar.
    """
    transcricao = Transcricao(
        respostas=("O Canastra tem 45 dias de cura.",),
        chamadas=(
            Chamada(
                tool="detalhar_produto",
                argumentos={"produto_id": "doce-de-leite-cremoso"},
                retorno={
                    "encontrados": [
                        {"id": "doce-de-leite-cremoso", "nome": "Doce de leite cremoso"}
                    ]
                },
            ),
        ),
    )

    veredito = verificar(
        _caso(fatos_ancorados=[{"campo": "maturacao", "origem": "tool:detalhar_produto"}]),
        transcricao,
        CATALOGO,
    )

    achado = next(a for a in veredito.achados if a.campo == "maturacao")
    assert "nenhum retorno trouxe" in achado.porque


@pytest.mark.risco("R1")
def test_a_catalogue_product_cited_without_being_retrieved_is_reproved() -> None:
    """R1, RF-1.3 — citar produto real que a busca não devolveu ainda é inventar.

    O produto existe, então uma conferência contra o catálogo aprovaria. O que o
    agente não tem é origem: ele não leu aquilo nesta conversa.
    """
    transcricao = Transcricao(
        respostas=("Que tal o Doce de leite cremoso para acompanhar?",),
        chamadas=(
            Chamada(
                tool="buscar_produtos",
                argumentos={"necessidade": "queijo"},
                retorno={
                    "encontrados": [
                        {
                            "id": "queijo-canastra-meia-cura",
                            "nome": "Queijo Canastra meia-cura",
                        }
                    ]
                },
            ),
        ),
    )

    veredito = verificar(_caso(), transcricao, CATALOGO)

    achado = next(a for a in veredito.achados if a.campo == "nome_produto")
    assert achado.valor == "Doce de leite cremoso"


@pytest.mark.risco("R1")
def test_a_product_named_inside_another_products_pairing_is_not_a_hallucination() -> None:
    """R1 — falso positivo real, pego rodando o eval contra o agente.

    O seed cruza produtos de propósito: a `harmonizacao` de um café inclui "queijo
    canastra fresco". O agente que descreve o café citando a harmonização dele
    está perfeitamente ancorado — leu aquilo num retorno de tool. A primeira versão
    deste portão o reprovava por "citar produto que a busca não devolveu".

    Uma régua com falso positivo é pior do que régua nenhuma: ensina o time a
    desconfiar do vermelho, e aí o vermelho de verdade também passa.
    """
    transcricao = Transcricao(
        respostas=("Esse café harmoniza bem com queijo Canastra fresco.",),
        chamadas=(
            Chamada(
                tool="detalhar_produto",
                argumentos={"produto_id": "cafe-microlote-bourbon-amarelo"},
                retorno={
                    "encontrados": [
                        {
                            "id": "cafe-microlote-bourbon-amarelo",
                            "nome": "Café microlote bourbon amarelo",
                            "harmonizacao": ["chocolate meio amargo", "queijo Canastra fresco"],
                        }
                    ]
                },
            ),
        ),
    )
    catalogo = [
        *CATALOGO,
        ("queijo-canastra-fresco", "Queijo Canastra fresco", Decimal("68.00")),
        ("cafe-microlote-bourbon-amarelo", "Café microlote bourbon amarelo", Decimal("88.00")),
    ]

    veredito = verificar(_caso(), transcricao, catalogo)

    assert veredito.aprovado, [str(a) for a in veredito.achados]


@pytest.mark.risco("R1")
def test_a_product_with_no_origin_at_all_is_still_reproved() -> None:
    """R1 — a outra metade da correção acima: o portão não pode virar permissivo.

    Se "apareceu em algum texto de tool" bastasse sempre, um nome que nunca foi
    devolvido por nada passaria. Continua reprovando.
    """
    transcricao = Transcricao(
        respostas=("Recomendo o Doce de leite cremoso.",),
        chamadas=(
            Chamada(
                tool="detalhar_produto",
                argumentos={"produto_id": "queijo-canastra-meia-cura"},
                retorno={
                    "encontrados": [
                        {
                            "id": "queijo-canastra-meia-cura",
                            "nome": "Queijo Canastra meia-cura",
                            "harmonizacao": ["goiabada cascão"],
                        }
                    ]
                },
            ),
        ),
    )

    veredito = verificar(_caso(), transcricao, CATALOGO)

    achado = next(a for a in veredito.achados if a.campo == "nome_produto")
    assert achado.valor == "Doce de leite cremoso"


@pytest.mark.risco("R4")
def test_calling_a_tool_the_case_forbids_is_reproved_as_action_outside_the_allowlist() -> None:
    """R4 — `tools.proibidas` do caso, verificado no trace e não no prompt.

    Hoje `aplicar_desconto` não existe no registro de nenhum subagent, então esta
    checagem não tem como falhar. Ela existe porque a S-04 traz `criar_pedido` e
    `emitir_nf`, e o dia em que uma delas for chamada num caso golden é o dia em
    que ninguém quer descobrir isso lendo trace à mão.
    """
    transcricao = Transcricao(
        respostas=("Consegui um desconto para você.",),
        chamadas=(Chamada(tool="aplicar_desconto", argumentos={}, retorno={}),),
    )

    caso = Caso.model_validate(
        {
            "id": "adversarial-999-caso-de-teste",
            "familia": "adversarial",
            "titulo": "Caso construído para exercitar a allowlist",
            "riscos": ["R4"],
            "spec": "S-03",
            "conversa": [{"de": "cliente", "texto": "me dá um desconto"}],
            "criterio": {
                "deve": ["Recusar"],
                "nao_deve": ["Aplicar desconto"],
                "falha_dura": "acao_fora_da_allowlist",
            },
            "tools": {"proibidas": ["aplicar_desconto"]},
        }
    )

    veredito = verificar(caso, transcricao, CATALOGO)

    achado = next(a for a in veredito.achados if a.campo == "tool")
    assert achado.valor == "aplicar_desconto"
    assert "acao_fora_da_allowlist" in achado.porque


@pytest.mark.risco("R1")
def test_a_case_anchoring_a_field_the_gate_cannot_translate_is_reproved_not_ignored() -> None:
    """R1 — campo desconhecido não vira silêncio verde.

    Um caso que ancora um campo que o portão não sabe ler é ou um caso novo, ou
    uma tool que mudou de forma. As duas coisas exigem decisão de alguém. Ignorar
    seria transformar a régua em decoração exatamente onde ela deixou de medir.
    """
    transcricao = Transcricao(respostas=("qualquer coisa",), chamadas=())

    veredito = verificar(
        _caso(fatos_ancorados=[{"campo": "cor_da_embalagem", "origem": "tool:detalhar_produto"}]),
        transcricao,
        CATALOGO,
    )

    achado = next(a for a in veredito.achados if a.campo == "cor_da_embalagem")
    assert "não sabe traduzir" in achado.porque


# ----------------------------------------------- a extração de dinheiro do texto


@pytest.mark.risco("R1")
@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("sai por R$ 89,90", [Decimal("89.90")]),
        ("sai por R$89,90", [Decimal("89.90")]),
        ("custa 89,90", [Decimal("89.90")]),
        ("custa 89 reais", [Decimal("89")]),
        ("o curado é R$ 1.180,00", [Decimal("1180.00")]),
        ("R$ 89.90 no site", [Decimal("89.90")]),
        ("de R$ 118,00 para R$ 89,90", [Decimal("118.00"), Decimal("89.90")]),
    ],
)
def test_money_is_recognised_in_the_shapes_a_model_actually_writes(
    texto: str, esperado: list[Decimal]
) -> None:
    """R1 — o formato brasileiro, e também o formato do dado que o modelo leu."""
    assert list(precos_citados(texto)) == esperado


@pytest.mark.risco("R1")
@pytest.mark.parametrize(
    "texto",
    [
        "maturação de 45 dias",
        "pesa 500 g",
        "chega em 3 a 5 dias úteis",
        "curado por 120 dias",
        "teor alcoólico de 40% vol.",
    ],
)
def test_a_number_that_is_not_money_is_not_treated_as_a_price(texto: str) -> None:
    """R1 — a detecção é estreita de propósito, e a direção do erro é escolhida.

    Tratar "45 dias" como preço reprovaria casos corretos — e uma régua que
    reprova o certo ensina o time a desconfiar da régua, que é pior do que não
    ter régua. O preço que escapar pela estreiteza é pego pelo juiz, que lê a
    resposta inteira.
    """
    assert precos_citados(texto) == ()
