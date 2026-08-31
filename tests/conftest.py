"""Shared configuration for the whole test suite.

Three things live here because every subfolder needs them:

1. **The `risco` marker.** Every test declares which risk of `docs/riscos.md` it
   closes. That is what lets `/verificar-spec` answer "which risks does this spec
   close, and which test proves each one?" without reading the implementation.
2. **Graceful skipping while `backend/` does not exist.** The convention is
   written before the code it governs (see `docs/testes.md`), so a test that
   imports the agent must skip, not error, until the spec that creates it lands.
3. **O Langfuse desligado.** A suíte não fala com o projeto de produção — ver
   `_o_langfuse_fica_fora_da_suite` no fim do arquivo.
"""

import json
import sys
from collections.abc import Awaitable, Callable, Iterator
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


@pytest.fixture(autouse=True)
def _o_langfuse_fica_fora_da_suite(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A suíte não exporta trace nenhum para o projeto de produção.

    Sem isto ela exporta, e exportava: `config.py` faz `load_dotenv` no import, o
    `.env` da máquina do desenvolvedor tem credencial de verdade, e todo teste que
    monta a aplicação constrói um `CallbackHandler` real no `lifespan`. O resultado
    medido foi **97 dos 100 traces mais recentes** sendo lixo de `pytest` — custo
    zero, latência de 4 ms — enterrando as conversas de verdade sob uma pilha de
    conversas com um modelo dublê. Quem abria o Langfuse para ver o custo de um
    atendimento clicava em traces vazios e concluía que o custo não era coletado.

    **String vazia, e não `delenv`.** `Settings` lê o `.env` como segunda fonte
    (`env_file=ENV_FILE`), então tirar a variável do ambiente do processo não a
    torna ausente: faz o arquivo vencer. A mesma pegadinha já está documentada em
    `test_provider_config.py`, e é o tipo de detalhe que faz uma fixture parecer
    funcionar e não funcionar.

    **Os dois caches, nas duas pontas.** `get_settings` e `observability.client`
    são `lru_cache`; sem limpá-los, o cliente já construído por um teste anterior
    continua sendo devolvido, com credencial e tudo.

    Não quebra nenhum teste que precise do caminho COM credencial:
    `test_the_langfuse_client_is_built_with_the_masking_hook` monta a própria chave
    falsa apontando para uma porta inalcançável e limpa estes mesmos dois caches —
    o `setenv` dele vence este, porque o ambiente do processo tem precedência sobre
    o arquivo e o dele é aplicado depois.
    """
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")

    if not BACKEND.is_dir():
        # Mesma razão do `requires_backend`: este arquivo tem que continuar
        # importável antes de a S-00 existir.
        yield
        return

    from vendinha.config import get_settings
    from vendinha.observability import client

    get_settings.cache_clear()
    client.cache_clear()
    try:
        yield
    finally:
        client.cache_clear()
        get_settings.cache_clear()
