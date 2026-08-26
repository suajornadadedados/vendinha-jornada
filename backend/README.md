# backend/ — o projeto de produto

Hoje esta pasta é **scaffold de build**, não código: `pyproject.toml` com mypy strict e um
pacote vazio. Foi entregue pela S-00 porque três arquivos dependem da pasta existir:

| Quem | O que faz quando `backend/` existe |
|---|---|
| `.github/workflows/ci.yml` | liga o job `typecheck` (que até então aparecia como *skipped*) |
| `tests/conftest.py` | para de pular os testes marcados com `requires_backend` |
| `scripts/run-tests.sh` | passa a **reprovar** suíte vazia — toda feature nasce com teste |

O primeiro comportamento chega na S-02 (FastAPI + grafo mínimo + Langfuse). Lint e format
são os da raiz (`ruff.toml`): uma régua só, um lugar só.

```bash
uv sync --dev
uv run mypy .
```
