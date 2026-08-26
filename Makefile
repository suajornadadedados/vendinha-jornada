# Atalhos do dia a dia. Cada alvo é uma linha só de comando real — o Makefile
# documenta o comando, não o esconde. Quem não tiver `make` roda a linha de
# dentro do alvo e chega no mesmo lugar (ver README, seção Quickstart).

.DEFAULT_GOAL := help
.PHONY: help up down logs db-setup api test lint format typecheck evals-check evals hooks

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

api:  ## Sobe a API (precisa de `make up` e `make db-setup` antes)
	cd backend && uv run python -m vendinha

test:  ## Suíte completa: unit + security
	bash scripts/run-tests.sh

lint:  ## Lint e checagem de formatação (uma régua só, na raiz)
	ruff check .
	ruff format --check .

format:  ## Aplica a formatação
	ruff format .

typecheck:  ## mypy strict no backend E na suite de testes
	cd backend && uv run mypy .
	uv run --project backend mypy --config-file backend/pyproject.toml --explicit-package-bases tests

evals-check:  ## Valida os casos de eval contra o schema — sem agente, sem API
	python -m pytest tests/unit/test_eval_corpus_is_traceable.py -q

evals:  ## Executa a suíte de evals contra o agente (chega na S-06)
	@echo "O runner de evals é entregável da S-06 (docs/specs/S-06-qualidade-como-gate.md)."
	@echo "Por enquanto use: make evals-check — valida os casos contra o schema."
	@exit 1

hooks:  ## Instala os portões locais (pre-commit, commit-msg, pre-push)
	pre-commit install --install-hooks
	pre-commit install --hook-type commit-msg
	pre-commit install --hook-type pre-push
