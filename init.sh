#!/usr/bin/env bash
set -e

echo "=== Harness Initialization ==="
echo "Working directory: $(pwd)"

if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed." >&2
    exit 1
fi

echo "=== Checking dependencies with uv ==="
uv sync --extra dev

echo "=== Running verification (ruff + pytest) ==="
export PYTHONPATH="src"

uv run ruff check src/funnelhub/api/auth.py
uv run pytest tests/test_metadata.py

echo "=== Verification Passed! Baseline is healthy. ==="
echo "Startup command: uv run uvicorn funnelhub.main:app --port 8000"
