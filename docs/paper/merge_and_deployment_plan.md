# Feature Branch Merge & Pi Deployment Plan

## Overview

Merge `feature/paper-trading` (which includes `feature/automated-trading`) from `Options-feature` into the production codebase (`Options`), then deploy to Raspberry Pi with dual environments (prod + dev).

**Scope**: 94 files changed, ~29K lines — paper trading, Tradier broker, monitoring, trading UI, PostgreSQL, analytics.

---

## Phase 1: Backup & Rollback Points

### 1.1 Local Prod Backup
```powershell
Copy-Item -Recurse Options "Options-backup-pre-merge-$(Get-Date -Format yyyyMMdd)"
```

### 1.2 GitHub Repo Tag
```powershell
cd Options
git tag v1.0.1-pre-merge -m "Stable prod before paper trading merge"
git push origin v1.0.1-pre-merge
```
The commit `74560ad` is always recoverable via this tag.

### 1.3 Pi Rollback Point
```bash
# On Pi — preserve current image
docker tag horlamy/newscanner:1.0.1 horlamy/newscanner:1.0.1-backup
```
Old image `1.0.1` stays on Docker Hub as-is. New merged image gets tag `1.1.0`.

---

## Phase 2: Safe Incremental Merge (3 Layers)

Instead of a big-bang merge, we apply changes in 3 layers — each testable independently.

---

### Layer 1: New Files Only (Zero Risk)

These files don't exist in prod. Adding them can't break anything.

**Backend — Paper Trading Core:**
| File | Purpose |
|------|---------|
| `backend/api/paper_routes.py` | Paper trading REST API (38 endpoints) |
| `backend/database/paper_models.py` | SQLAlchemy models for trades, snapshots |
| `backend/database/paper_session.py` | Separate Postgres session + RLS |
| `backend/queries/__init__.py` | Queries package |
| `backend/queries/analytics.py` | Raw SQL analytics queries |
| `backend/security/__init__.py` | Security package init |
| `backend/security/crypto.py` | Fernet encryption for API tokens |

**Backend — Broker Integration:**
| File | Purpose |
|------|---------|
| `backend/services/broker/__init__.py` | Provider pattern init |
| `backend/services/broker/base.py` | Abstract broker base class |
| `backend/services/broker/exceptions.py` | Broker exceptions |
| `backend/services/broker/factory.py` | Broker factory (Tradier/Paper) |
| `backend/services/broker/tradier.py` | Tradier API client |

**Backend — Services:**
| File | Purpose |
|------|---------|
| `backend/services/analytics_service.py` | Portfolio analytics |
| `backend/services/context_service.py` | Trade context collector |
| `backend/services/lifecycle.py` | Position lifecycle state machine |
| `backend/services/monitor_service.py` | Background trade monitor + cron |
| `backend/utils/market_hours.py` | Market hours utility |
| `backend/utils/rate_limiter.py` | API rate limiter |

**Frontend — New Components:**
| File | Purpose |
|------|---------|
| `frontend/css/components/trading.css` | Trading UI styles |
| `frontend/js/components/portfolio.js` | Portfolio panel |
| `frontend/js/components/risk-dashboard.js` | Risk metrics |
| `frontend/js/components/trade-modal.js` | Trade entry modal |
| `frontend/js/paper_api.js` | Paper trading API client |
| `frontend/js/utils/ai-cache.js` | AI analysis cache |
| `frontend/vendor/chart.umd.min.js` | Chart.js library |

**Database & Config:**
| File | Purpose |
|------|---------|
| `alembic_paper.ini` | Alembic config for paper DB |
| `migrations/paper/env.py` | Migration environment |
| `migrations/paper/versions/001_initial_paper_trading.py` | Initial schema |
| `migrations/paper/versions/002_force_rls.py` | RLS policies |
| `migrations/paper/versions/003_snapshot_username.py` | Snapshot user col |
| `migrations/paper/script.py.mako` | Migration template |
| `docker-compose.paper.yml` | Dev Postgres setup |
| `docker-compose.dev.yml` | Dev Docker config |
| `scripts/init-app-user.sql` | DB user init |
| `scripts/init_dev_db.sql` | Dev DB init |
| `reset_paper_db.bat` | Dev DB reset utility |

**Tests:**
| File | Purpose |
|------|---------|
| `tests/test_point_01_schema.py` → `test_point_09_tradier.py` | 9 test modules |
| `tests/test_phase3_*.py`, `test_phase4_*.py`, `test_phase5_*.py` | Phase tests |
| `tests/test_advanced_scenarios.py` | Edge case tests |
| `tests/test_e2e_multi_user_lifecycle.py` | E2E tests |

**Docs (for reference):**
| File | Destination |
|------|-------------|
| `docs/paper/*.md` (13 deep-dive files) | → `Options/docs/paper/` |
| `docs/AUTOMATED_TRADING_ANALYSIS.md` | → `Options/docs/` |

**Verify after Layer 1:**
```powershell
cd Options
python -c "from backend.app import app; print('✅ App imports successfully')"
```
This should pass because nothing is wired up yet.

---

### Layer 2: Modify Existing Files (Controlled Risk)

These are surgical edits to existing prod files. Each change is small and testable.

| File | Change | Risk |
|------|--------|------|
| `backend/config.py` | Add `PAPER_TRADE_DB_URL` config entry | 🟢 Low — additive only |
| `backend/security.py` | Add `/api/paper` to public routes whitelist | 🟢 Low — 1 line |
| `backend/app.py` | Register `paper_bp` blueprint + init monitor | 🟡 Medium — new import |
| `backend/users.json` | Add dev user for testing | 🟢 Low — additive |
| `requirements.txt` | Add `alembic`, `psycopg2-binary`, `cryptography` | 🟢 Low — additive |
| `frontend/index.html` | Add Portfolio/Risk tabs + new script tags | 🟡 Medium — UI changes |
| `frontend/css/styles.css` | Add trading-related styles | 🟢 Low — additive CSS |
| `frontend/js/app.js` | Add tab switching logic + paper API init | 🟡 Medium |
| `frontend/js/components/opportunities.js` | Add "Trade" button to cards | 🟡 Medium |
| `frontend/js/components/analysis-detail.js` | Minor updates | 🟢 Low |
| `frontend/js/components/scanner.js` | Add AI cache integration | 🟢 Low |
| `frontend/js/utils/api.js` | Minor API util changes | 🟢 Low |
| `run_and_share.bat` | Updated launcher | 🟢 Low |
| `share_app.bat` | Updated sharer | 🟢 Low |
| `start_backend.bat` | Updated startup | 🟢 Low |
| `.gitignore` | Add new ignore patterns | 🟢 Low |

**Verify after Layer 2:**
```powershell
# Without Postgres (scanner should still work)
python -c "from backend.app import app; print('✅ App imports successfully')"

# Start app — scanner features should work
start_backend.bat
# Test: login, run a scan, verify results display
```

---

### Layer 3: Handle Breaking Changes (Careful)

| Change | What Happened | Resolution |
|--------|--------------|------------|
| `ticker_lookup.py` DELETED | Feature branch replaced it with inline dict in `reasoning_engine.py` and simplified `free_news.py` | ✅ Safe — feature branch already handles both. The simplified approach is actually better (no JSON file dependency). |
| `backend/services/reasoning_engine.py` | Removed `TickerLookup` import, added inline company name dict + sector search hints | Test AI analysis output for 3-4 tickers to verify |
| `backend/api/free_news.py` | Removed `TickerLookup` import, simplified Google News query | Test news fetching for 3-4 tickers to verify |
| `backend/services/hybrid_scanner_service.py` | Added AI cache hooks, verdict display changes | Test LEAP and weekly scans |
| `backend/api/orats.py` | Minor encoding fix | Low risk |

**Verify after Layer 3:**
```powershell
# Full scan test
start_backend.bat
# Test: scan NVDA (LEAP), scan SPY (weekly), verify AI analysis, verify news
```

---

## Phase 3: Files to EXCLUDE from Merge

| File | Reason |
|------|--------|
| `docs/TRADING_UI_DEMO.html` | 1,897-line standalone mockup — not app code |
| `docs/TRADING_UI_PLAN.md` | Planning doc — superseded by implementation |
| `task.md` | Internal dev checklist — not app code |
| `start_feature.bat` | Dev-only launcher (port 5001) — not needed in prod |
| `dev-start.ps1` | Dev-only PowerShell launcher — not needed in prod |

---

## Phase 4: Docker Build & Push

### 4.1 Build Prod Image
```powershell
cd Options
docker buildx build --platform linux/amd64,linux/arm64 `
  -t horlamy/newscanner:1.1.0 `
  -t horlamy/newscanner:latest `
  --push .
```

### 4.2 Build Dev Image (same code, different tag)
```powershell
docker buildx build --platform linux/amd64,linux/arm64 `
  -t horlamy/newscanner:dev `
  --push .
```

### 4.3 Docker Hub Tags After Push
| Tag | Purpose |
|-----|---------|
| `1.0.1` | Old prod (rollback) |
| `1.1.0` | New merged prod |
| `dev` | Development/testing |
| `latest` | Points to 1.1.0 |

---

## Phase 5: Pi Deployment

### 5.1 Pi Docker Compose
```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    ports: ["5433:5432"]
    environment:
      POSTGRES_DB: paper_trading
      POSTGRES_USER: paper_user
      POSTGRES_PASSWORD: paper_pass
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U paper_user -d paper_trading"]
      interval: 10s
      timeout: 5s
      retries: 5

  scanner-prod:
    image: horlamy/newscanner:1.1.0
    restart: unless-stopped
    ports: ["5000:5000"]
    env_file: .env.prod
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - prod_data:/app/data

  scanner-dev:
    image: horlamy/newscanner:dev
    restart: unless-stopped
    ports: ["5001:5001"]
    env_file: .env.dev
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - dev_data:/app/data

volumes:
  pg_data:
  prod_data:
  dev_data:
```

### 5.2 Start on Pi
```bash
docker compose pull
docker compose up -d
# Run migrations
docker exec scanner-prod alembic -c alembic_paper.ini upgrade head
docker exec scanner-dev alembic -c alembic_paper.ini upgrade head
```

---

## Phase 6: Rollback Procedures

### Local Rollback
```powershell
Remove-Item -Recurse Options
Rename-Item "Options-backup-pre-merge-<date>" Options
```

### Git Rollback
```powershell
cd Options
git reset --hard v1.0.1-pre-merge
git push --force origin main
```

### Pi Rollback
```bash
# Edit docker-compose: change image to horlamy/newscanner:1.0.1
docker compose down
docker compose up -d
```

---

# Testing Plan

## T1: Pre-Merge — Feature Branch Stability

Confirm feature branch is stable before touching prod. **Requires Docker Postgres running.**

```powershell
cd Options-feature
docker compose -f docker-compose.paper.yml up -d
```

| # | Test | Command | Pass |
|---|------|---------|------|
| 1.1 | DB schema | `pytest tests/test_point_01_schema.py -v` | 10/10 |
| 1.2 | Polling | `pytest tests/test_point_02_polling.py -v` | All |
| 1.3 | Brackets | `pytest tests/test_point_04_brackets.py -v` | All |
| 1.4 | Context | `pytest tests/test_point_06_context.py -v` | All |
| 1.5 | RLS | `pytest tests/test_point_07_rls.py -v` | 10/10 |
| 1.6 | Concurrency | `pytest tests/test_point_08_10_11_concurrency_lifecycle.py -v` | All |
| 1.7 | Tradier | `pytest tests/test_point_09_tradier.py -v` | All |
| 1.8 | Paper routes | `pytest tests/test_phase3_paper_routes.py -v` | All |
| 1.9 | Market hours | `pytest tests/test_phase3_market_hours.py -v` | All |
| 1.10 | Order logic | `pytest tests/test_phase4_order_logic.py -v` | All |
| 1.11 | Analytics | `pytest tests/test_phase5_analytics.py -v` | All |
| 1.12 | E2E | `pytest tests/test_e2e_multi_user_lifecycle.py -v` | All |

## T2: Post-Merge Layer 1 — Import Check

| # | Test | Expected |
|---|------|----------|
| 2.1 | `python -c "from backend.app import app"` | No import errors |
| 2.2 | Start server without Postgres | Scanner works, paper trading shows "DB unavailable" |
| 2.3 | Login as admin | Dashboard loads |
| 2.4 | Run LEAP scan (NVDA) | Opportunities returned |

## T3: Post-Merge Layer 2 — UI Check

| # | Test | Expected |
|---|------|----------|
| 3.1 | Open app in browser | 3 tabs visible: Scanner, Portfolio, Risk |
| 3.2 | Scanner tab | Scan results display normally |
| 3.3 | Portfolio tab | Shows "Connect to start" or empty state |
| 3.4 | Risk tab | Shows default metrics |
| 3.5 | Opportunity cards | "Trade" button visible on each card |

## T4: Post-Merge Layer 3 — Breaking Changes

| # | Test | Expected |
|---|------|----------|
| 4.1 | AI analysis (NVDA) | Perplexity returns valid analysis with company name |
| 4.2 | AI analysis (AAPL) | Company name resolved correctly |
| 4.3 | Free news (SPY) | Google News returns articles |
| 4.4 | Weekly scan (SPY) | Results returned with AI verdict |
| 4.5 | Sector scan (Technology) | Top picks returned |

## T5: Post-Merge Full — With Postgres

Start Docker Postgres, run migrations, test paper trading end-to-end.

| # | Test | Expected |
|---|------|----------|
| 5.1 | `docker compose -f docker-compose.paper.yml up -d` | Postgres starts |
| 5.2 | `alembic -c alembic_paper.ini upgrade head` | Migrations run |
| 5.3 | Place a paper trade via UI | Trade appears in portfolio |
| 5.4 | Check portfolio P&L | P&L calculates correctly |
| 5.5 | Tradier settings | Token saves and encrypts |
| 5.6 | Run all tests | `pytest tests/ -v` — all pass |

## T6: Docker Image Verification

| # | Test | Expected |
|---|------|----------|
| 6.1 | Build succeeds | Exit code 0 |
| 6.2 | Tags on Docker Hub | `1.0.1`, `1.1.0`, `dev`, `latest` |
| 6.3 | `docker run -p 5000:5000 horlamy/newscanner:1.1.0` | App starts |

## T7: Pi Deployment Verification

| # | Test | Expected |
|---|------|----------|
| 7.1 | `docker compose up -d` on Pi | 3 containers running |
| 7.2 | Postgres healthy | `\dt` shows tables |
| 7.3 | Prod accessible (port 5000) | Login page loads |
| 7.4 | Dev accessible (port 5001) | Login page loads |
| 7.5 | Prod scan | Opportunities returned |
| 7.6 | Dev scan | Opportunities returned |
| 7.7 | Paper trade on prod | Saved to prod DB |
| 7.8 | Paper trade on dev | Saved to dev DB |
| 7.9 | DB isolation | Prod trade NOT visible on dev |
| 7.10 | Rollback test | Switch to `1.0.1`, old prod works |
