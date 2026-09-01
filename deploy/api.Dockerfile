# A imagem da API. Contexto de build: a RAIZ do repositório, nunca `backend/`.
#
# **O layout de diretórios é contrato, não arrumação.** `config.py` resolve
# `REPO_ROOT = Path(__file__).resolve().parents[2]`, e três leitores dependem
# disso: `<root>/.env`, `<root>/data/catalogo/` (o seed) e
# `<root>/data/precos-modelos.json` — este último no caminho de **runtime** de
# `/admin/metricas`. Um `COPY backend/ /app` sobe, atende o chat, e só quebra
# quando alguém abre a tela de métricas. Por isso a imagem reproduz
# `/app/backend/vendinha/` e `/app/data/`.
#
# Duas dependências que NÃO precisam de nada do sistema, e vale registrar para
# ninguém acrescentar depois "por via das dúvidas": `psycopg[binary]` traz a
# libpq compilada (sem `libpq-dev`, sem gcc), e o `reportlab` da DANFE usa só as
# fontes built-in do PDF (sem pacote de fontes).

FROM python:3.12-slim AS builder

# `uv` porque o lockfile do projeto é `backend/uv.lock` e é a única fonte de
# versões que existe aqui — `pip install .` resolveria de novo e a imagem sairia
# com um conjunto de versões que ninguém revisou.
COPY --from=ghcr.io/astral-sh/uv:0.9.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

# As dependências primeiro, e o código depois, porque as duas mudam em ritmos
# diferentes: `--no-install-project` deixa esta camada valer enquanto o lockfile
# não mudar, e um commit que só mexe em `vendinha/` reaproveita o venv inteiro.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim AS runtime

# Non-root (RNF-9). Numerado e sem shell: este usuário existe para ser dono do
# processo, não para alguém entrar com ele.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin vendinha

ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/backend

COPY --from=builder --chown=vendinha:vendinha /app/backend/.venv /app/backend/.venv

# O pacote NÃO é instalado no venv (`--no-install-project` acima): ele é
# importado do fonte, a partir do `WORKDIR`. Uma cópia instalada mais o fonte
# montado seriam duas versões do mesmo módulo, e a que responde depende do
# `sys.path` — a classe de bug que só aparece depois de um deploy.
COPY --chown=vendinha:vendinha backend/vendinha ./vendinha

# `data/` sobe para a raiz do "repo" dentro da imagem, e não para dentro de
# `backend/`, porque é lá que `REPO_ROOT` vai procurar.
COPY --chown=vendinha:vendinha data /app/data

USER vendinha

EXPOSE 8000

# `python -m vendinha`, e não `uvicorn vendinha.app:app`. Em Linux os dois
# funcionam — o `__main__.py` diz isso —, mas o entrypoint próprio é o que
# decide o event loop, e usar o mesmo comando em Windows e em contêiner é a
# decisão já registrada lá. Comando divergente por plataforma é como se
# descobre, em produção, que a plataforma de desenvolvimento nunca exerceu o
# caminho de produção.
CMD ["python", "-m", "vendinha"]
