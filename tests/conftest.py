"""Shared configuration for the whole test suite.

Two things live here because every subfolder needs them:

1. **The `risco` marker.** Every test declares which risk of `docs/riscos.md` it
   closes. That is what lets `/verificar-spec` answer "which risks does this spec
   close, and which test proves each one?" without reading the implementation.
2. **Graceful skipping while `backend/` does not exist.** The convention is
   written before the code it governs (see `docs/testes.md`), so a test that
   imports the agent must skip, not error, until the spec that creates it lands.
"""

import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

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


@pytest.fixture(scope="session")
def empresa_valida() -> dict[str, Any]:
    """A compradora corporativa de teste, usada pelas duas camadas (S-04).

    Um dicionário, e não um modelo Pydantic, porque este arquivo tem que continuar
    importável sem `backend/` — é o que faz `requires_backend` pular em vez de
    quebrar na coleta.

    Tudo aqui é fabricado. O CNPJ `11.222.333/0001-81` é o mesmo do `golden-003`:
    dígitos verificadores válidos, empresa que não existe. Nenhum documento, nome,
    e-mail ou endereço real entra neste repositório, nem em fixture (RNF-7).
    """
    return {
        "razao_social": "Aurora Servicos Digitais LTDA",
        "cnpj": "11.222.333/0001-81",
        "contato_nome": "Marta Ribeiro",
        "contato_email": "marta@exemplo.com.br",
        "endereco": {
            "logradouro": "Rua das Acacias",
            "numero": "240",
            "complemento": "sala 12",
            "bairro": "Savassi",
            "cidade": "Belo Horizonte",
            "uf": "MG",
            "cep": "30140-071",
        },
    }


@pytest.fixture
def chamar() -> Callable[..., Awaitable[dict[str, Any]]]:
    """Executa uma tool e devolve o JSON que ela respondeu, já parseado.

    Passa pelo `ainvoke` de propósito, e não pela função interna: é o caminho que
    o `ToolNode` percorre, incluindo a validação do `args_schema`. Chamar a
    coroutine direto testaria um caminho que produção não usa.
    """

    async def _chamar(tool: Any, **argumentos: Any) -> dict[str, Any]:
        resposta: dict[str, Any] = json.loads(await tool.ainvoke(argumentos))
        return resposta

    return _chamar
