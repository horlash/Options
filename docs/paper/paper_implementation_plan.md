# Paper Trade Monitoring — Implementation Plan

> **Branch:** `feature/paper-trading` (off `feature/automated-trading`)  
> **Status:** Planning — Point-by-Point Review  
> **Last Updated:** Feb 18, 2026

---

## Overview

Build a production-grade paper trade monitoring system using **Tradier** for order execution (sandbox for paper, production for live), **Neon PostgreSQL** for persistence, and **ORATS** for price snapshots.

---

# Point 1: Database Persistence ✅ FINALIZED

> **Deep Dive:** [point_1_database_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_1_database_deepdive.md)

| Decision | Choice |
|----------|--------|
| Dev database | SQLite (local) |
| Production database | Neon PostgreSQL (always free, 500MB) |
| Toggle | `DATABASE_URL` env variable |

### Implementation Steps

#### Step 1.1: Create SQLAlchemy Models
**File:** `backend/database/models.py` — ADD three new model classes:
- **`PaperTrade`**: Stores trade details, SL/TP, execution status, and Tradier order IDs.
- **`PriceSnapshot`**: Stores 40s interval price/greeks data for charts.
- **`UserSettings`**: Stores API keys and account preferences.

#### Step 1.2: Update Config
**File:** `backend/config.py` — Add Tradier Sandbox/Live URLs.

#### Step 1.3: Create Neon Project
- Sign up at neon.tech
- Add `DATABASE_URL` to `.env.production`

#### Step 1.4: Add API Routes
**File:** `backend/app.py`
- `POST /api/trades`: Place trade
- `GET /api/trades`: List open/closed trades
- `GET /api/trades/stats`: Performance metrics
- `PUT /api/settings`: Update API keys

---

# Point 2: Polling & Price Cache ✅ FINALIZED

> **Deep Dive:** [point_2_polling_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_2_polling_deepdive.md)

| Decision | Choice |
|----------|--------|
| Trade execution | Tradier (tick-level SL/TP) |
| Server cron | 60s (Tradier sync) + 40s (ORATS snapshots) |
| Frontend poll | 15s (DB reads) |

### Implementation Steps

#### Step 2.1: Install APScheduler
`pip install apscheduler`

#### Step 2.2: Create Monitor Service
**File:** `backend/services/monitor_service.py`
- `sync_tradier_orders()`: Checks for fills/stops at Tradier.
- `update_price_snapshots()`: Fetches ORATS data for open positions.

#### Step 2.3: Create Tradier API Client
**File:** `backend/api/tradier.py`
- Wrapper for Tradier REST API (Place Order, Cancel Order, Get Status).

#### Step 2.4: Wire Up APScheduler
**File:** `backend/app.py`
- Initialize `BackgroundScheduler`.
- Schedule jobs to run only during market hours (9:30-4:00 ET).

#### Step 2.5: Frontend Polling
**File:** `frontend/js/components/portfolio.js`
- `setInterval` to fetch `/api/trades` every 15s.

---

# Point 3: UI Upgrade — Portfolio Tab ✅ FINALIZED

> **Deep Dive:** [point_3_ui_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_3_ui_deepdive.md)

| Decision | Choice |
|----------|--------|
| Location | **Upgrade Existing Portfolio Tab** |
| Sub-Tabs | **Open Positions**, **Trade History**, **Performance** |
| Expansion | **Inline** (slide-down details) |
| Export | **JSON + CSV** |
| **Mandate** | **Visual Verification (Mockups) Required First** |

### Implementation Steps

#### Step 3.1: Visual Verification (MOCKUPS FIRST)
- [ ] Generate numbered UI mockups for user review.
- [ ] **Wait for explicit approval.**

#### Step 3.2: Code Structure Updates
- **`frontend/index.html`**: Add sub-tab selection pills and refresh bar.
- **`frontend/css/index.css`**: CSS for badges, pills, and inline expansion animations.

#### Step 3.3: Refactor `portfolio.js`
- Add state for `currentTab` ('OPEN', 'HISTORY', 'PERFORMANCE').
- `renderOpenPositions()`: Table with inline expansion logic.
- `renderTradeHistory()`: Filterable table of closed trades.

#### Step 3.4: Backend Support
- Add `GET /api/trades/history` endpoint.
- Add `GET /api/trades/export` endpoint.

---

# Point 4: SL/TP Bracket Enforcement ✅ FINALIZED

> **Deep Dive:** [point_4_brackets_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_4_brackets_deepdive.md)

| Decision | Choice |
|----------|--------|
| Execution | **Tradier OCO** (Server-side brackets) |
| Manual Close | **Immediate Cleanup** (Backend fires cancel commands) |
| Confirmation | **Mandatory Modal** ("Are you sure?") |
| Sounds | **Yes** (Profit 💰, Loss 📉, Close 🔵) |

### The 3 Scenarios

#### Scenario A: Clean Bracket Hit (The Happy Path)
- **Action:** Price hits TP ($6.30).
- **Tradier:** Fills TP order, cancels SL order automatically (OCO).
- **System:** Cron detects fill, updates DB to `TP_HIT`, plays "Cha-ching" sound.

#### Scenario B: User Manual Override (The "Panic Close")
- **Action:** User clicks "Close" in UI.
- **Risk:** The SL/TP bracket orders might remain open at Tradier.
- **Solution:**
  1. Backend places Market Sell order.
  2. Backend **IMMEDIATELY** sends `cancel_order` for the orphaned SL/TP legs.
  3. **Orphan Guard:** Cron double-checks every 60s for any missed orphans.

#### Scenario C: "Adjust SL" (Modify Bracket)
- **Action:** User modifies SL price.
- **Logic:** Tradier doesn't support "edit". We must:
  1. Cancel the existing OCO group.
  2. Place a **new** OCO group with the new SL and original TP.
  3. Update DB with new Order IDs.

### Implementation Steps

#### Step 4.1: Update `MonitorService`
- Implement `manual_close_position(trade_id)` with immediate cancel logic.
- Add `orphan_guard()` check to the 60s cron loop.

#### Step 4.2: Frontend Logic
- Add sound assets (`pop.mp3`, `cash_register.mp3`, `downer.mp3`).
- Implement `confirm()` modal on Close button.
- Wire up sound playback on status changes.

#### Step 4.3: Toggle Endpoint
- Add `POST /api/trades/<id>/adjust` to handle Scenario C.

---

# Points 5-12: PENDING

## Point 5: Market Hours & Bookend Snapshots 🔲
**Plan:**
- **Polling Window:** Only run scheduler between 9:30 AM and 4:00 PM ET.
- **Bookends:**
  - **Pre-Market:** Take a snapshot at 9:25 AM to capture gap-ups/downs.
  - **Post-Market:** Take a final snapshot at 4:05 PM to close the day's data.

## Point 6: Backtesting Data Model 🔲
**Plan:** Ensure `PaperTrade` model captures full "Context at Entry" (Scanner scores, Greeks, AI verdict) so we can train future models on "What did we see?" vs "What happened?".

## Point 7: Multi-User Data Isolation 🔲
**Plan:** Add `username` column to all tables. Use a `current_user` context in Flask to automatically filter queries (e.g., `PaperTrade.query.filter_by(username=g.user)`).

## Point 8: Multi-Device Sync 🔲
**Plan:** Use an Optimistic Locking strategy (`version` column). If two devices try to modify a trade, the second one fails if the version doesn't match. Tradier is the ultimate source of truth.

## Point 9: Tradier Integration Architecture 🔲
**Plan:** Create a `BrokerInterface` abstract class. `TradierBroker` implements it. This allows easy swapping between Sandbox and Live modes (or other brokers later).

## Point 10: Concurrency & Race Conditions 🔲
**Plan:** Use database transactions and "Idempotency Keys" for sensitive actions (like placing a trade) to prevent double-execution if the specific request is retried.

## Point 11: Position Lifecycle Management 🔲
**Plan:** Define a strict State Machine: `OPEN` → `PARTIAL` → `FILLED` → `CLOSING` → `CLOSED`. Enforce valid transitions only.

## Point 12: Analytics & Performance Reporting 🔲
**Plan:** A dedicated "Performance" tab calculating Win Rate, Profit Factor, Average Win/Loss, and "Best Strategy" analysis.

---

## Implementation Phases

| Phase | What | Status |
|-------|------|--------|
| Phase 1 | DB Models + Trade Placement + Tradier Client | 🔲 |
| Phase 2 | Portfolio UI (Mockups → Code) | 🔲 |
| Phase 3 | Price Monitoring (Cron + Orphan Guard) | 🔲 |
| Phase 4 | Bracket Logic + Sounds | 🔲 |
| Phase 5 | Analytics Dashboard | 🔲 |
| Phase 6 | Tradier Live Toggle | 🔲 |
| Phase 7 | MCP Knowledge Server | 🔲 |
