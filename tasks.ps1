# DarijaCare — équivalent PowerShell du Makefile (Windows sans make).
# Usage : .\tasks.ps1 <cible>    ex. .\tasks.ps1 repro
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

function Invoke-Step([string]$Cmd) {
    Write-Host "> $Cmd" -ForegroundColor DarkMagenta
    Invoke-Expression $Cmd
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    "install"     { Invoke-Step "uv sync --locked --extra pipeline --extra nlu --extra rag --extra api --extra cpu"; Invoke-Step "uv run pre-commit install" }
    "install-gpu" { Invoke-Step "uv sync --locked --extra pipeline --extra nlu --extra rag --extra api --extra cu126" }
    "lint"        { Invoke-Step "uv run ruff check src tests tools migrations"; Invoke-Step "uv run black --check src tests tools migrations" }
    "format"      { Invoke-Step "uv run ruff check --fix src tests tools migrations"; Invoke-Step "uv run black src tests tools migrations" }
    "typecheck"   { Invoke-Step "uv run mypy" }
    "test"        { Invoke-Step "uv run pytest" }
    "test-data"   { Invoke-Step "uv run pytest -m data" }
    "cov"         { Invoke-Step "uv run pytest --cov=darijacare --cov-report=term-missing --cov-report=html" }
    "repro"       { Invoke-Step "uv run dvc repro" }
    "data-status" { Invoke-Step "uv run dvc status" }
    "eda"         { Invoke-Step "uv run dvc repro eda" }
    "certs"       { Invoke-Step "uv run python tools/make_certs.py" }
    "up"          { Invoke-Step "uv run python tools/make_certs.py"; Invoke-Step "docker compose up -d --build" }
    "dev-up"      { Invoke-Step "docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres qdrant mlflow" }
    "down"        { Invoke-Step "docker compose down" }
    "logs"        { Invoke-Step "docker compose logs -f --tail=100" }
    "kb-validate" { Invoke-Step "uv run python -m darijacare.rag.cli validate-kb" }
    "rag-index"   { Invoke-Step "uv run python -m darijacare.rag.cli index" }
    "rag-eval"    { Invoke-Step "uv run python -m darijacare.rag.cli evaluate --split val"; Invoke-Step "uv run python -m darijacare.rag.cli evaluate --split test" }
    "db-upgrade"  { Invoke-Step "uv run python -m darijacare.api.cli db-upgrade" }
    "api"         { Invoke-Step "uv run python -m darijacare.api.cli serve" }
    "api-smoke"   { Invoke-Step "uv run python tools/api_smoke.py" }
    "front-install" { Invoke-Step "npm --prefix frontend ci" }
    "front-dev"   { Invoke-Step "npm --prefix frontend run dev" }
    "front-test"  { Invoke-Step "npm --prefix frontend run typecheck"; Invoke-Step "npm --prefix frontend run format:check"; Invoke-Step "npm --prefix frontend test" }
    "front-build" { Invoke-Step "npm --prefix frontend run build" }
    "integration" { Invoke-Step "uv run pytest -m integration" }
    "e2e"         { Push-Location frontend; try { Invoke-Step "node --env-file=../.env node_modules/@playwright/test/cli.js test" } finally { Pop-Location } }
    "load-capacity" {
        Invoke-Step "docker compose -f docker-compose.yml -f deploy/load/docker-compose.load.yml up -d backend edge"
        Invoke-Step "uv run --group load locust -f tests/load/locustfile.py --headless -u 20 -r 2 -t 3m --host https://127.0.0.1:8443/api --csv reports/quality/load/capacite"
        Invoke-Step "docker compose up -d backend edge"
    }
    "load-abuse"  {
        $env:DARIJACARE_LOAD_WAIT = "0.5,1.5"
        Invoke-Step "uv run --group load locust -f tests/load/locustfile.py --headless -u 20 -r 5 -t 1m --host https://127.0.0.1:8443/api --csv reports/quality/load/abus"
    }
    "quality-decision"   { Invoke-Step "uv run python -m darijacare.quality.cli decision --split test" }
    "quality-injections" { Invoke-Step "uv run python -m darijacare.quality.cli injections" }
    "quality-robustness" {
        $device = if ($env:DEVICE) { $env:DEVICE } else { "cpu" }
        Invoke-Step "uv run python -m darijacare.quality.cli robustness --split test --device $device"
    }
    "quality-latency"    { Invoke-Step "uv run python -m darijacare.quality.cli latency --device cpu --quantize" }
    "audit" {
        Invoke-Step "uv export --locked --format requirements-txt --no-hashes --no-emit-project --extra nlu --extra rag --extra api --extra cpu --no-dev -o requirements-prod.txt"
        Invoke-Step "uvx --from pip-audit==2.10.1 pip-audit --no-deps --disable-pip -r requirements-prod.txt"
        Invoke-Step "npm --prefix frontend audit"
    }
    "registry-promote" {
        $model = if ($env:MODEL) { $env:MODEL } else { "v5" }
        Invoke-Step "uv run python -m darijacare.nlu.registry promote --model $model"
    }
    "gold-validate" { Invoke-Step "uv run python -m darijacare.data.gold validate" }
    "precommit"   { Invoke-Step "uv run pre-commit run --all-files" }
    default       { Write-Host "Cibles : certs up dev-up install install-gpu lint format typecheck test test-data cov repro data-status eda up down logs precommit kb-validate rag-index rag-eval db-upgrade api api-smoke front-install front-dev front-test front-build integration e2e load-capacity load-abuse quality-decision quality-injections quality-robustness quality-latency audit registry-promote gold-validate" }
}
