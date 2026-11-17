# DarijaCare — commandes usuelles (Linux, macOS, WSL, CI).
# Sous Windows sans `make` : utiliser .\tasks.ps1 <cible> (mêmes cibles).

export PYTHONUTF8 := 1
UV ?= uv

.PHONY: help install lint format typecheck test test-data cov repro data-status eda up down logs clean precommit

help:
	@echo "Cibles : install lint format typecheck test test-data cov repro data-status up down logs clean precommit"

install:  ## Environnement figé (uv.lock), torch CPU + hooks pre-commit
	$(UV) sync --locked --extra pipeline --extra nlu --extra cpu
	$(UV) run pre-commit install

lint:
	$(UV) run ruff check src tests tools
	$(UV) run black --check src tests tools

format:
	$(UV) run ruff check --fix src tests tools
	$(UV) run black src tests tools

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
	$(UV) sync --locked --extra pipeline --extra nlu --extra cu126

precommit:
	$(UV) run pre-commit run --all-files

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
