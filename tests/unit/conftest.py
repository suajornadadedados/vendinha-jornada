"""Fixtures for the unit suite.

Unit here means: no container, no network, no clock. There is no integration
tier in this repository (docs/testes.md §1) — what needs live infrastructure is
verified by hand in /verificar-spec, and said so out loud.

The sample data below deliberately uses the same product ids and prices as the
seed in `data/catalogo/` (S-01). It is shaped like a tool return, not like a seed
row, but the numbers have to agree: a fixture that quotes a price the catalogue
does not have would let `test_order_total.py` assert a total no customer could
ever be charged.
"""

from decimal import Decimal
from typing import Any

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/unit/ is a unit test — no need to mark each one."""
    for item in items:
        item.add_marker(pytest.mark.unit)


@pytest.fixture
def produto() -> dict[str, Any]:
    """One catalogue row, shaped like what a read-only tool returns.

    Price is Decimal on purpose: money is never a float in this project, and a
    unit test that accepts a float would let that through (R1, RF-1.3).
    """
    return {
        "sku": "queijo-canastra-meia-cura",
        "nome": "Queijo Canastra meia-cura",
        "preco_unitario": Decimal("89.90"),
        "maturacao_dias": 45,
        "disponivel": True,
        "prazo_estimado_dias": 4,
    }


@pytest.fixture
def catalogo(produto: dict[str, Any]) -> list[dict[str, Any]]:
    """A minimal catalogue: enough to test recommendation and totals, no more."""
    return [
        produto,
        {
            "sku": "doce-de-leite-cremoso",
            "nome": "Doce de leite cremoso",
            "preco_unitario": Decimal("32.00"),
            "maturacao_dias": None,
            "disponivel": True,
            "prazo_estimado_dias": 4,
        },
        # Unavailable on purpose, and unavailable in the seed too: the "we do not
        # have this right now" path needs a row, and it must be the same row the
        # catalogue would return.
        {
            "sku": "cafe-fermentado-anaerobico",
            "nome": "Cafe fermentado anaerobico",
            "preco_unitario": Decimal("96.00"),
            "maturacao_dias": None,
            "disponivel": False,
            "prazo_estimado_dias": 7,
        },
    ]


@pytest.fixture
def cliente() -> dict[str, Any]:
    """Synthetic customer data. Never a real CPF, in any file, ever.

    123.456.789-09 is a well-known test number that passes the check digits, so
    validation tests exercise the happy path without inventing a real person.
    """
    return {
        "nome": "Marta Ribeiro",
        "cpf": "123.456.789-09",
        "email": "marta@exemplo.com.br",
    }
