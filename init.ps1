# Harness Initialization & Verification Script (Windows PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "=== Harness Initialization ===" -ForegroundColor Cyan
Write-Host "Working directory: $(Get-Location)"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed. Please install uv first."
    exit 1
}

Write-Host "=== Checking dependencies with uv ===" -ForegroundColor Yellow
uv sync --extra dev

Write-Host "=== Running verification (ruff + pytest) ===" -ForegroundColor Yellow
$env:PYTHONPATH = "src"

uv run ruff check src/funnelhub/api/auth.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

uv run pytest tests/test_metadata.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "=== Verification Passed! Baseline is healthy. ===" -ForegroundColor Green
Write-Host "Startup command: uv run uvicorn funnelhub.main:app --port 8000" -ForegroundColor Gray
