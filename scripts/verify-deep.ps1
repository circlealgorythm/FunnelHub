# ==============================================================================
# FunnelHub Deep DB-Backed Test Suite (verify.ps1 stage 2)
# Countermeasure for FUNNEL-EMAIL-001: quick verifyCmd covers only 18 fast tests,
# while DB-backed funnel/email tests lived outside the gate and drifted silently.
# Requires local PostgreSQL container "fh-test-pg" (funnelhub:funnelhub@127.0.0.1:5432).
# Machines without Docker/fh-test-pg (e.g., MacBook dev box) SKIP gracefully -
# the quick 18-test stage still gates the commit.
# ==============================================================================
$ErrorActionPreference = "Continue"

Write-Host "[DEEP] Deep DB-backed tests: checking fh-test-pg..."

$dockerOk = $false
try {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch { }

if (-not $dockerOk) {
    Write-Host "[SKIP] Docker engine not running - deep DB tests skipped (quick stage already passed)"
    exit 0
}

$exists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq "fh-test-pg" }
if (-not $exists) {
    Write-Host "[SKIP] fh-test-pg container not found on this machine - deep DB tests skipped"
    exit 0
}

$running = docker ps --format "{{.Names}}" | Where-Object { $_ -eq "fh-test-pg" }
if (-not $running) {
    Write-Host "[DEEP] Starting stopped container fh-test-pg..."
    docker start fh-test-pg | Out-Null
    Start-Sleep -Seconds 3
}

Write-Host "[DEEP] Running funnel/email DB-backed tests..."
$env:DATABASE_URL = "postgresql+asyncpg://funnelhub:funnelhub@127.0.0.1:5432/funnelhub"
uv run pytest tests/test_funnel_runner.py tests/test_funnel_engine.py tests/test_funnel_answers.py tests/test_funnel_autostart.py tests/test_email_funnel_definition.py tests/test_email_messaging.py tests/test_email_provider_webhooks.py tests/test_cors_and_vk_failclosed.py -q
exit $LASTEXITCODE
