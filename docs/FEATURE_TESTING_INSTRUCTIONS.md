# Feature Testing Instructions — `feature/ui-improvements` Branch

> **Last Updated:** February 27, 2026  
> **Branch:** `feature/ui-improvements` (ahead of `main` @ `8daaac7`)  
> **Target Release:** `v2.1.0`  
> **Scope:** Trading System Enhancements S1-S5/S7A, Unified BOTH scan, UI bug fixes, App rename  

---

## Overview

This document covers **all changes on the `feature/ui-improvements` branch** that need testing before merging to `main`. The branch contains:

1. **App Rename**: "LEAP Scanner" → "Options Scanner" (17 files)
2. **Unified Scan Direction**: Default `BOTH` (CALL + PUT merged) with direction toggle
3. **6 Trading System Enhancements** (S1-S5, S7A) — proven backtested systems
4. **6 Bug Fixes**: AI verdict colors, empty scan 500→200, logout button, empty ticker guard, score threshold alignment, ticker validation
5. **ARM64 Build Fix**: Removed `pandas-ta` dependency for Raspberry Pi compatibility

---

## Pre-Requisites

### Environment
- Docker running on Raspberry Pi (or local dev machine)
- `.env.feature` file with all API keys configured
- PostgreSQL container running for paper trading DB

### Build & Deploy (on Pi)
```bash
# 1. SSH into Pi
ssh -i ~/.ssh/pikeypair root@192.168.1.244

# 2. Pull the feature branch
cd /home/Options
git fetch origin
git checkout feature/ui-improvements
git pull origin feature/ui-improvements

# 3. Rebuild Docker image
docker build -t horlamy/newscanner:feature-test .

# 4. Stop existing container and start with feature image
docker stop leap_scanner_prod
docker run -d --name leap_scanner_feature \
  -p 5000:5000 \
  --env-file .env.feature \
  -v ./leap_scanner.db:/app/leap_scanner.db \
  horlamy/newscanner:feature-test

# 5. Verify container is running
docker logs --tail 20 leap_scanner_feature
```

### Test Credentials
| User | Password | Purpose |
|------|----------|---------|
| `dev` | `password123` | Primary test account |
| `trader2` | `password123` | Secondary (broker credential testing) |
| `trader3` | `password123` | Multi-user isolation testing |

---

## Test Categories

| # | Category | Tests | Priority |
|---|----------|:-----:|:--------:|
| A | App Rename Verification | 6 | P0 |
| B | Unified BOTH Scan Direction | 8 | P0 |
| C | Trading Systems S1-S5/S7A | 18 | P0 |
| D | Bug Fixes | 8 | P0 |
| E | Regression — Scanner Core | 7 | P1 |
| F | Regression — Paper Trading | 5 | P1 |
| G | Regression — Portfolio & Risk | 4 | P1 |
| H | ARM64 / Docker Build | 3 | P0 |
| **Total** | | **59** | |

---

## Category A: App Rename Verification (6 tests)

Validates "LEAP Scanner" → "Options Scanner" across all user-facing surfaces.

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| A-01 | Login page title | Open login.html, check browser tab | Tab reads "Login - Options Scanner" | ⬜ |
| A-02 | Login page subtitle | Observe login card | Reads "Sign in to access the Options Scanner" | ⬜ |
| A-03 | Dashboard header | Login → observe header h1 | Reads "Options Scanner" (not "LEAP Scanner") | ⬜ |
| A-04 | Dashboard page title | Check browser tab after login | Tab reads "Options Scanner - AI-Powered Options Analysis" | ⬜ |
| A-05 | Console log | Open DevTools → Console → reload | Shows "Options Scanner initialized" (not LEAP) | ⬜ |
| A-06 | No stale references | Ctrl+F "LEAP Scanner" in page source | Zero matches on both login.html and index.html | ⬜ |

**Pass Criteria:** Zero user-visible "LEAP Scanner" text anywhere in the UI.

---

## Category B: Unified BOTH Scan Direction (8 tests)

The scanner now defaults to `BOTH` (CALL + PUT merged results) instead of CALL-only.

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| B-01 | Default direction is BOTH | Load page → observe direction toggle | "📊 Both" button is active (highlighted) | ⬜ |
| B-02 | BOTH scan returns mixed results | Scan AAPL with BOTH selected | Results include both CALL and PUT opportunity cards | ⬜ |
| B-03 | CALL-only filter | Click "📈 CALL" → scan AAPL | Only CALL cards appear, no PUT cards | ⬜ |
| B-04 | PUT-only filter | Click "📉 PUT" → scan AAPL | Only PUT cards appear, no CALL cards | ⬜ |
| B-05 | Direction persists across scans | Set to PUT → scan AAPL → scan MSFT | Both scans return PUT-only results | ⬜ |
| B-06 | BOTH card count ≥ CALL-only | Scan NVDA BOTH, note count. Switch to CALL, scan again | BOTH count ≥ CALL-only count | ⬜ |
| B-07 | Card color coding | Observe BOTH results | CALL cards green-themed, PUT cards red-themed | ⬜ |
| B-08 | API contract: direction param | Check terminal/logs during BOTH scan | Log shows two scan passes (CALL + PUT) merged | ⬜ |

**Pass Criteria:** BOTH mode returns merged CALL+PUT results. Toggle switches are functional. Card styling distinguishes CALL vs PUT.

---

## Category C: Trading System Enhancements S1-S5, S7A (18 tests)

Six proven trading systems integrated into the scan pipeline. Each adds signal data and score adjustments.

### C1: S1 — VIX Regime Detection (5-Tier)

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-01 | VIX regime in logs | Scan any ticker → check terminal | Line: `S1 VIX Regime: XX.X → {CALM/NORMAL/ELEVATED/FEAR/CRISIS}` | ⬜ |
| C-02 | Score penalty applied | Scan during elevated VIX (>20) | Log shows: `S1 Score Penalty: -X, Size Mult: 0.X` | ⬜ |
| C-03 | API response includes VIX data | Check scan JSON response | `trading_systems.vix_regime` object present with `level`, `regime`, `context` | ⬜ |

### C2: S2 — CBOE Put/Call Ratio (Contrarian Sentiment)

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-04 | P/C ratio in logs | Scan any ticker → check terminal | Line: `S2 P/C Ratio: X.XXX (Z=X.XX) → {signal} ({contrarian_bias})` | ⬜ |
| C-05 | Sentiment adjustment | Observe terminal | Line: `S2 Adjusted Sentiment: XX.X → XX.X (+/-X P/C)` | ⬜ |
| C-06 | API response includes P/C | Check scan JSON response | `trading_systems.put_call` object present with `ratio`, `z_score`, `signal` | ⬜ |

### C3: S3 — RSI(2) Mean Reversion

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-07 | RSI(2) in API response | Scan → check JSON response | `trading_systems.rsi2` object present with `value`, `signal`, `score_modifier` | ⬜ |
| C-08 | RSI(2) score modifier | Scan a stock with RSI(2) < 10 or > 90 | Score modifier shows ±points in response | ⬜ |

### C4: S4 — Sector Momentum Rotation

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-09 | Sector ranking in logs | Scan a known sector stock (e.g., AAPL=XLK) | Line: `S4 Sector: Technology (XLK) — Rank #X ({tier}, +/-X)` | ⬜ |
| C-10 | Top sector boost | Scan a stock in a top-3 sector | Positive score modifier in response | ⬜ |
| C-11 | Bottom sector penalty | Scan a stock in a bottom-3 sector | Negative score modifier in response | ⬜ |
| C-12 | API response includes sector | Check scan JSON response | `trading_systems.sector_momentum` object with `rank`, `tier`, `score_modifier` | ⬜ |

### C5: S5 — Minervini Trend Template

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-13 | Minervini in API response | Scan → check JSON response | `trading_systems.minervini` object with `passed`, `criteria`, `score_modifier` | ⬜ |
| C-14 | Strong trend stock | Scan a clearly trending stock | `minervini.passed: true`, positive score modifier | ⬜ |

### C6: S7A — VWAP Levels

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-15 | VWAP in API response | Scan → check JSON response | `trading_systems.vwap` object with `level`, `bias`, `score_modifier` | ⬜ |

### C7: Combined Score Adjustments

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| C-16 | Raw vs adjusted scores | Check scan JSON response | `trading_systems.score_adjustments` shows `technical_raw`, `technical_adjusted`, `sentiment_raw`, `sentiment_adjusted` | ⬜ |
| C-17 | Adjustments affect card display | Compare card scores before/after enabling systems | Score values on cards reflect adjustments from S1-S7A | ⬜ |
| C-18 | Config toggles work | Set `ENABLE_VIX_REGIME=False` in env → scan | No S1 log lines, VIX regime shows as disabled/fallback | ⬜ |

**Pass Criteria:** All 6 trading systems produce log output and API response data. Score adjustments are applied. Config toggles can disable individual systems.

---

## Category D: Bug Fixes (8 tests)

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| D-01 | AI verdict color coding | Scan → trigger AI on a card | Score ≥66 = green, 41-65 = amber, <41 = red (was ≥65/≥40) | ⬜ |
| D-02 | Gate 2 threshold alignment | Click Trade on score 65 card | Shows "⚠️ Proceed with Caution" (amber), not green checkmark | ⬜ |
| D-03 | Empty scan returns 200 | Scan a ticker with no opportunities (e.g., low-liquidity stock) | HTTP 200 with `"error": "No opportunities found"` (was HTTP 500) | ⬜ |
| D-04 | Logout button visible | Login → observe header | "🚪 Logout" link visible in header stats area | ⬜ |
| D-05 | Logout button works | Click Logout | Redirects to login page, session cleared | ⬜ |
| D-06 | Empty ticker guard | Click Scan with empty input field | Toast error "Please enter a ticker symbol" (no API call) | ⬜ |
| D-07 | Invalid ticker rejected | Type "MSTRAAPL" → Scan | Toast error about invalid ticker format | ⬜ |
| D-08 | Ticker format validation | Type "XYZ999" in watchlist add | Error: "Invalid ticker format" (1-5 uppercase letters only) | ⬜ |

**Pass Criteria:** All 6 bug fixes verified. No regression in normal flows.

---

## Category E: Regression — Scanner Core (7 tests)

Re-run core scanner tests to verify no regressions from trading system integration.

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| E-01 | Single ticker weekly scan | Scan AAPL (This Week) | Terminal shows all scan phases, opportunities returned | ⬜ |
| E-02 | Single ticker LEAP scan | Scan JPM (LEAP mode) | LEAP results with delta filter, correct expiry dates | ⬜ |
| E-03 | Sector scan | Technology sector → Scan Top Picks | Batch fetch completes, top 3 get AI analysis | ⬜ |
| E-04 | AI Reasoning Engine | Click "Run AI Analysis" on any card | Spinner → AI analysis text with bull/bear case, verdict, score | ⬜ |
| E-05 | Watchlist operations | Add MSFT → view → remove | All CRUD operations work | ⬜ |
| E-06 | Scan history | Scan AAPL → check history pills | AAPL appears in recent history, clickable for re-scan | ⬜ |
| E-07 | Smart search autocomplete | Type "NV" in search field | Dropdown shows NVDA, NVS, etc. | ⬜ |

---

## Category F: Regression — Paper Trading (5 tests)

Verify paper trading pipeline unaffected by branch changes.

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| F-01 | Place paper trade | Scan → Trade on a card → confirm | Trade appears in Open Positions | ⬜ |
| F-02 | Close paper trade | Click Close on open position | Position moves to Trade History with P&L | ⬜ |
| F-03 | Adjust SL/TP | Click SL/TP adjust on open position | Values update, version increments | ⬜ |
| F-04 | Price snapshots running | Check terminal for snapshot logs | `update_price_snapshots` runs on schedule, updates `current_price` | ⬜ |
| F-05 | Portfolio stats | Navigate to Portfolio | Stat cards show Value, P&L, Positions, Cash from live API | ⬜ |

---

## Category G: Regression — Portfolio & Risk (4 tests)

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| G-01 | Trade History tab | Click Trade History | Summary stats + closed trade rows | ⬜ |
| G-02 | Performance tab | Click Performance | KPI cards, equity chart (if data exists) | ⬜ |
| G-03 | Risk Dashboard | Click Risk tab | Heat %, Win Rate, Tilt Status, Weekly Report | ⬜ |
| G-04 | Settings persistence | Change Max Positions → Save → Reload | Value persists after page reload | ⬜ |

---

## Category H: ARM64 / Docker Build (3 tests)

| ID | Test | Steps | Expected | Status |
|----|------|-------|----------|:------:|
| H-01 | Docker build succeeds | `docker build -t horlamy/newscanner:feature-test .` on Pi | Build completes without errors | ⬜ |
| H-02 | No pandas-ta dependency | Check `requirements.txt` | `pandas-ta` not listed (was causing ARM64 build failure) | ⬜ |
| H-03 | Container starts cleanly | `docker logs --tail 20 leap_scanner_feature` | Flask starts on port 5000, no import errors | ⬜ |

---

## Test Execution Procedure

### Step 1: Build & Deploy
```bash
# On Pi — build and start feature container
docker build -t horlamy/newscanner:feature-test .
docker stop leap_scanner_prod 2>/dev/null
docker run -d --name leap_scanner_feature -p 5000:5000 \
  --env-file .env.feature \
  -v ./leap_scanner.db:/app/leap_scanner.db \
  horlamy/newscanner:feature-test
```

### Step 2: Run Tests in Order
1. **Category H** (Build) — if this fails, stop and fix
2. **Category A** (Rename) — visual verification
3. **Category B** (BOTH scan) — core new feature
4. **Category C** (Trading systems) — new backend logic
5. **Category D** (Bug fixes) — targeted verifications
6. **Category E-G** (Regressions) — ensure nothing broke

### Step 3: Record Results
Update the Status column:
- ✅ = Pass
- ❌ = Fail (note the issue)
- ⬜ = Not tested
- ⏭️ = Skipped (with reason)

### Step 4: Post-Test Actions

**If ALL tests pass:**
```bash
# Stop feature container, restore prod
docker stop leap_scanner_feature
docker rm leap_scanner_feature

# Merge to main
git checkout main
git merge feature/ui-improvements
git tag v2.1.0
git push origin main --tags

# Rebuild prod
docker build -t horlamy/newscanner:latest .
docker run -d --name leap_scanner_prod -p 5000:5000 \
  --env-file .env \
  -v ./leap_scanner.db:/app/leap_scanner.db \
  horlamy/newscanner:latest
```

**If any test fails:**
```bash
# Note the failure, fix on the feature branch
git checkout feature/ui-improvements
# ... fix ...
git commit -m "fix: [description]"

# Rebuild and re-test
docker build -t horlamy/newscanner:feature-test .
docker stop leap_scanner_feature && docker rm leap_scanner_feature
docker run -d --name leap_scanner_feature -p 5000:5000 \
  --env-file .env.feature \
  -v ./leap_scanner.db:/app/leap_scanner.db \
  horlamy/newscanner:feature-test
```

---

## Files Changed on This Branch

### New Files (3)
| File | Purpose |
|------|---------|
| `backend/analysis/regime_detector.py` | S1: VIX 5-tier regime classification |
| `backend/analysis/sector_analysis.py` | S4: Sector momentum rotation ranking |
| `test_trading_systems.py` | Unit tests for all 6 trading systems |

### Modified Files (27)
| File | Changes |
|------|---------|
| `backend/analysis/technical_indicators.py` | Added RSI(2) (S3), Minervini filter (S5), VWAP levels (S7A) |
| `backend/app.py` | BOTH scan logic, ticker validation regex, empty scan 200 response, logout button |
| `backend/config.py` | 6 new `ENABLE_*` config flags for trading systems |
| `backend/services/hybrid_scanner_service.py` | Integrated S1-S5/S7A into LEAP + Sector + Weekly scan paths |
| `frontend/index.html` | Renamed title/header, added BOTH toggle, logout button |
| `frontend/login.html` | Renamed title/subtitle |
| `frontend/js/app.js` | Console log rename |
| `frontend/js/components/opportunities.js` | Score thresholds 65→66, 40→41, verdict color fix |
| `frontend/js/components/scanner.js` | BOTH direction support in API calls |
| `frontend/js/components/watchlist.js` | Watchlist ticker validation |
| `frontend/js/utils/api.js` | Direction parameter in scan API |
| `requirements.txt` | Removed `pandas-ta` for ARM64 compatibility |
| `docs/*` (5 files) | Renamed "LEAP Scanner" → "Options Scanner" |
| `.bat` files (7 files) | Renamed echo text |
| `run.py` | Renamed console banner |

---

## Trading Systems Config Reference

All trading systems are **enabled by default**. To disable during testing, set environment variables:

```bash
# Disable individual systems (set in .env.feature or docker run -e)
ENABLE_VIX_REGIME=False        # S1: VIX 5-tier regime
ENABLE_PUT_CALL_RATIO=False    # S2: P/C ratio contrarian signal
ENABLE_RSI2=False              # S3: RSI(2) mean reversion
ENABLE_SECTOR_MOMENTUM=False   # S4: Sector rotation boost/penalty
ENABLE_MINERVINI_FILTER=False  # S5: Trend template filter
ENABLE_VWAP_LEVELS=False       # S7A: VWAP session levels
```

---

## Automated Test Suite (Backend)

The branch includes `test_trading_systems.py` which can be run standalone:

```bash
# Inside Docker container or local dev
python test_trading_systems.py
```

This validates:
- S1: VIX regime classification thresholds (5 tiers), position sizing, score penalties
- S2: P/C ratio z-score calculation, signal classification, contrarian bias
- S3: RSI(2) extreme detection, score modifier direction
- S4: Sector ETF ranking, tier assignment, score modifier mapping
- S5: Minervini 8-criteria trend template validation
- S7A: VWAP level bias calculation

**Note:** This tests the module logic with synthetic data. Live API integration is tested via Categories B-C above.

---

## Known Limitations

1. **UI-28, UI-30** (profit filters >15%, >35%): Data-dependent — may show no effect if all scanned opportunities exceed threshold
2. **Sector scan timing**: Sector scans use market data that varies throughout the trading day
3. **VIX regime**: During calm markets (VIX < 15), S1 score penalty will be 0 — this is correct behavior
4. **P/C ratio cache**: S2 data is cached for 1 hour — first scan of the day may be slower

---

## Commit History (Branch)

| Hash | Description |
|------|-------------|
| `a3d3794` | refactor: rename LEAP Scanner → Options Scanner across all UI and docs |
| `6e6cdf6` | feat: Trading System Enhancements S1-S5, S7A — 6 proven systems integrated |
| `8ac845f` | feat: Unified scan (BOTH default), AI verdict color coding, 6 bug fixes |
| `8daaac7` | fix: remove unused pandas-ta for ARM64 Pi build compatibility |
| `c25c208` | merge: accept remote requirements.txt, re-apply numpy/pandas-ta fix |
| `e3b4b2c` | fix: remove unused pandas-ta, allow numpy 2.x for ARM64 build |
