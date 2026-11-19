# DarijaCare — commandes usuelles (Linux, macOS, WSL, CI).
# Sous Windows sans `make` : utiliser .\tasks.ps1 <cible> (mêmes cibles).

export PYTHONUTF8 := 1
UV ?= uv

.PHONY: certs dev-up help install install-gpu lint format typecheck test test-data cov repro data-status eda up down logs clean precommit kb-validate rag-index rag-eval db-upgrade api api-smoke front-install front-dev front-test front-build integration e2e load-capacity load-abuse quality-decision quality-injections quality-robustness quality-latency audit registry-promote gold-validate

help:
	@echo "Cibles : install install-gpu lint format typecheck test test-data cov repro data-status up down logs clean precommit kb-validate rag-index rag-eval db-upgrade api api-smoke front-install front-dev front-test front-build integration e2e load-capacity load-abuse quality-decision quality-injections quality-robustness quality-latency audit registry-promote gold-validate"

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
	$(UV) run pytest -m data tests/data

cov:
	$(UV) run pytest --cov=darijacare --cov-report=term-missing --cov-report=html

repro:  ## Rejoue le pipeline de données (ingest -> validate -> normalize -> split -> eda)
	$(UV) run dvc repro

data-status:
	$(UV) run dvc status

eda:
	$(UV) run dvc repro eda

certs:  ## Certificat TLS auto-signé du frontal (deploy/certs, ignoré par git)
	$(UV) run python tools/make_certs.py

up: certs  ## Pile complète : https://127.0.0.1:8443 (nginx, interface, API, données)
	docker compose up -d --build

dev-up:  ## Données seules (PostgreSQL, Qdrant, MLflow) publiées sur 127.0.0.1
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres qdrant mlflow

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

front-install:  ## Dépendances de l'interface (versions figées : package-lock.json)
	npm --prefix frontend ci

front-dev:  ## Interface sur http://127.0.0.1:5173 (relaie /api vers l'API du port 8000)
	npm --prefix frontend run dev

front-test:  ## Types, formatage et tests de l'interface
	npm --prefix frontend run typecheck
	npm --prefix frontend run format:check
	npm --prefix frontend test

front-build:  ## Version de production de l'interface -> frontend/dist
	npm --prefix frontend run build

# --- Phase 6 : qualité, sécurité, livraison -------------------------------------------

integration:  ## Tests Testcontainers : API <-> PostgreSQL <-> Qdrant (Docker requis)
	$(UV) run pytest -m integration

e2e:  ## Parcours Playwright sur la pile lancée (make up) ; comptes lus dans .env
	cd frontend && node --env-file=../.env node_modules/@playwright/test/cli.js test

load-capacity:  ## Locust, 20 clients, limites relâchées -> reports/quality/load/
	docker compose -f docker-compose.yml -f deploy/load/docker-compose.load.yml up -d backend edge
	$(UV) run --group load locust -f tests/load/locustfile.py --headless -u 20 -r 2 -t 3m 		--host https://127.0.0.1:8443/api --csv reports/quality/load/capacite
	docker compose up -d backend edge

load-abuse:  ## Locust, 20 clients rapides, limites normales : des 429 sont attendus
	DARIJACARE_LOAD_WAIT=0.5,1.5 $(UV) run --group load locust -f tests/load/locustfile.py 		--headless -u 20 -r 5 -t 1m --host https://127.0.0.1:8443/api --csv reports/quality/load/abus

quality-decision:  ## Politique de décision rejouée sur le test (erreurs critiques)
	$(UV) run python -m darijacare.quality.cli decision --split test

quality-injections:  ## 50 attaques + entrées atypiques sur la pile lancée (make up)
	$(UV) run python -m darijacare.quality.cli injections

quality-robustness:  ## Test de perturbation du NLU (GPU conseillé : DEVICE=cuda)
	$(UV) run python -m darijacare.quality.cli robustness --split test --device $(or $(DEVICE),cpu)

quality-latency:  ## Latence du NLU sur CPU, avec l'essai int8
	$(UV) run python -m darijacare.quality.cli latency --device cpu --quantize

audit:  ## pip-audit (dépendances de production) et npm audit
	$(UV) export --locked --format requirements-txt --no-hashes --no-emit-project 		--extra nlu --extra rag --extra api --extra cpu --no-dev > requirements-prod.txt
	uvx --from pip-audit==2.10.1 pip-audit --no-deps --disable-pip -r requirements-prod.txt
	npm --prefix frontend audit

registry-promote:  ## Promotion explicite du modèle MODEL (contrôle de non-régression)
	$(UV) run python -m darijacare.nlu.registry promote --model $(or $(MODEL),v5)

gold-validate:  ## Contrôles du jeu gold (data/gold, rédigé par l'équipe) et kappa
	$(UV) run python -m darijacare.data.gold validate

precommit:
	$(UV) run pre-commit run --all-files

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
