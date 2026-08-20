"""Fixtures for the unit suite.

Unit here means: no container, no network, no clock. There is no integration
tier in this repository (docs/testes.md §1) — what needs live infrastructure is
verified by hand in /verificar-spec, and said so out loud.

The sample data below deliberately uses the same product names as the eval cases
in `evals/golden/`. When the S-01 seed lands, these names have to exist in it —
otherwise a case fails for the wrong reason: missing data, not a wrong agent.
"""

from decimal import Decimal

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/unit/ is a unit test — no need to mark each one."""
    for item in items:
        item.add_marker(pytest.mark.unit)


@pytest.fixture
def produto() -> dict:
    """One catalogue row, shaped like what a read-only tool returns.

    Price is Decimal on purpose: money is never a float in this project, and a
    unit test that accepts a float would let that through (R1, RF-1.3).
    """
    return {
        "sku": "queijo-canastra-meia-cura",
        "nome": "Queijo Canastra meia-cura",
        "preco_unitario": Decimal("78.90"),
        "maturacao_dias": 45,
        "disponivel": True,
        "prazo_estimado_dias": 4,
    }


@pytest.fixture
def catalogo(produto: dict) -> list[dict]:
    """A minimal catalogue: enough to test recommendation and totals, no more."""
    return [
        produto,
        {
            "sku": "doce-de-leite-vicosa",
            "nome": "Doce de leite de Vicosa",
            "preco_unitario": Decimal("24.50"),
            "maturacao_dias": None,
            "disponivel": True,
            "prazo_estimado_dias": 4,
        },
        {
            "sku": "cafe-cerrado-torra-media",
            "nome": "Cafe do Cerrado Mineiro, torra media",
            "preco_unitario": Decimal("42.00"),
            "maturacao_dias": None,
            "disponivel": False,
            "prazo_estimado_dias": 9,
        },
    ]


@pytest.fixture
def cliente() -> dict:
    """Synthetic customer data. Never a real CPF, in any file, ever.

    123.456.789-09 is a well-known test number that passes the check digits, so
    validation tests exercise the happy path without inventing a real person.
    """
    return {
        "nome": "Marta Ribeiro",
        "cpf": "123.456.789-09",
        "email": "marta@exemplo.com.br",
    }
