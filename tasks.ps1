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
    "install"     { Invoke-Step "uv sync --locked --all-extras"; Invoke-Step "uv run pre-commit install" }
    "lint"        { Invoke-Step "uv run ruff check src tests tools"; Invoke-Step "uv run black --check src tests tools" }
    "format"      { Invoke-Step "uv run ruff check --fix src tests tools"; Invoke-Step "uv run black src tests tools" }
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
    "precommit"   { Invoke-Step "uv run pre-commit run --all-files" }
    default       { Write-Host "Cibles : install lint format typecheck test test-data cov repro data-status eda up down logs precommit" }
}
