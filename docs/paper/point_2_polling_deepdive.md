# Point 2: Polling Frequency & Shared Price Cache — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 18, 2026  
> **Depends On:** Point 1 ✅

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Trade Execution** | **Tradier-First** (Server-side brackets at the broker level) |
| **Server Polling** | **60 Seconds** (Sync order status from Tradier) |
| **Price Data** | **40 Seconds** (Capture ORATS snapshots for P&L curves) |
| **Frontend Polling** | **15 Seconds** (Read from local DB cache, no direct API calls) |
| **Auto-Refresh** | **Enabled by default** (with user toggle) |

---

## 🔄 The Polling Cycle

### 1. The "Heartbeat" (Server Cron)
*   **Frequency:** Every 60 seconds (during market hours).
*   **Job 1 (Order Sync):** Call Tradier API for all open positions.
    *   *Filled?* Update status, set close price, mark as `CLOSED` (immutable).
    *   *Stop Hit?* Tradier handles execution. We just record the result.
*   **Job 2 (Price Snapshots):** Every 40 seconds.
    *   Fetch latest Greeks/Mark from ORATS.
    *   Save to `price_snapshots` table (for charts).
    *   Update `paper_trades.current_price` (for the UI).

### 2. The "View" (Frontend)
*   **Frequency:** Every 15 seconds.
*   **Action:** `GET /api/trades?status=OPEN`
*   **Source:** Reads from **PostgreSQL** (fast, cached). never calls Tradier/ORATS directly.
*   **Benefit:** Zero API rate limit issues, fast UI response.

---

## Detailed Implementation Steps

### Step 2.1: Install APScheduler
- Run: `pip install apscheduler`
- Update `requirements.txt` with `apscheduler>=3.10`.

### Step 2.2: Create Monitor Service
- **File:** `backend/services/monitor_service.py`
- Implement `sync_tradier_orders()`:
  - Query DB for `OPEN` trades with `tradier_order_id`.
  - Call `tradier.get_order(id)`.
  - If status is `filled` or `expired`, update DB record (close price, fill time, reason).
- Implement `update_price_snapshots()`:
  - Fetch ORATS option chain for tickers in open positions.
  - Match specific option contracts.
  - Write new row to `price_snapshots` table.
  - Update `paper_trades` current price and unrealized P&L.

### Step 2.3: Create Tradier API Client
- **File:** `backend/api/tradier.py`
- Create `TradierAPI` class initialized with Access Token.
- Implement methods: `get_order()`, `get_positions()`, `place_order()`.

### Step 2.4: Wire Up APScheduler in Flask
- **File:** `backend/app.py`
- Initialize `BackgroundScheduler`.
- Define two jobs:
  - `cron_sync_orders` (Interval: 60s)
  - `cron_price_snapshots` (Interval: 40s)
- Add guard: `if monitor_service.is_market_hours(): ...`

### Step 2.5: Frontend Polling
- **File:** `frontend/js/components/portfolio.js`
- Implement `startAutoRefresh()` using `setInterval(fetchTrades, 15000)`.
- Add "Auto-refresh: ON/OFF" toggle UI in the refresh bar.

---

## Key Scenarios

| Scenario | Tradier | Server (Cron) | Frontend |
|:---|:---|:---|:---|
| **User Buys Option** | Receives order | Saves `OPEN` trade to DB | Shows "Pending" |
| **Price hits TP** | Executes Sell Order (OCO) | Detects `filled` status | Updates to "Win" 🟢 |
| **Price crashes** | Executes Stop Loss (OCO) | Detects `filled` status | Updates to "Loss" 🔴 |
| **User is Offline** | Handles everything | Updates DB in background | Shows result on next login |
