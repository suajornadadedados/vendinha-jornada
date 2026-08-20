"""Shared configuration for the whole test suite.

Two things live here because every subfolder needs them:

1. **The `risco` marker.** Every test declares which risk of `docs/riscos.md` it
   closes. That is what lets `/verificar-spec` answer "which risks does this spec
   close, and which test proves each one?" without reading the implementation.
2. **Graceful skipping while `backend/` does not exist.** The convention is
   written before the code it governs (see `docs/testes.md`), so a test that
   imports the agent must skip, not error, until the spec that creates it lands.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
EVALS = REPO_ROOT / "evals"
DOCS = REPO_ROOT / "docs"

# Once backend/ exists (S-00), its packages become importable from any test.
if BACKEND.is_dir() and str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "risco(id): the risk from docs/riscos.md this test closes, e.g. risco('R2')",
    )
    config.addinivalue_line("markers", "unit: fast, no I/O, no container")
    config.addinivalue_line("markers", "security: permission boundary, injection, PII, HITL")
    config.addinivalue_line(
        "markers",
        "requires_backend: needs backend/ — skipped until the spec that creates it lands",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip backend-dependent tests instead of failing them on import.

    A permanently red suite teaches people to ignore a red suite. A skipped test
    turns itself on the day the code arrives.
    """
    if BACKEND.is_dir():
        return
    skip = pytest.mark.skip(reason="backend/ ainda nao existe (entregavel da S-00)")
    for item in items:
        if "requires_backend" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def evals_dir() -> Path:
    return EVALS
