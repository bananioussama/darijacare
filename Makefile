# DarijaCare — commandes usuelles (Linux, macOS, WSL, CI).
# Sous Windows sans `make` : utiliser .\tasks.ps1 <cible> (mêmes cibles).

export PYTHONUTF8 := 1
UV ?= uv

.PHONY: help install install-gpu lint format typecheck test test-data cov repro data-status eda up down logs clean precommit kb-validate rag-index rag-eval db-upgrade api api-smoke

help:
	@echo "Cibles : install install-gpu lint format typecheck test test-data cov repro data-status up down logs clean precommit kb-validate rag-index rag-eval db-upgrade api api-smoke"

install:  ## Environnement figé (uv.lock), torch CPU + hooks pre-commit
	$(UV) sync --locked --extra pipeline --extra nlu --extra rag --extra api --extra cpu
	$(UV) run pre-commit install

lint:
	$(UV) run ruff check src tests tools migrations
	$(UV) run black --check src tests tools migrations

format:
	$(UV) run ruff check --fix src tests tools migrations
	$(UV) run black src tests tools migrations

typecheck:
	$(UV) run mypy

test:
	$(UV) run pytest

test-data:  ## Tests sur les vraies données (après `make repro`)
	$(UV) run pytest -m data

cov:
	$(UV) run pytest --cov=darijacare --cov-report=term-missing --cov-report=html

repro:  ## Rejoue le pipeline de données (ingest -> validate -> normalize -> split -> eda)
	$(UV) run dvc repro

data-status:
	$(UV) run dvc status

eda:
	$(UV) run dvc repro eda

up:  ## Services de base (PostgreSQL, Qdrant, MLflow)
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

install-gpu:  ## Variante torch CUDA 12.6 (GPU Pascal et plus récents)
	$(UV) sync --locked --extra pipeline --extra nlu --extra rag --extra api --extra cu126

kb-validate:  ## Contrôle des 75 fiches (une par intention, sections, longueur, « fictif »)
	$(UV) run python -m darijacare.rag.cli validate-kb

rag-index:  ## Indexe les fiches dans Qdrant (BGE-M3 dense + creux ; QDRANT_URL ou mode local)
	$(UV) run python -m darijacare.rag.cli index

rag-eval:  ## Recall@k / MRR avec et sans filtre d'intention (validation puis test)
	$(UV) run python -m darijacare.rag.cli evaluate --split val
	$(UV) run python -m darijacare.rag.cli evaluate --split test

db-upgrade:  ## Migrations Alembic de la base PostgreSQL (POSTGRES_* ou DATABASE_URL dans .env)
	$(UV) run python -m darijacare.api.cli db-upgrade

api:  ## API FastAPI sur http://127.0.0.1:8000 (documentation : /docs)
	$(UV) run python -m darijacare.api.cli serve

api-smoke:  ## Démonstration de bout en bout sur l'API lancée -> reports/demo/phase4.md
	$(UV) run python tools/api_smoke.py

precommit:
	$(UV) run pre-commit run --all-files

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
