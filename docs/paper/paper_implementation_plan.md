# Paper Trade Monitoring — Implementation Plan

> **Branch:** `feature/paper-trading` (off `feature/automated-trading`)  
> **Status:** Planning — Point-by-Point Review  
> **Last Updated:** Feb 18, 2026

---

## Overview

Build a production-grade paper trade monitoring system using **Tradier** for order execution (sandbox for paper, production for live), **Neon PostgreSQL** for persistence, and **ORATS** for price snapshots.

---

# Point 1: Database Persistence ✅ FINALIZED

**Deep Dive:** [point_1_database_deepdive.md](./point_1_database_deepdive.md)

| Decision | Choice |
|----------|--------|
| Dev database | SQLite (local) |
| Production database | Neon PostgreSQL (always free, 500MB) |
| Toggle | `DATABASE_URL` env variable |

### Implementation Steps

**Step 1.1** — Create SQLAlchemy models in `backend/database/models.py`:
- `PaperTrade` (40+ fields: trade details, scanner context, Tradier IDs, outcome)
- `PriceSnapshot` (trade_id, mark_price, bid, ask, delta, iv, underlying)
- `UserSettings` (broker_mode, Tradier tokens, limits, preferences)

**Step 1.2** — Update `backend/config.py`: add Tradier URLs

**Step 1.3** — Create Neon project, get connection string, add to `.env.production`

**Step 1.4** — Add API routes to `backend/app.py`:

| Method | Route | Purpose |
|--------|-------|---------|
| POST | `/api/trades` | Place trade → DB + Tradier |
| GET | `/api/trades?status=OPEN` | Open positions |
| GET | `/api/trades?status=CLOSED` | Trade history |
| GET | `/api/trades/<id>` | Trade detail + snapshots |
| PUT | `/api/trades/<id>/close` | Manual close |
| GET | `/api/trades/stats` | Performance metrics |
| GET | `/api/trades/refresh` | Force-refresh prices |
| GET/PUT | `/api/settings` | User settings |

---

# Point 2: Polling & Price Cache ✅ FINALIZED

**Deep Dive:** [point_2_polling_deepdive.md](./point_2_polling_deepdive.md)

| Decision | Choice |
|----------|--------|
| Trade execution | Tradier (sandbox/live) — SL/TP at tick level |
| Server cron | 60s (Tradier sync) + 40s (ORATS snapshots) |
| Frontend poll | 15s (DB reads) |
| Scheduler | APScheduler |

### Implementation Steps

**Step 2.1** — Install APScheduler: `pip install apscheduler`

**Step 2.2** — Create `backend/services/monitor_service.py`:
- `sync_tradier_orders()`: check fills, update DB with exact Tradier data
- `update_price_snapshots()`: ORATS chain fetch, save snapshots, update current_price
- `is_market_hours()`: 9:30-4:00 ET guard

**Step 2.3** — Create `backend/api/tradier.py`:
- `place_order()`, `place_bracket_order()`, `get_order()`, `get_positions()`, `get_account_balance()`

**Step 2.4** — Wire APScheduler in `backend/app.py`:
- 60s job: `sync_tradier_orders()`
- 40s job: `update_price_snapshots()`

**Step 2.5** — Frontend polling in `frontend/js/components/portfolio.js`:
- 15s `setInterval` reading `/api/trades?status=OPEN`
- Start on Portfolio tab active, stop on tab switch

---

# Points 3-12: PENDING

## Point 3: UI Location — Portfolio Tab Upgrade 🔲
Upgrade existing tab with DB-backed data, responsive layout.

## Point 4: SL/TP Bracket Enforcement 🔲
Simplified by Tradier. Sync and display results. Alert queue.

## Point 5: Market Hours & Bookend Snapshots 🔲
9:30-4:00 ET polling. Pre-market 9:25 AM, post-close 4:05 PM.

## Point 6: Backtesting Data Model 🔲
Full context at entry + outcome at close. Schema in Point 1.

## Point 7: Multi-User Data Isolation 🔲
`username` on every table, `@require_user` decorator.

## Point 8: Multi-Device Sync 🔲
Optimistic locking, Tradier as source of truth.

## Point 9: Tradier Integration Architecture 🔲
`BrokerInterface` abstraction. Sandbox ↔ live URL swap.

## Point 10: Concurrency & Race Conditions 🔲
Idempotency keys, transactions, optimistic locking.

## Point 11: Position Lifecycle Management 🔲
OPEN → SL_HIT/TP_HIT/MANUAL_CLOSE/EXPIRED_OTM/EXPIRED_ITM.

## Point 12: Analytics & Performance Reporting 🔲
Win rate, profit factor, AI accuracy, segmented analysis.

---

## Implementation Phases

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | DB Models + Trade Placement + Tradier Client | 🔲 |
| Phase 2 | Portfolio Display (DB-backed) | 🔲 |
| Phase 3 | Price Monitoring (APScheduler cron) | 🔲 |
| Phase 4 | Bracket Sync (Tradier order status) | 🔲 |
| Phase 5 | Analytics Dashboard | 🔲 |
| Phase 6 | Tradier Live Toggle | 🔲 |
| Phase 7 | MCP Knowledge Server | 🔲 |
