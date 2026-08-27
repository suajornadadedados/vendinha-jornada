"""Guards the catalogue seed that R1 depends on — without closing R1 itself.

R1 is closed by the agent never asserting a price, attribute or availability from
memory: `tests/unit/test_order_total.py` (S-04) proves the total comes from code,
and the groundedness eval (S-03) proves the text comes from a tool return. Both
assume something this file has to guarantee first — that the seed those tools read
is complete, unambiguous, and the only place a price lives.

A seed with a duplicated id, a missing price or a float where money should be is
still counted as "~50 products" by anyone eyeballing the folder. The gap only
surfaces later, as an agent that quotes a wrong number and a suite that agrees
with it.

Money is the reason the price check is this strict. `docs/testes.md` section 4:
a test that accepts a float lets through exactly the class of error R1 exists to
prevent. JSON has no decimal type, so the seed stores prices as strings and this
file refuses anything a `Decimal` cannot take losslessly.

No network, no agent, no API key — it only reads files already in the repo.
"""

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGO = REPO_ROOT / "data" / "catalogo"
SCHEMA = CATALOGO / "schema" / "produto.schema.json"

# docs/specs/S-01: "~50 produtos", metrica ">= 50, 100% com preco e >=4 atributos".
# S-10 subiu o piso para 60: o seed B2B tem 65, e um piso de 50 deixaria a suite
# verde depois de perder os petiscos e o topo de faixa inteiros — que sao
# exatamente o que faz uma composicao de evento ter escolha (ADR-013).
MINIMO_DE_PRODUTOS = 60
MINIMO_DE_ATRIBUTOS = 4

# Espelha o enum de `contem` em data/catalogo/schema/produto.schema.json e o
# Literal `Alergeno` em backend/vendinha/catalogo.py. Os tres precisam concordar:
# um alergeno que existe no seed e nao no Literal derruba a ingestao, e um que
# existe no Literal e nao no schema passa pela validacao e nunca e cortado.
ALERGENOS = frozenset({"lactose", "gluten", "ovos", "castanhas", "amendoim", "alcool", "acucar"})

# Os campos que descrevem o produto para a busca semantica da S-03 — o que faz o
# catalogo responder "presente pra minha sogra" em vez de exigir um filtro.
ATRIBUTOS = (
    "regiao",
    "intensidade",
    "harmonizacao",
    "ocasiao",
    "maturacao",
    "torra",
    "notas_sensoriais",
    "teor_alcoolico",
    "peso",
)


def _seed_files() -> list[Path]:
    return sorted(CATALOGO.glob("*.json"))


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _all_products() -> list[tuple[Path, dict[str, Any]]]:
    return [(path, item) for path in _seed_files() for item in _load(path)]


SEED_FILES = _seed_files()
PRODUCTS = _all_products()
PRODUCT_IDS = [f"{path.stem}:{item.get('id', '<sem id>')}" for path, item in PRODUCTS]
# Nem toda checagem precisa saber de que arquivo o produto veio.
PRODUCT_ROWS = [item for _, item in PRODUCTS]


def test_the_seed_is_not_empty() -> None:
    """An empty seed would make every check below vacuously true."""
    assert SEED_FILES, f"no seed file found under {CATALOGO}/*.json"


def test_the_seed_has_enough_products() -> None:
    """The S-01 success metric: at least 50 products in the catalogue."""
    assert len(PRODUCTS) >= MINIMO_DE_PRODUTOS, (
        f"{len(PRODUCTS)} products in the seed, spec asks for >= {MINIMO_DE_PRODUTOS}"
    )


@pytest.mark.parametrize(("seed_file", "produto"), PRODUCTS, ids=PRODUCT_IDS)
def test_every_product_matches_the_normative_schema(
    seed_file: Path, produto: dict[str, Any]
) -> None:
    """`data/catalogo/schema/produto.schema.json` is normative (data/catalogo/README.md)."""
    validator = Draft202012Validator(_load(SCHEMA))
    errors = sorted(validator.iter_errors(produto), key=lambda e: list(e.path))
    assert not errors, "\n".join(
        f"{seed_file.name}/{produto.get('id', '<sem id>')}: "
        f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
        for e in errors
    )


def test_no_product_id_is_used_twice() -> None:
    """Two rows sharing an id make "the price of X" an ambiguous question.

    The eval cases cite products by id, so a duplicate silently changes which
    product a case is about.
    """
    seen: dict[str, list[str]] = {}
    for path, produto in PRODUCTS:
        seen.setdefault(produto["id"], []).append(path.name)
    duplicated = {pid: files for pid, files in seen.items() if len(files) > 1}
    assert not duplicated, f"ids used more than once: {duplicated}"


@pytest.mark.parametrize("produto", PRODUCT_ROWS, ids=PRODUCT_IDS)
def test_every_price_survives_decimal_without_a_float(produto: dict[str, Any]) -> None:
    """R1 — money is Decimal, never float (docs/testes.md section 4).

    The schema already pins the string format. This goes one step further and
    asserts the value round-trips through Decimal unchanged, which is the property
    the order total will depend on in S-04.
    """
    preco = produto["preco"]
    assert isinstance(preco, str), (
        f"{produto['id']}: preco is {type(preco).__name__}, must be a string — "
        "a JSON number is parsed as float and loses cents"
    )
    try:
        valor = Decimal(preco)
    except InvalidOperation:  # pragma: no cover - the schema pattern catches this first
        pytest.fail(f"{produto['id']}: preco {preco!r} is not a valid Decimal")
    assert valor > 0, f"{produto['id']}: preco must be positive, got {valor}"
    assert str(valor) == preco, (
        f"{produto['id']}: preco {preco!r} does not round-trip through Decimal ({valor})"
    )


@pytest.mark.parametrize("produto", PRODUCT_ROWS, ids=PRODUCT_IDS)
def test_every_product_carries_enough_attributes_to_be_recommended(produto: dict[str, Any]) -> None:
    """The S-01 success metric: 100% of products with price and >= 4 attributes.

    A product with a name and a price is an e-commerce row. What makes the agent
    answer "a present for my mother-in-law who loves red wine" is the attributes
    around it (RF-1.2, RF-1.4).
    """
    preenchidos = [campo for campo in ATRIBUTOS if produto.get(campo)]
    assert len(preenchidos) >= MINIMO_DE_ATRIBUTOS, (
        f"{produto['id']}: only {len(preenchidos)} attributes filled "
        f"({preenchidos}), spec asks for >= {MINIMO_DE_ATRIBUTOS}"
    )


@pytest.mark.parametrize(("seed_file", "produto"), PRODUCTS, ids=PRODUCT_IDS)
def test_product_type_matches_the_file_it_lives_in(
    seed_file: Path, produto: dict[str, Any]
) -> None:
    """A cheese filed under cafes.json is found by the wrong search, or not at all."""
    esperado = {
        "queijos": {"queijo"},
        "cafes": {"cafe"},
        "doces": {"doce"},
        "cachacas-e-licores": {"cachaca", "licor"},
        "petiscos": {"petisco"},
    }
    assert seed_file.stem in esperado, (
        f"{seed_file.name} is not a known catalogue file — add it to this map "
        "so its products keep being checked"
    )
    assert produto["tipo"] in esperado[seed_file.stem], (
        f"{produto['id']}: tipo '{produto['tipo']}' does not belong in {seed_file.name}"
    )


@pytest.mark.parametrize("produto", PRODUCT_ROWS, ids=PRODUCT_IDS)
def test_every_product_declares_how_many_people_it_serves(produto: dict[str, Any]) -> None:
    """R10/R1 — `rendimento` is what turns "40 people" into a quantity.

    Without it the agent would have to guess how many guests a 250 g bag of coffee
    covers, and a guessed quantity is a made-up fact wearing a number (RF-1.6).
    The schema already pins the type; this pins that nobody parked a placeholder.
    """
    rendimento = produto["rendimento"]
    assert isinstance(rendimento, int) and not isinstance(rendimento, bool), (
        f"{produto['id']}: rendimento is {type(rendimento).__name__}, must be an int"
    )
    assert rendimento >= 1, f"{produto['id']}: rendimento must be >= 1, got {rendimento}"


@pytest.mark.parametrize("produto", PRODUCT_ROWS, ids=PRODUCT_IDS)
def test_every_product_declares_its_allergens(produto: dict[str, Any]) -> None:
    """R10 — `contem` is a declared cut, and it cannot be inferred from the text.

    Doce de leite does not announce lactose and broa de fuba does not warn about
    wheat. An undeclared allergen is the one catalogue gap whose cost is not a bad
    recommendation but someone getting hurt, so the field is required and closed:
    a typo like "gluteN" would be a restriction no search ever matches.
    """
    contem = produto["contem"]
    assert isinstance(contem, list), (
        f"{produto['id']}: contem is {type(contem).__name__}, must be a list "
        "(an empty list means 'nothing to declare', which is not the same as absent)"
    )
    desconhecidos = sorted(set(contem) - ALERGENOS)
    assert not desconhecidos, (
        f"{produto['id']}: allergens outside the closed list: {desconhecidos}. "
        f"Known: {sorted(ALERGENOS)}"
    )
    assert len(set(contem)) == len(contem), f"{produto['id']}: contem repeats an allergen: {contem}"
