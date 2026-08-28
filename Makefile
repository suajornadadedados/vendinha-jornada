# Atalhos do dia a dia. Cada alvo é uma linha só de comando real — o Makefile
# documenta o comando, não o esconde. Quem não tiver `make` roda a linha de
# dentro do alvo e chega no mesmo lugar (ver README, seção Quickstart).

.DEFAULT_GOAL := help
.PHONY: help up down logs db-setup seed api test lint format typecheck evals-check evals-groundedness evals-composicao evals-checkout evals-observabilidade evals-hitl evals evals-afetadas hooks

help:  ## Lista os alvos disponíveis
	@grep -E "^[a-z-]+:.*?## " $(MAKEFILE_LIST) | sed "s/:.*## /\t/" | expand -t24

up:  ## Sobe Postgres e Qdrant e espera ficarem healthy
	docker compose up -d --wait

down:  ## Derruba os serviços (volumes preservados)
	docker compose down

logs:  ## Segue o log dos serviços
	docker compose logs -f

db-setup:  ## Cria as tabelas do checkpointer do LangGraph (rode uma vez após `make up`)
	cd backend && uv run python -m vendinha.db

seed:  ## Carrega o catálogo no Postgres e no Qdrant (rode após `make db-setup`)
	cd backend && uv run python -m vendinha.ingest

api:  ## Sobe a API (precisa de `make up`, `make db-setup` e `make seed` antes)
	cd backend && uv run python -m vendinha

test:  ## Suíte completa: unit + security
	bash scripts/run-tests.sh

lint:  ## Lint e checagem de formatação (uma régua só, e a MESMA do CI)
	uv run --project backend ruff check .
	uv run --project backend ruff format --check .

format:  ## Aplica a formatação
	uv run --project backend ruff format .

typecheck:  ## mypy strict no backend E na suite de testes
	cd backend && uv run mypy .
	uv run --project backend mypy --config-file backend/pyproject.toml --explicit-package-bases tests

evals-check:  ## Valida os casos de eval contra o schema — sem agente, sem API
	python -m pytest tests/unit/test_eval_corpus_is_traceable.py -q

evals-groundedness:  ## Roda os 6 casos da S-03 contra o agente (precisa de `make up`, `db-setup` e `seed`)
	cd backend && uv run python -m vendinha.evals.runner --spec S-03

evals-composicao:  ## Roda os 4 casos de composição da S-11 contra o agente (precisa de `make up`, `db-setup` e `seed`)
	cd backend && uv run python -m vendinha.evals.runner --spec S-11

evals-checkout:  ## Roda os 7 casos da S-04 contra o agente (precisa de `make up`, `db-setup` e `seed`)
	cd backend && uv run python -m vendinha.evals.runner --spec S-04

evals-observabilidade:  ## Roda os 2 casos da S-02 — PII e teto de custo (precisa de `make up`, `db-setup` e `seed`)
	cd backend && uv run python -m vendinha.evals.runner --spec S-02

evals-hitl:  ## Roda os 4 casos da S-05 — aprovação e emissão de NF (precisa de `make up`, `db-setup` e `seed`)
	cd backend && uv run python -m vendinha.evals.runner --spec S-05

# A suíte inteira, as cinco sub-suítes, 23 casos. É a camada 2 do ADR-014, e é o
# MESMO comando que o CI roda no pós-merge — não uma segunda receita que envelhece
# em paralelo. `--tudo` pula a decisão por diff e roda tudo.
evals:  ## Suíte completa: as cinco sub-suítes, contra o agente (precisa de `make up`, `db-setup` e `seed`)
	bash scripts/evals-ci.sh --tudo

evals-afetadas:  ## Só as sub-suítes que o seu diff contra a main pode ter mudado — o que o CI faz no PR
	bash scripts/evals-ci.sh

hooks:  ## Instala os portões locais (pre-commit, commit-msg, pre-push)
	pre-commit install --install-hooks
	pre-commit install --hook-type commit-msg
	pre-commit install --hook-type pre-push
