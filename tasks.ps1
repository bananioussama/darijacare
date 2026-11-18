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
    "up"          { Invoke-Step "docker compose up -d" }
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
    "precommit"   { Invoke-Step "uv run pre-commit run --all-files" }
    default       { Write-Host "Cibles : install install-gpu lint format typecheck test test-data cov repro data-status eda up down logs precommit kb-validate rag-index rag-eval db-upgrade api api-smoke front-install front-dev front-test front-build" }
}
