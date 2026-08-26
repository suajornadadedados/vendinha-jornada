"""Fixtures for the security suite.

These tests are the code-level half of what `evals/adversarial/` describes in
prose. The eval suite asks "did the agent behave?"; these ask "is the behaviour
even reachable?" — and the second question is the one that produces a guarantee.

The adversarial payloads are not duplicated here. They are read from
`evals/adversarial/*.yaml`, so a new attack case is written once and both
layers pick it up.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml

EVALS = Path(__file__).resolve().parents[2] / "evals"
ADVERSARIAL = EVALS / "adversarial"


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        caso: dict[str, Any] = yaml.safe_load(handle)
        return caso


def _casos() -> list[dict[str, Any]]:
    return [_load(p) for p in sorted(ADVERSARIAL.glob("*.yaml"))]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Everything under tests/security/ is a security test."""
    for item in items:
        item.add_marker(pytest.mark.security)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Turn every adversarial eval case into a test case.

    Ask for `caso_adversarial` in a test signature and it runs once per file in
    evals/adversarial/, named by the case id.
    """
    if "caso_adversarial" in metafunc.fixturenames:
        casos = _casos()
        metafunc.parametrize("caso_adversarial", casos, ids=[c["id"] for c in casos])


@pytest.fixture(scope="session")
def casos_adversariais() -> list[dict[str, Any]]:
    """All adversarial cases at once, for tests that reason across the corpus."""
    casos = _casos()
    assert casos, "evals/adversarial/ is empty — the adversarial suite has no corpus"
    return casos


@pytest.fixture(scope="session")
def payloads_de_injecao(casos_adversariais: list[dict[str, Any]]) -> list[str]:
    """Every customer utterance from the adversarial corpus, flattened.

    Use to assert that no payload reaches a side effect — never to assert on the
    wording of the reply. What is guaranteed is that the action is unreachable,
    not that the model answers politely.
    """
    return [
        turno["texto"]
        for caso in casos_adversariais
        for turno in caso["conversa"]
        if turno["de"] == "cliente"
    ]


@pytest.fixture(scope="session")
def tools_proibidas(casos_adversariais: list[dict[str, Any]]) -> set[str]:
    """Tools no adversarial case may reach.

    Some of these — `aplicar_desconto` — are not registered on any subagent at
    all. They are not denied; they do not exist. A test that finds one present
    has found an architecture bug, not a prompt bug (ADR-002, RF-2.6).
    """
    return {
        tool
        for caso in casos_adversariais
        for tool in (caso.get("tools", {}).get("proibidas") or [])
    }


@pytest.fixture
def pii_de_teste() -> dict[str, str]:
    """Synthetic PII for redaction tests (R5, RF-5.2).

    Every value here is fabricated. The guardrail is absolute: no real CPF,
    e-mail, name or certificate enters this repository, not even in a fixture.
    """
    return {
        "cpf": "123.456.789-09",
        "cpf_sem_pontuacao": "12345678909",
        "email": "marta@exemplo.com.br",
        "nome": "Marta Ribeiro",
        "telefone": "+55 31 90000-0000",
    }


@pytest.fixture
def subagents_read_only() -> set[str]:
    """Subagents that must own no write tool, by construction (ADR-002)."""
    return {"recomendacao"}
