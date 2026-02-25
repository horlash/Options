# ═══════════════════════════════════════════════════════════
# Options-feature Dev Environment Startup
# ═══════════════════════════════════════════════════════════
# Usage: .\dev-start.ps1
# This script:
#   1. Starts Postgres (paper trading DB) via Docker
#   2. Waits for it to be healthy
#   3. Runs Alembic migrations
#   4. Starts the Flask dev server on port 5001
#
# Prod stays untouched on port 5000.
# ═══════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "═══ Options-feature Dev Environment ═══" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Start Postgres ──────────────────────────────────
Write-Host "[1/4] Starting paper trading database..." -ForegroundColor Yellow
docker-compose -f "$ProjectRoot\docker-compose.dev.yml" up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start Postgres container" -ForegroundColor Red
    exit 1
}

# ── Step 2: Wait for Postgres health ────────────────────────
Write-Host "[2/4] Waiting for database to be ready..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    $health = docker inspect --format='{{.State.Health.Status}}' paper_trading_dev_db 2>$null
    if ($health -eq "healthy") {
        Write-Host "       Database is healthy!" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 1
    $waited++
    if ($waited % 5 -eq 0) {
        Write-Host "       Still waiting... ($waited seconds)" -ForegroundColor DarkYellow
    }
}
if ($waited -ge $maxWait) {
    Write-Host "WARNING: Database may not be ready (timed out after ${maxWait}s)" -ForegroundColor Red
}

# ── Step 3: Run Alembic Migrations ──────────────────────────
Write-Host "[3/4] Running paper trading migrations..." -ForegroundColor Yellow
Push-Location $ProjectRoot
try {
    # Use paper_user (superuser) for migrations
    $env:PAPER_TRADE_DB_URL = "postgresql://paper_user:paper_pass@localhost:5433/paper_trading"
    alembic -c alembic_paper.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Alembic migration may have failed" -ForegroundColor Red
    } else {
        Write-Host "       Migrations applied!" -ForegroundColor Green
    }
} finally {
    Pop-Location
}

# ── Step 4: Start Flask Dev Server ──────────────────────────
Write-Host "[4/4] Starting Flask dev server on port 5001..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  ┌──────────────────────────────────────────────┐" -ForegroundColor DarkCyan
Write-Host "  │  Dev server: http://localhost:5001            │" -ForegroundColor Cyan
Write-Host "  │  Login:      dev / password123                │" -ForegroundColor Cyan
Write-Host "  │  Prod stays: http://localhost:5000            │" -ForegroundColor DarkGray
Write-Host "  │  Press Ctrl+C to stop                        │" -ForegroundColor DarkGray
Write-Host "  └──────────────────────────────────────────────┘" -ForegroundColor DarkCyan
Write-Host ""

# Load .env.feature values and start the server
Set-Location $ProjectRoot
$env:PORT = "5001"
python -m backend.app
