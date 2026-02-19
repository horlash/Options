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
| Dev database | Dockerized PostgreSQL (local) |
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
- Implement `get_db_url()` logic to read `DATABASE_URL` env var or default to local **Dockerized Postgres**.

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

# Point 5: Market Hours & Bookend Snapshots ✅ FINALIZED

> **Deep Dive:** [point_5_market_hours_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_5_market_hours_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Polling Window** | **9:30 AM – 4:00 PM ET** (Strict US/Eastern time) |
| **Pre-Market Snapshot** | **9:25 AM ET** (Capture gap-ups/downs) |
| **Post-Market Snapshot** | **4:05 PM ET** (Official mark-to-market close) |
| **Holidays** | **Ignored for V1** (Polling on holidays is harmless) |
| **Extended Hours** | **Ignored** (Standard equity options only) |

### Detailed Implementation Steps

#### Step 5.1: Timezone Utility
- **File:** `backend/utils/market_hours.py`
- **Task:** Implement `is_market_open()` helper:
  ```python
  from datetime import datetime, time
  import pytz
  
  EASTERN = pytz.timezone('US/Eastern')
  
  def is_market_open():
      now = datetime.now(EASTERN)
      if now.weekday() > 4: return False  # Weekend
      # 9:30 AM to 4:00 PM
      return time(9, 30) <= now.time() <= time(16, 0)
  ```

#### Step 5.2: Configure Scheduler Triggers
- **File:** `backend/app.py`
- **Task:** Use `CronTrigger` with explicit timezone:
  ```python
  from apscheduler.triggers.cron import CronTrigger
  
  # 1. Main Polling (9:30 - 4:00)
  scheduler.add_job(
      monitor.sync_tradier_orders,
      CronTrigger(day_of_week='mon-fri', hour='9-15', minute='*', timezone=EASTERN)
  )
  
  # 2. Pre-Market Bookend (9:25 AM)
  scheduler.add_job(
      monitor.capture_bookend_snapshot,
      CronTrigger(day_of_week='mon-fri', hour=9, minute=25, timezone=EASTERN),
      args=['PRE_MARKET']
  )
  
  # 3. Post-Market Bookend (4:05 PM)
  scheduler.add_job(
      monitor.capture_bookend_snapshot,
      CronTrigger(day_of_week='mon-fri', hour=16, minute=5, timezone=EASTERN),
      args=['POST_MARKET']
  )
  ```

#### Step 5.3: Manual Override
- **task:** Add logic to `is_market_open()` to return `True` if `os.getenv('FORCE_MARKET_OPEN')` is set.

---

# Point 6: Backtesting Data Model & Schema ✅ FINALIZED

> **Deep Dive:** [point_6_backtesting_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_6_backtesting_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Signals** | **Multi-Timeframe** (1m, 5m, 1h, Daily) snapshots |
| **Market Context** | **Regime Aware** (SPY, VIX, Sector Correlations) |
| **Liquidity** | **Order Book State** (Bid/Ask Spread + Greeks) |
| **AI Logic** | **Full Reasoning Log** (Prompt + Output + Confidence) |
| **Targets** | **MFE/MAE/PnL** (Calculated post-trade for ML labeling) |

### 🧱 The "Context-Rich" Data Architecture

We are building a **Time Capsule** for every trade.

#### 1. `signals_snapshot` (The "Micro" View)
```json
{
  "1m": { "rsi": 75, "macd_hist": 0.02, "ema_9_21_cross": "bullish" },
  "5m": { "rsi": 60, "macd_hist": 0.15, "ema_9_21_cross": "bullish" },
  "15m": { "rsi": 55, "squeeze": "firing" },
  "1h": { "trend": "neutral" },
  "daily": { "trend": "bullish", "dist_from_200sma": 5.2 }
}
```

#### 2. `market_regime` (The "Macro" View)
```json
{
  "spy": { "price": 502.50, "pct_change": -0.45, "vix": 18.2 },
  "sector": { "ticker": "XLK", "pct_change": -1.2, "correlation_30d": 0.85 },
  "market_internals": { "ad_line": "declining", "put_call_ratio": 1.15 }
}
```

#### 3. `order_book_state` (Liquidity & Greeks)
```json
{
  "bid": 4.50,
  "ask": 4.60,
  "spread_pct": 2.1,
  "volume": 520,
  "open_interest": 12000,
  "greeks": {
    "delta": 0.35,
    "gamma": 0.04,
    "theta": -0.08,
    "vega": 0.12,
    "iv": 45.5
  }
}
```

### 🧪 Target Variables (ML Labels)

We calculate these **after the trade closes** (Forensic Analysis).
*   `target_pnl_15m`: P&L 15 minutes after entry.
*   `target_pnl_1h`: P&L 1 hour after entry.
*   `target_mae_pct`: **Maximum Adverse Excursion** (Max risk/pain during trade).
*   `target_mfe_pct`: **Maximum Favorable Excursion** (Max potential profit).

### Detailed Implementation Steps

#### Step 6.1: Database Schema Overhaul
- **File:** `backend/database/models.py`
- **Task:** Add `JSONB` columns to `PaperTrade` (Postgres only).

```python
from sqlalchemy.dialects.postgresql import JSONB

class PaperTrade(Base):
    # ... existing fields ...
    
    # Context (Inputs - Captured at Entry)
    signals_snapshot = Column(JSONB)   # Multi-timeframe technicals
    market_regime    = Column(JSONB)   # SPY, VIX, Sector
    order_book_state = Column(JSONB)   # Bid/Ask, Greeks, Liquidity
    ai_reasoning_log = Column(JSONB)   # LLM Inputs/Outputs
    
    # Targets (Outputs - Calculated Post-Close)
    target_pnl_15m   = Column(Float)
    target_pnl_1h    = Column(Float)
    target_mfe_pct   = Column(Float)   # Max potential profit %
    target_mae_pct   = Column(Float)   # Max risk (pain) %
```

#### Step 6.2: "Context Collector" Service
- **File:** `backend/services/context_service.py`
- **Task:** Implement service that runs *at the moment of entry*:
  1.  **get_multi_timeframe_signals(ticker):** Queries the scanner for 1m/5m/1h/D data.
  2.  **get_market_context():** Fetches SPY/VIX and the ticker's Sector ETF (e.g., NVDA -> XLK).
  3.  **get_greeks(option_symbol):** Fetches Delta/Gamma/Theta from Tradier/ORATS.

#### Step 6.3: "Forensic Analyst" Job (Nightly)
- **Task:** dedicated cron job to calculate `target_` variables for closed trades.
  - Queries minute-level price history for the day.
  - Computes MFE/MAE relative to entry price.
  - Updates the `PaperTrade` record.

---

# Point 7: Multi-User Data Isolation ✅ FINALIZED

> **Deep Dive:** [point_7_multi_user_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_7_multi_user_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Dev Database** | **Dockerized PostgreSQL** (No SQLite) |
| **Layer 1 (Schema)** | **`username` Column** on all user tables |
| **Layer 2 (App)** | **Service Layer Isolation** (Mandatory `current_user` filter) |
| **Layer 3 (API)** | **IDOR Protection** (Return 404 on mismatch) |
| **Layer 4 (DB)** | **Row Level Security (RLS)** via SQLAlchemy Event Hooks |

### 🏗️ The Infrastructure Change (Dev/Prod Parity)
**Decision:** We are dropping SQLite for development.
**Reason:** SQLite does not support Row Level Security (RLS). To test Layer 4, we **must** use Postgres in Dev.

### 🧱 The 4-Layer Defense Strategy

#### Layer 1: The Database Schema
Every user-owned table MUST have a `username` column (Indexed).

#### Layer 2: The Application Layer
**Mandatory Service Pattern:**
```python
class TradeService:
    def __init__(self, db, user):
        self.db = db
        self.user = user

    def get_trades(self):
        # Python-side filtering
        return self.db.query(PaperTrade).filter_by(username=self.user.username).all()
```

#### Layer 3: The API Layer (IDOR Protection)
**Rule:** If a user requests a resource ID that belongs to someone else, return `404 Not Found` (Mask existence).

#### Layer 4: Postgres Row Level Security (RLS) 🛡️
**Critical Component for Future-Proofing.**
This moves the security logic *into the database kernel*.

**1. The Database Policy (Migration)**
```sql
-- Enable RLS
ALTER TABLE paper_trades ENABLE ROW LEVEL SECURITY;
-- Create Policy
CREATE POLICY tenant_isolation_policy ON paper_trades
    USING (username = current_setting('app.current_user', true));
```

**2. The SQLAlchemy Integration (The "Messenger")**
We use SQLAlchemy **Events** to inject the user ID into the Postgres session.
```python
# backend/database/session.py
def set_app_user(conn, cursor, ...):
    # This runs before EVERY SQL statement
    from flask import g
    if g.user:
        cursor.execute(f"SET LOCAL app.current_user = '{g.user.username}'")
    else:
        cursor.execute("SET LOCAL app.current_user = 'SYSTEM'")
event.listen(engine, 'before_cursor_execute', set_app_user)
```

### 💾 Automated Backup Strategy
To skip RLS logic during backups (so we get full data):
1.  **Create User:** `backup_service` with `BYPASSRLS` permission.
2.  **Script:** `pg_dump -h host -U backup_service ...`
3.  **Cron:** `0 2 * * * /scripts/backup_db.sh`

---

# Point 8: Multi-Device Session Synchronization ✅ FINALIZED

> **Deep Dive:** [point_8_multi_device_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_8_multi_device_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Strategy** | **Optimistic Locking** (Version Column) |
| **Mechanism** | `UPDATE ... WHERE version=X` (Atomic) |
| **Frontend UX** | **Auto-Refresh** (No errors shown to user) |
| **WebSockets** | **Rejected for V1** (Complexity vs Value trade-off) |

### 🔒 The "Zombie Trade" Prevention

**Scenario:** Laptop closes trade. Phone still shows "Open". User tries to close on Phone.
**Prevention:** Database rejects the update because the version number has changed.

### Detailed Implementation Steps

#### Step 8.1: Schema Update
- **File:** `backend/database/models.py`
- **Task:** Add `version` column to `PaperTrade`.
```python
class PaperTrade(Base):
    # ...
    version = Column(Integer, default=1, nullable=False)
```

#### Step 8.2: Backend "Atomic Check"
- **File:** `backend/services/trade_service.py`
- **Check:** `UPDATE paper_trades ... WHERE id=101 AND version=1`
- **Result:** If `rows_affected == 0`, return `409 Conflict`.

#### Step 8.3: Frontend Warning System
- **File:** `frontend/js/api.js`
- **Interceptor:** Catch `409` status code.
- **Action:**
  1.  Hide Spinner ⏳
  2.  Show Toast: ⚠️ *"Sync Alert: This trade was updated on another device."*
  3.  **Auto-Refresh** the portfolio list.

---

# Points 9-12: PENDING

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
