# Paper Trade Monitoring — Implementation Plan

> **Branch:** `feature/paper-trading` (off `feature/automated-trading`)  
> **Status:** Planning — Point-by-Point Review  
> **Last Updated:** Feb 19, 2026

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

### Detailed Implementation Steps

#### Step 1.1: Create SQLAlchemy Models
**File:** `backend/database/models.py` — ADD three new model classes:

**1. `PaperTrade` Model** (The core table)
```python
class PaperTrade(Base):
    __tablename__ = 'paper_trades'

    id              = Column(Integer, primary_key=True)
    username        = Column(String(50), nullable=False, index=True)
    idempotency_key = Column(String(100), unique=True)

    # Trade details
    ticker          = Column(String(10), nullable=False)
    option_type     = Column(String(4), nullable=False)   # CALL / PUT
    strike          = Column(Float, nullable=False)
    expiry          = Column(String(10), nullable=False)   # YYYY-MM-DD
    entry_price     = Column(Float, nullable=False)
    entry_date      = Column(DateTime, default=datetime.utcnow)
    qty             = Column(Integer, default=1)

    # Brackets
    sl_price        = Column(Float)
    tp_price        = Column(Float)

    # Scanner context (snapshot at entry)
    strategy        = Column(String(20))
    card_score      = Column(Float)
    ai_score        = Column(Float)
    ai_verdict      = Column(String(20))
    gate_verdict    = Column(String(20))
    technical_score = Column(Float)
    sentiment_score = Column(Float)
    delta_at_entry  = Column(Float)
    iv_at_entry     = Column(Float)

    # Live monitoring
    current_price   = Column(Float)
    last_updated    = Column(DateTime)
    unrealized_pnl  = Column(Float)

    # Outcome
    status          = Column(String(20), default='OPEN')
    close_price     = Column(Float)
    close_date      = Column(DateTime)
    close_reason    = Column(String(20))
    realized_pnl    = Column(Float)
    realized_pnl_pct = Column(Float)
    max_drawdown    = Column(Float)
    max_gain        = Column(Float)
    hold_duration_h = Column(Float)
    override_count  = Column(Integer, default=0)

    # Tradier integration
    broker_mode         = Column(String(20), default='TRADIER_SANDBOX')
    tradier_order_id    = Column(String(50))
    tradier_sl_order_id = Column(String(50))
    tradier_tp_order_id = Column(String(50))
    trigger_precision   = Column(String(20), default='BROKER_FILL')
    broker_fill_price   = Column(Float)
    broker_fill_time    = Column(DateTime)

    # Concurrency + immutability
    version         = Column(Integer, default=1)
    is_locked       = Column(Boolean, default=False)
```

**2. `PriceSnapshot` Model** (For P&L charts)
```python
class PriceSnapshot(Base):
    __tablename__ = 'price_snapshots'

    id          = Column(Integer, primary_key=True)
    trade_id    = Column(Integer, nullable=False, index=True)
    timestamp   = Column(DateTime, default=datetime.utcnow)
    mark_price  = Column(Float)
    bid         = Column(Float)
    ask         = Column(Float)
    delta       = Column(Float)
    iv          = Column(Float)
    underlying  = Column(Float)
```

**3. `UserSettings` Model**
```python
class UserSettings(Base):
    __tablename__ = 'user_settings'

    username            = Column(String(50), primary_key=True)
    broker_mode         = Column(String(20), default='TRADIER_SANDBOX')
    tradier_sandbox_token = Column(String(200))
    tradier_live_token  = Column(String(200))
    tradier_account_id  = Column(String(50))
    account_balance     = Column(Float, default=5000.0)
    max_positions       = Column(Integer, default=5)
    daily_loss_limit    = Column(Float, default=150.0)
    heat_limit_pct      = Column(Float, default=6.0)
    auto_refresh        = Column(Boolean, default=True)
    created_date        = Column(DateTime, default=datetime.utcnow)
    updated_date        = Column(DateTime, default=datetime.utcnow)
```

#### Step 1.2: Update Config
- **File:** `backend/config.py`
- Add `TRADIER_SANDBOX_URL` and `TRADIER_LIVE_URL` constants.
- Implement `get_db_url()` logic to read `DATABASE_URL` env var or default to local SQLite.

#### Step 1.3: Create Neon Project
- Sign up at [neon.tech](https://neon.tech).
- Create project `tradeoptions`.
- Get connection string: `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`.
- Add to `.env.production`.

#### Step 1.4: Add API Routes
**File:** `backend/app.py`
- `POST /api/trades` (Place trade)
- `GET /api/trades` (List open/closed)
- `GET /api/trades/<id>` (Detail view)
- `PUT /api/settings` (Update configuration)

---

# Point 2: Polling & Price Cache ✅ FINALIZED

> **Deep Dive:** [point_2_polling_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_2_polling_deepdive.md)

| Decision | Choice |
|----------|--------|
| Trade execution | Tradier (tick-level SL/TP) |
| Server cron | 60s (Tradier sync) + 40s (ORATS snapshots) |
| Frontend poll | 15s (DB reads) |

### Detailed Implementation Steps

#### Step 2.1: Install APScheduler
- Run: `pip install apscheduler`
- Update `requirements.txt` with `apscheduler>=3.10`.

#### Step 2.2: Create Monitor Service
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

#### Step 2.3: Create Tradier API Client
- **File:** `backend/api/tradier.py`
- Create `TradierAPI` class initialized with Access Token.
- Implement methods: `get_order()`, `get_positions()`, `place_order()`.

#### Step 2.4: Wire Up APScheduler in Flask
- **File:** `backend/app.py`
- Initialize `BackgroundScheduler`.
- Define two jobs:
  - `cron_sync_orders` (Interval: 60s)
  - `cron_price_snapshots` (Interval: 40s)
- Add guard: `if monitor_service.is_market_hours(): ...`

#### Step 2.5: Frontend Polling
- **File:** `frontend/js/components/portfolio.js`
- Implement `startAutoRefresh()` using `setInterval(fetchTrades, 15000)`.
- Add "Auto-refresh: ON/OFF" toggle UI in the refresh bar.

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

### Detailed Implementation Steps

#### Step 3.1: Visual Verification (MOCKUPS FIRST)
- [ ] Generate numbered UI mockups (Tab view, Mobile view, etc.)
- [ ] Present to user for review
- [ ] **HOLD** until approved

#### Step 3.2: Code Structure Updates
- **File:** `frontend/index.html` — Add sub-tab pills, refresh bar, history table container.
- **File:** `frontend/css/index.css` — Add styles for pills, badges, mobile cards, inline expansion.

#### Step 3.3: Refactor `portfolio.js`
- Implement sub-tab switching logic (`currentTab` state: OPEN, HISTORY, PERFORMANCE).
- Fetch real data from `/api/trades?status=OPEN` and `/api/trades?status=CLOSED`.
- Implement `renderOpenPositions()` with inline expansion (slide-down details).
- Implement `renderTradeHistory()` with filtering (Wins, Losses, Expired).
- Wire up "Refresh All" and Auto-refresh toggle.

#### Step 3.4: Add Backend Support
- **File:** `backend/api/routes.py`
- Add `GET /api/trades/history` endpoint (paginated or filtered).
- Add `GET /api/trades/export` endpoint (supports `?format=csv` and `?format=json`).

---

# Point 4: SL/TP Bracket Enforcement ✅ FINALIZED

> **Deep Dive:** [point_4_brackets_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_4_brackets_deepdive.md)

| Decision | Choice |
|----------|--------|
| Execution | **Tradier OCO** (Server-side brackets) |
| Manual Close | **Immediate Cleanup** (Backend fires cancel commands) |
| Confirmation | **Mandatory Modal** ("Are you sure?") |
| Sounds | **Yes** (Profit 💰, Loss 📉, Close 🔵) |

### The 4 Scenarios

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

#### Scenario C: "Adjust SL" (Modify Stop Loss)
- **Action:** User modifies SL price.
- **Logic:** Tradier doesn't support "edit". We must:
  1. Cancel the existing OCO group.
  2. Place a **new** OCO group with the new SL and original TP.
  3. Update DB with new Order IDs.
- **Result:** Same entry price, updated exit plan.

#### Scenario D: "Adjust TP" (Modify Take Profit)
- **Action:** User modifies TP price from $8.00 to $10.00.
- **Logic:**
  1. Cancel the existing OCO group.
  2. Place a **new** OCO group with the new TP and original SL.
- **Result:** Seamless update of upside target.

### Detailed Implementation Steps

#### Step 4.1: Update `MonitorService`
- **File:** `backend/services/monitor_service.py`
- **Task:** Implement `manual_close_position(trade_id)`:
  ```python
  def manual_close_position(self, trade_id):
      trade = self.db.query(PaperTrade).get(trade_id)
      
      # 1. Place Market Sell
      fill = self.tradier.place_order(..., side='sell', type='market')
      
      # 2. IMMEDIATE CLEANUP
      if trade.tradier_sl_order_id:
          self.tradier.cancel_order(trade.tradier_sl_order_id)
      if trade.tradier_tp_order_id:
          self.tradier.cancel_order(trade.tradier_tp_order_id)
          
      # 3. Update DB
      trade.status = 'MANUAL_CLOSE'
      trade.close_price = fill['price']
      return trade
  ```
- **Task:** Add **Orphan Guard** to `sync_tradier_orders` (60s cron):
  - Check for closed positions with open bracket orders → Cancel them.

#### Step 4.2: Frontend Confirmation & Sounds
- **Assets:** Add `pop.mp3`, `cash_register.mp3`, `downer.mp3` to `frontend/assets/sounds/`.
- **File:** `frontend/js/utils/sound.js` — Create helper to play sounds.
- **File:** `frontend/js/components/portfolio.js` — Add `confirm()` check to "Close Position" button:
  ```javascript
  function closePosition(ticker, id) {
      if (!confirm(`Are you sure you want to close ${ticker} at market price?`)) {
          return;
      }
      api.closeTrade(id).then(() => {
          playSound('click');
          showToast(`Closed ${ticker}`);
          refreshPortfolio();
      });
  }
  ```

#### Step 4.3: Backend "Adjust SL/TP" Endpoint
- **File:** `backend/app.py`
- **Task:** Add `POST /api/trades/<id>/adjust` endpoint:
  - Accepts `new_sl` OR `new_tp`.
  - Cancels existing OCO group.
  - Places new OCO group with updated values.
  - Updates DB with new order IDs.

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
