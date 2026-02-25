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
  - Match specific option contracts using `get_option_quote(ticker, strike, expiry, option_type)`.
  - Write new row to `price_snapshots` table with option-specific bid/ask/mark.
  - Update `paper_trades` current price and unrealized P&L.
  - Uses `get_paper_db_system()` (superuser session) to bypass RLS for cross-user visibility.
  - **Smart after-hours guard (DB-backed):**
    - During market hours: fetch every 40s
    - After hours: check last snapshot timestamp in `price_snapshots` table
    - If last snapshot < today's 4 PM ET → fetch once (closing price)
    - If last snapshot ≥ today's 4 PM ET → skip (already have close, no wasted API calls)

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
- Guard logic handled inside `update_price_snapshots()` (DB-backed, not in scheduler)

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

**Scenario:**
1.  **Laptop:** You close a trade. Profit secured. 💰
2.  **Phone:** You are walking to lunch. The screen still shows the trade as `OPEN` (because it hasn't refreshed yet).
3.  **Panic:** You see it "open" and hit **Close** on your iPhone.

---

### 👁️ The User Experience (What You See)

**Q: "What does the user see?"**
**A: They do NOT see a crash or a "409" error.**

Here is the exact UI flow on the Phone:

1.  **Action:** You tap **[CLOSE POSITION]**.
2.  **Feedback:** The button turns into a **Spinner** ⏳.
3.  **Behind the Scenes:** The API sends the request. The Server returns `409 Conflict`.
4.  **The Intercept:** The JavaScript `api.js` layer catches the 409.
5.  **The Notification:**
    *   The Spinner stops.
    *   A **Toast Notification** (Yellow/Orange) slides down:
    *   ⚠️ *"Sync Alert: This trade was updated on another device."*
6.  **The Auto-Fix:**
    *   The app **automatically refreshes** the list 1 second later.
    *   The "OPEN" trade vanishes from the list.
    *   You see it in "HISTORY" as closed (by your laptop).

**Result:** The user realizes, "Oh, I already closed it," instead of "Why is the system broken?"

---

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

```python
def close_trade(self, trade_id, user_version):
    # Atomic Update: Only works if version matches
    rows = db.query(PaperTrade).filter(
        id=trade_id, 
        version=user_version
    ).update({
        "status": "CLOSED",
        "version": PaperTrade.version + 1
    })
    
    if rows == 0:
        # Check if trade even exists
        if db.query(PaperTrade).get(trade_id):
            # It exists, so it must be a version mismatch
            abort(409) 
```

#### Step 8.3: Frontend Warning System
- **File:** `frontend/js/api.js`

```javascript
async function closeTrade(id, currentVersion) {
    const res = await fetch(`/api/trades/${id}/close`, { ... });

    if (res.status === 409) {
        showToast("⚠️ State changed on another device. Refreshing...", "warning");
        await refreshPortfolio(); // <--- The Magic Fix
        return;
    }
}
```

---

# Point 9: Tradier Integration Architecture ✅ FINALIZED

> **Deep Dive:** [point_9_tradier_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_9_tradier_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Architecture** | **Provider Pattern** (`BrokerProvider` ABC → `TradierBroker`) |
| **Mode Switch** | **Factory Pattern** (`BrokerFactory.get_broker(user)`) |
| **Token Security** | **Fernet Encryption** (Symmetric, key in env vars) |
| **Rate Limiting** | **Token Bucket** (50/min ceiling for safety) |
| **OCO Orders** | **Native Tradier OCO** (`class: oco`, indexed legs) |

### 🌐 Tradier API: The Two Worlds

#### Base URLs
| Environment | Base URL | Purpose |
|-------------|----------|---------|
| **Sandbox** | `https://sandbox.tradier.com/v1/` | Paper trading, testing |
| **Live** | `https://api.tradier.com/v1/` | Real money trading |
| **Streaming** | `https://stream.tradier.com/v1/` | Live only (NOT available in Sandbox) |

#### Authentication
Every request requires a Bearer token in the header:
```
Authorization: Bearer <ACCESS_TOKEN>
```
**⚠️ Critical:** Sandbox tokens and Live tokens are **NOT interchangeable**.
Using a Sandbox token on `api.tradier.com` returns `401 Unauthorized` with:
`"invalid api call as no apiproduct match found"`

---

### 🚦 Rate Limits (Per Token, Per Minute)

| Resource Type | Sandbox | Production |
|--------------|---------|------------|
| **Standard** (`/accounts`, `/orders` GET, `/watchlists`) | 60/min | 120/min |
| **Market Data** (`/markets`) | 60/min | 120/min |
| **Trading** (`/orders` POST, all trade scope) | 60/min | 60/min |

**Response Headers for Monitoring:**
```
X-Ratelimit-Allowed: 120
X-Ratelimit-Used: 15
X-Ratelimit-Available: 105
X-Ratelimit-Expiry: 1709856000
```

#### Rate Limiter Implementation
```python
import time
from collections import deque

class RateLimiter:
    def __init__(self, max_calls=50, period=60):
        # Use 50 instead of 60 to leave headroom
        self.timestamps = deque()
        self.max_calls = max_calls
        self.period = period
    
    def wait(self):
        now = time.time()
        # Remove expired timestamps
        while self.timestamps and now - self.timestamps[0] > self.period:
            self.timestamps.popleft()
        
        if len(self.timestamps) >= self.max_calls:
            sleep_time = self.period - (now - self.timestamps[0])
            time.sleep(sleep_time)
            
        self.timestamps.append(time.time())
```

---

### ⚠️ Error Handling: The "Silent Failure" Gotcha

#### Standard HTTP Errors
| Code | Meaning | Our Response |
|------|---------|-------------|
| `400` | Bad Request (invalid params) | Log + Return user-friendly message |
| `401` | Wrong token or wrong environment | **CRITICAL:** Flag in UI as "Re-authenticate" |
| `403` | Insufficient permissions | Log + Block action |
| `429` | Rate limited | Auto-retry with backoff |
| `500` | Tradier internal error | Retry 2x, then alert |
| `503` | Tradier down/maintenance | Show "Broker Unavailable" banner |

#### 🚨 The Critical Gotcha: "200 OK But Actually Failed"
**Problem:** When you place an order, Tradier returns `200 OK` **immediately**.
But the order might fail downstream (risk management, margin check, etc.).

**The Trap:**
```
POST /v1/accounts/{id}/orders → 200 OK  (You think it worked!)
GET  /v1/accounts/{id}/orders/{order_id} → { "status": "rejected", "errors": ["AccountMarginRuleViolation"] }
```

**The Fix:** We MUST poll the order status after placement.
```python
def place_and_confirm(self, order_request):
    # 1. Place the order
    order_id = self._place_order(order_request)
    
    # 2. Wait briefly for downstream processing
    time.sleep(1)
    
    # 3. Confirm the order status
    order = self._get_order(order_id)
    
    if order['status'] == 'rejected':
        raise BrokerException(
            f"Order rejected: {order.get('errors', 'Unknown reason')}"
        )
    
    return order
```

---

### 🏗️ The Architecture: Provider Pattern

#### 1. The Abstract Base Class (`BrokerProvider`)
Defines the contract. Any broker (Schwab, IBKR) must implement this.

```python
# backend/services/broker/base.py
from abc import ABC, abstractmethod

class BrokerProvider(ABC):
    @abstractmethod
    def get_quotes(self, symbols: list) -> dict:
        """Get current quotes for a list of symbols."""
        pass
    
    @abstractmethod
    def get_option_chain(self, symbol: str, expiry: str) -> dict:
        """Get option chain for a symbol and expiration date."""
        pass

    @abstractmethod
    def place_order(self, order_request: dict) -> str:
        """Place an order. Returns order_id."""
        pass
    
    @abstractmethod
    def place_oco_order(self, leg1: dict, leg2: dict) -> dict:
        """Place a One-Cancels-Other order. Returns both order_ids."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """Get status of an existing order."""
        pass
    
    @abstractmethod
    def get_account_balance(self) -> dict:
        """Get account balance and buying power."""
        pass
```

#### 2. The Concrete Implementation (`TradierBroker`)

```python
# backend/services/broker/tradier.py
import requests

class TradierBroker(BrokerProvider):
    SANDBOX_URL = "https://sandbox.tradier.com/v1"
    LIVE_URL = "https://api.tradier.com/v1"
    
    def __init__(self, access_token, account_id, is_live=False):
        self.token = access_token
        self.account_id = account_id
        self.base_url = self.LIVE_URL if is_live else self.SANDBOX_URL
        self.limiter = RateLimiter(max_calls=50, period=60)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }

    def get_quotes(self, symbols):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/markets/quotes",
            params={"symbols": ",".join(symbols)},
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["quotes"]["quote"]

    def place_order(self, order_request):
        self.limiter.wait()
        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_id}/orders",
            data=order_request,
            headers=self.headers
        )
        self._check_response(resp)
        order_id = resp.json()["order"]["id"]
        
        # CRITICAL: Confirm order wasn't silently rejected
        time.sleep(1)
        confirmation = self.get_order(order_id)
        if confirmation.get("status") == "rejected":
            raise BrokerException(
                f"Order rejected: {confirmation.get('errors')}"
            )
        return order_id

    def place_oco_order(self, sl_order, tp_order):
        """
        Tradier OCO: Two legs, one cancels the other.
        Used for SL/TP brackets (Point 4).
        """
        self.limiter.wait()
        payload = {
            "class": "oco",
            "duration": "gtc",
            # Leg 1: Stop Loss
            "side[0]": "sell_to_close",
            "symbol[0]": sl_order["symbol"],
            "quantity[0]": sl_order["qty"],
            "type[0]": "stop",
            "stop[0]": sl_order["stop_price"],
            # Leg 2: Take Profit
            "side[1]": "sell_to_close",
            "symbol[1]": tp_order["symbol"],
            "quantity[1]": tp_order["qty"],
            "type[1]": "limit",
            "price[1]": tp_order["limit_price"],
        }
        resp = requests.post(
            f"{self.base_url}/accounts/{self.account_id}/orders",
            data=payload,
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["order"]

    def cancel_order(self, order_id):
        self.limiter.wait()
        resp = requests.delete(
            f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
            headers=self.headers
        )
        return resp.status_code == 200

    def get_order(self, order_id):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["order"]

    def get_account_balance(self):
        self.limiter.wait()
        resp = requests.get(
            f"{self.base_url}/accounts/{self.account_id}/balances",
            headers=self.headers
        )
        self._check_response(resp)
        return resp.json()["balances"]
    
    def _check_response(self, resp):
        if resp.status_code == 401:
            raise BrokerAuthException("Invalid or expired token. Re-authenticate.")
        if resp.status_code == 429:
            raise BrokerRateLimitException("Rate limited. Retrying...")
        if resp.status_code >= 400:
            raise BrokerException(f"Tradier Error {resp.status_code}: {resp.text}")
```

---

### 🏭 The Factory: The "Switch"

How does the app know which broker context to use?

```python
# backend/services/broker/factory.py
class BrokerFactory:
    @staticmethod
    def get_broker(user: UserSettings) -> BrokerProvider:
        if user.broker_mode == 'LIVE':
            token = decrypt(user.tradier_live_token)
            is_live = True
        else:
            token = decrypt(user.tradier_sandbox_token)
            is_live = False
            
        return TradierBroker(
            access_token=token,
            account_id=user.tradier_account_id,
            is_live=is_live
        )
```

**Usage in Service Layer:**
```python
# backend/services/trade_service.py
def execute_trade(user, signal):
    broker = BrokerFactory.get_broker(user)  # <--- THE SWITCH
    order_id = broker.place_order({
        "class": "option",
        "symbol": signal["option_symbol"],
        "side": "buy_to_open",
        "quantity": signal["qty"],
        "type": "market",
        "duration": "day"
    })
    return order_id
```

---

### 🔑 Token Security: The "Vault" Strategy

**Problem:** API tokens stored in plain text in the DB = catastrophic if DB leaks.
**Solution:** Symmetric Encryption (Fernet).

```python
# backend/security/crypto.py
from cryptography.fernet import Fernet
import os

cipher = Fernet(os.getenv('ENCRYPTION_KEY'))

def encrypt(token: str) -> str:
    return cipher.encrypt(token.encode()).decode()

def decrypt(token_encrypted: str) -> str:
    return cipher.decrypt(token_encrypted.encode()).decode()
```

**Key Management:**
- `ENCRYPTION_KEY` is stored in Docker environment variables (never in code or DB).
- Generate once: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- Rotate by re-encrypting all tokens with new key during maintenance window.

---

### 🧪 Sandbox Gotchas (Things That Will Bite You)

| Gotcha | Impact | Mitigation |
|--------|--------|------------|
| **15-min delayed quotes** | Prices are stale | Use ORATS for real-time snapshots (Point 2) |
| **No streaming** | Can't use WebSocket feeds | Polling only (already our V1 strategy) |
| **Weekly data wipes** | Test trades disappear | Our DB is the source of truth, not Tradier |
| **Different rate limits** | Sandbox=60/min vs Live=120/min | Use the lower limit (50/min) as our ceiling |
| **Tokens not interchangeable** | Using wrong token = instant 401 | Factory pattern prevents this by design |

---

### 🗂️ File Structure

```
backend/
├── services/
│   └── broker/
│       ├── __init__.py
│       ├── base.py          # BrokerProvider (ABC)
│       ├── tradier.py        # TradierBroker (Concrete)
│       ├── factory.py        # BrokerFactory
│       └── exceptions.py     # BrokerException, BrokerAuthException, etc.
├── security/
│   └── crypto.py             # encrypt() / decrypt()
└── utils/
    └── rate_limiter.py       # RateLimiter class
```

---

# Point 10: Concurrency & Race Conditions ✅ FINALIZED

> **Deep Dive:** [point_10_concurrency_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_10_concurrency_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Double Click** | **Idempotency Keys** (UUID + `UNIQUE` constraint) |
| **Cron Overlap** | **PostgreSQL Advisory Locks** (`pg_try_advisory_lock`) |
| **Simultaneous Adjust** | **Optimistic Locking** (Point 8 `version` column) |
| **Button Spam** | **Disable + Debounce** (Frontend) |
| **Pool Exhaustion** | **SQLAlchemy Pool Config** (`pool_size=10`) |
| **Phantom Read** | **Transaction Isolation** (`REPEATABLE READ`) |

### 🏁 Race Condition #1: The "Double Click" (Idempotency)

**The Problem:** User clicks "Place Trade" on NVDA. Network is slow. They click again.
Without protection, the system places **two identical trades**.

**The Danger:**
- 2x position size (double the risk)
- 2x bracket orders at Tradier
- Confused P&L calculations

#### Frontend: Generate the Key
```javascript
// frontend/js/api.js
async function placeTrade(signal) {
    const idempotencyKey = crypto.randomUUID(); // e.g., "a1b2c3d4-..."
    
    const res = await fetch('/api/trades', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ...signal,
            idempotency_key: idempotencyKey
        })
    });
    
    if (res.status === 409) {
        // Duplicate detected — the first request already went through
        showToast("Trade already placed.", "info");
        return;
    }
    
    return res.json();
}
```

#### Backend: Enforce Uniqueness
```python
# backend/services/trade_service.py
def place_trade(self, signal, idempotency_key):
    # 1. Check if this key already exists
    existing = self.db.query(PaperTrade).filter_by(
        idempotency_key=idempotency_key
    ).first()
    
    if existing:
        # Return the existing trade (idempotent response)
        return existing
    
    # 2. Create the trade
    trade = PaperTrade(
        idempotency_key=idempotency_key,
        ticker=signal['ticker'],
        # ... all other fields ...
    )
    
    try:
        self.db.add(trade)
        self.db.commit()
    except IntegrityError:
        # Race condition: another request snuck in between check and insert
        self.db.rollback()
        return self.db.query(PaperTrade).filter_by(
            idempotency_key=idempotency_key
        ).first()
    
    return trade
```

#### Database: The Safety Net
```python
# backend/database/models.py
class PaperTrade(Base):
    # ...
    idempotency_key = Column(String(100), unique=True, nullable=True)
    #                                       ^^^^^^ THIS IS THE GUARD
```

**Flow:**
1. Click 1 → Key `abc123` → INSERT succeeds → Trade placed ✅
2. Click 2 → Key `abc123` → UNIQUE violation → Return existing trade ✅

---

### 🏁 Race Condition #2: Cron Job Overlap (Scheduler Locking)

**The Problem:** The `sync_tradier_orders` cron runs every 60 seconds.
If one run takes 65 seconds (slow API), the next run starts while the first is still going.
Both runs try to update the same trade → **data corruption**.

**The Danger:**
- Trade gets closed twice
- Bracket orders get double-canceled
- P&L calculated on stale data

#### The Fix: PostgreSQL Advisory Locks

Advisory Locks are lightweight, application-level locks provided by Postgres.
They don't lock rows — they lock a **concept** (identified by a number).

```python
# backend/services/monitor_service.py
LOCK_ID_SYNC_ORDERS = 100001
LOCK_ID_PRICE_SNAPSHOTS = 100002

def sync_tradier_orders(self):
    """Cron job: Sync order statuses from Tradier."""
    conn = self.db.connection()
    
    # Try to acquire lock (non-blocking)
    acquired = conn.execute(
        "SELECT pg_try_advisory_lock(%s)", [LOCK_ID_SYNC_ORDERS]
    ).scalar()
    
    if not acquired:
        # Another instance is already running — skip this cycle
        logger.info("sync_tradier_orders: Skipped (lock held by another instance)")
        return
    
    try:
        # === DO THE ACTUAL WORK ===
        open_trades = self.db.query(PaperTrade).filter_by(status='OPEN').all()
        for trade in open_trades:
            self._sync_single_trade(trade)
        self.db.commit()
    finally:
        # Always release the lock
        conn.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID_SYNC_ORDERS])
```

**Flow:**
1. Cron Run A starts → Acquires lock `100001` → Processing...
2. Cron Run B starts → `pg_try_advisory_lock(100001)` → Returns `false` → **Skips** ✅
3. Cron Run A finishes → Releases lock → Next cron cycle can proceed

---

### 🏁 Race Condition #3: Simultaneous Adjust (Already Solved)

**The Problem:** Phone sends "Adjust SL to $3.00". Laptop sends "Adjust SL to $3.50".
Both hit the server at the same time.

**The Fix: Optimistic Locking (Point 8)**
This is already solved by the `version` column.

```python
# Both requests arrive:
# Phone:  UPDATE ... SET sl_price=3.00 WHERE id=101 AND version=3
# Laptop: UPDATE ... SET sl_price=3.50 WHERE id=101 AND version=3

# Only ONE succeeds (the first to commit).
# The other gets rows_affected=0 → 409 Conflict → Auto-refresh.
```

**No additional code needed.** Point 8's Optimistic Locking handles this.

---

### 🏁 Race Condition #4: Frontend Button Spam (Debounce)

**The Problem:** Even with idempotency keys, we don't want 50 requests hitting the server.
The user is stress-clicking "Close Position" during a market crash.

#### The Fix: Disable + Debounce

```javascript
// frontend/js/components/portfolio.js
async function closePosition(ticker, tradeId, version) {
    const button = document.getElementById(`close-btn-${tradeId}`);
    
    // 1. IMMEDIATELY disable the button
    button.disabled = true;
    button.textContent = "Closing...";
    
    try {
        const result = await api.closeTrade(tradeId, version);
        if (result.success) {
            playSound('click');
            showToast(`Closed ${ticker}`, 'success');
        }
    } catch (err) {
        showToast(`Error: ${err.message}`, 'error');
    } finally {
        // 2. Re-enable after response (success or failure)
        button.disabled = false;
        button.textContent = "Close";
        await refreshPortfolio();
    }
}
```

**Defense Layers:**
1. **Button Disable** → Prevents clicks during flight (instant).
2. **Idempotency Key** → Prevents duplicates even if disable fails (backend).
3. **Optimistic Lock** → Prevents stale actions (database).

---

### 🏁 Race Condition #5: Connection Pool Exhaustion

**The Problem:** Under load (many users, frequent cron jobs), all database connections are in use.
New requests queue up → timeouts → 500 errors.

#### The Fix: SQLAlchemy Pool Configuration

```python
# backend/database/session.py
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # Base number of connections
    max_overflow=5,         # Burst capacity (up to 15 total)
    pool_timeout=30,        # Wait 30s for a connection before error
    pool_recycle=1800,      # Recycle connections every 30 minutes
    pool_pre_ping=True,     # Test connections before using them
)
```

| Parameter | Value | Why |
|-----------|-------|-----|
| `pool_size` | 10 | Enough for 10 concurrent requests |
| `max_overflow` | 5 | Burst to 15 during peak (market open) |
| `pool_timeout` | 30 | Don't wait forever — fail fast |
| `pool_recycle` | 1800 | Neon closes idle connections after 5 min |
| `pool_pre_ping` | True | Avoid "connection already closed" errors |

---

### 🏁 Race Condition #6: The "Phantom Read" (Transaction Isolation)

**The Problem:** Cron job reads: "Trade #101 is OPEN, current_price = $5.00".
Between the read and the write, user manually closes the trade.
Cron job writes: "Trade #101 unrealized_pnl = $50" → **Overwriting the closed status**.

#### The Fix: Transaction Isolation Level

```python
# For critical operations, use REPEATABLE READ isolation
from sqlalchemy.orm import Session

with Session(engine, expire_on_commit=False) as session:
    session.connection(execution_options={
        "isolation_level": "REPEATABLE READ"
    })
    
    trade = session.query(PaperTrade).filter_by(id=101).first()
    
    if trade.status != 'OPEN':
        # Someone closed it while we were processing
        return
    
    trade.unrealized_pnl = calculate_pnl(trade)
    session.commit()  # Will fail if trade was modified by another transaction
```

| Isolation Level | Protection | Use Case |
|----------------|------------|----------|
| `READ COMMITTED` (Default) | No dirty reads | Normal queries |
| `REPEATABLE READ` | No phantom reads | Cron job updates |
| `SERIALIZABLE` | Full isolation | Financial transactions (rare) |

---

### 📋 The Defense Matrix

| Race Condition | Scenario | Fix | Layer |
|---------------|----------|-----|-------|
| Double Click | User clicks "Place Trade" twice | Idempotency Key (UUID) | Frontend + DB |
| Cron Overlap | Two cron instances run simultaneously | Advisory Locks (`pg_try_advisory_lock`) | Database |
| Simultaneous Adjust | Two devices adjust SL at same time | Optimistic Locking (`version` column) | Database |
| Button Spam | User stress-clicks during crash | Button Disable + Debounce | Frontend |
| Pool Exhaustion | Too many concurrent connections | Pool Config (`pool_size=10`) | Infrastructure |
| Phantom Read | Cron overwrites user action | Transaction Isolation (`REPEATABLE READ`) | Database |

---

### 🗂️ Files Affected

```
backend/
├── database/
│   └── session.py            # Pool config + transaction helpers
├── services/
│   ├── trade_service.py      # Idempotency check on place_trade()
│   └── monitor_service.py    # Advisory lock wrapper on cron jobs
frontend/
└── js/
    ├── api.js                # Idempotency key generation
    └── components/
        └── portfolio.js      # Button disable/debounce
```

---

# Point 11: Position Lifecycle Management ✅ FINALIZED

> **Deep Dive:** [point_11_lifecycle_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_11_lifecycle_deepdive.md)

| Decision | Choice |
|----------|--------|
| **States** | 7: PENDING, OPEN, PARTIALLY_FILLED, CLOSING, CLOSED, EXPIRED, CANCELED |
| **Transitions** | Strict whitelist (`InvalidTransitionError` on violation) |
| **Audit** | `state_transitions` table logging every change |
| **Automation** | `lifecycle_sync` cron (60s) |
| **UI Mapping** | Color + icon + badge per state |

### 🔄 The State Machine

#### All Valid States

| State | Meaning | Who Sets It |
|-------|---------|-------------|
| `PENDING` | Order sent to Tradier, not yet filled | App (on place_order) |
| `OPEN` | Order filled, position is live | Cron (on fill confirmation) |
| `PARTIALLY_FILLED` | Multi-leg order, some legs filled | Cron (on partial fill) |
| `CLOSING` | Close order sent, not yet executed | App (on close_position) |
| `CLOSED` | Position fully closed, P&L finalized | Cron (on close confirmation) |
| `EXPIRED` | Option expired worthless (OCC) | Cron (on expiration date) |
| `CANCELED` | Order canceled before fill | App/Cron (on cancel) |

#### State Diagram

```mermaid
stateDiagram-v2
    [*] --> PENDING : User clicks "Place Trade"
    
    PENDING --> OPEN : Tradier confirms fill
    PENDING --> PARTIALLY_FILLED : Some legs filled
    PENDING --> CANCELED : User cancels / Tradier rejects
    
    PARTIALLY_FILLED --> OPEN : Remaining legs filled
    PARTIALLY_FILLED --> CANCELED : User cancels remaining
    
    OPEN --> CLOSING : User clicks "Close" / SL-TP triggered
    OPEN --> EXPIRED : Option hits expiry date at $0
    
    CLOSING --> CLOSED : Tradier confirms close fill
    CLOSING --> OPEN : Close order rejected (retry needed)
    
    CLOSED --> [*]
    EXPIRED --> [*]
    CANCELED --> [*]
```

---

### 🚫 Forbidden Transitions (The "Cannot Happen" Rules)

| From | To | Why It's Forbidden |
|------|----|--------------------|
| `PENDING` | `CLOSED` | Can't close what was never opened |
| `PENDING` | `CLOSING` | Can't close what was never opened |
| `PENDING` | `EXPIRED` | Can't expire what was never opened |
| `CLOSED` | ANY | Terminal state. Nothing changes. |
| `EXPIRED` | ANY | Terminal state. Nothing changes. |
| `CANCELED` | ANY | Terminal state. Nothing changes. |
| `CLOSING` | `PENDING` | Can't go backwards |
| `OPEN` | `PENDING` | Can't go backwards |
| `OPEN` | `CANCELED` | An open position exists — must close, not cancel |

---

### 🛡️ Transition Guards

Each transition has **conditions** that must be true before it's allowed.

| Transition | Guard Condition |
|-----------|-----------------|
| `PENDING → OPEN` | Tradier order status = `filled` AND all legs filled |
| `PENDING → PARTIALLY_FILLED` | Tradier order status = `partially_filled` |
| `PENDING → CANCELED` | Tradier order status = `canceled` OR `rejected` |
| `PARTIALLY_FILLED → OPEN` | All remaining legs now filled |
| `PARTIALLY_FILLED → CANCELED` | User explicitly cancels + unfilled legs canceled at Tradier |
| `OPEN → CLOSING` | Close order successfully placed at Tradier (order_id returned) |
| `OPEN → EXPIRED` | `expiry_date <= today` AND `current_price <= $0.05` (worthless) |
| `CLOSING → CLOSED` | Tradier close order status = `filled` |
| `CLOSING → OPEN` | Tradier close order status = `rejected` (need to retry) |

---

### 💻 Implementation

#### 1. The State Enum

```python
# backend/models/enums.py
import enum

class TradeStatus(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"
```

#### 2. The Transition Map (Code)

```python
# backend/services/lifecycle.py

# Valid transitions: { current_state: [allowed_next_states] }
VALID_TRANSITIONS = {
    TradeStatus.PENDING: [
        TradeStatus.OPEN,
        TradeStatus.PARTIALLY_FILLED,
        TradeStatus.CANCELED,
    ],
    TradeStatus.PARTIALLY_FILLED: [
        TradeStatus.OPEN,
        TradeStatus.CANCELED,
    ],
    TradeStatus.OPEN: [
        TradeStatus.CLOSING,
        TradeStatus.EXPIRED,
    ],
    TradeStatus.CLOSING: [
        TradeStatus.CLOSED,
        TradeStatus.OPEN,  # Close rejected → revert to OPEN
    ],
    # Terminal states — no transitions allowed
    TradeStatus.CLOSED: [],
    TradeStatus.EXPIRED: [],
    TradeStatus.CANCELED: [],
}
```

#### 3. The State Machine Class

```python
# backend/services/lifecycle.py

class LifecycleManager:
    def __init__(self, db_session):
        self.db = db_session
    
    def transition(self, trade: PaperTrade, new_status: TradeStatus, 
                   trigger: str, metadata: dict = None):
        """
        Attempt a state transition. Raises if invalid.
        
        Args:
            trade: The trade to transition
            new_status: Target state
            trigger: What caused this ("user_close", "cron_sync", "sl_triggered")
            metadata: Optional context (e.g., {"tradier_order_id": "12345"})
        """
        old_status = TradeStatus(trade.status)
        
        # 1. Validate the transition
        if new_status not in VALID_TRANSITIONS.get(old_status, []):
            raise InvalidTransitionError(
                f"Cannot transition from {old_status} to {new_status}. "
                f"Allowed: {VALID_TRANSITIONS.get(old_status, [])}"
            )
        
        # 2. Apply the transition
        trade.status = new_status.value
        trade.version += 1  # Optimistic lock (Point 8)
        trade.updated_at = datetime.utcnow()
        
        # 3. Handle terminal state side effects
        if new_status == TradeStatus.CLOSED:
            trade.closed_at = datetime.utcnow()
            trade.realized_pnl = self._calculate_realized_pnl(trade)
        elif new_status == TradeStatus.EXPIRED:
            trade.closed_at = datetime.utcnow()
            trade.realized_pnl = -(trade.entry_price * trade.quantity * 100)
        
        # 4. Log the transition (Audit Trail)
        audit = StateTransition(
            trade_id=trade.id,
            from_status=old_status.value,
            to_status=new_status.value,
            trigger=trigger,
            metadata_json=json.dumps(metadata or {}),
            created_at=datetime.utcnow()
        )
        self.db.add(audit)
        self.db.commit()
        
        return trade
    
    def _calculate_realized_pnl(self, trade):
        """Calculate P&L on close."""
        if trade.direction == 'LONG':
            return (trade.exit_price - trade.entry_price) * trade.quantity * 100
        else:
            return (trade.entry_price - trade.exit_price) * trade.quantity * 100
```

---

### 📝 The Audit Trail

Every state change is recorded. This is critical for debugging and backtesting (Point 6).

#### Audit Table Schema

```python
# backend/database/models.py

class StateTransition(Base):
    __tablename__ = 'state_transitions'
    
    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey('paper_trades.id'), nullable=False)
    from_status = Column(String(25), nullable=False)
    to_status = Column(String(25), nullable=False)
    trigger = Column(String(50), nullable=False)
    # Examples: "user_close", "cron_fill_check", "sl_triggered", "tp_triggered",
    #           "expiry_check", "user_cancel", "tradier_rejected"
    metadata_json = Column(Text, default='{}')
    # Examples: {"tradier_order_id": "12345"}, {"reason": "margin_violation"}
    created_at = Column(DateTime, nullable=False)
    
    trade = relationship("PaperTrade", backref="transitions")
```

#### Example Audit Trail for a Complete Trade

| # | From | To | Trigger | Metadata | Time |
|---|------|----|---------|----------|------|
| 1 | — | PENDING | `user_place` | `{"ticker": "NVDA", "order_id": "T-001"}` | 10:01:00 |
| 2 | PENDING | OPEN | `cron_fill_check` | `{"fill_price": 5.20}` | 10:01:45 |
| 3 | OPEN | CLOSING | `sl_triggered` | `{"sl_price": 4.16, "close_order_id": "T-002"}` | 14:30:22 |
| 4 | CLOSING | CLOSED | `cron_fill_check` | `{"fill_price": 4.10, "pnl": -110.00}` | 14:30:58 |

---

### ⏰ Cron Job Integration: Automatic Transitions

#### The `lifecycle_sync` Cron (runs every 60s)

```python
# backend/services/monitor_service.py

def lifecycle_sync(self):
    """
    Cron: Check all non-terminal trades and update their states.
    Uses Advisory Lock (Point 10) to prevent overlap.
    """
    acquired = self._acquire_lock(LOCK_ID_LIFECYCLE_SYNC)
    if not acquired:
        return
    
    try:
        # --- PENDING trades: check if filled ---
        pending = self.db.query(PaperTrade).filter_by(
            status=TradeStatus.PENDING.value
        ).all()
        
        for trade in pending:
            broker = BrokerFactory.get_broker(trade.user)
            order = broker.get_order(trade.tradier_order_id)
            
            if order['status'] == 'filled':
                trade.entry_price = float(order['avg_fill_price'])
                self.lifecycle.transition(
                    trade, TradeStatus.OPEN, 
                    trigger='cron_fill_check',
                    metadata={'fill_price': trade.entry_price}
                )
            elif order['status'] == 'partially_filled':
                self.lifecycle.transition(
                    trade, TradeStatus.PARTIALLY_FILLED,
                    trigger='cron_fill_check',
                    metadata={'filled_qty': order['filled_quantity']}
                )
            elif order['status'] in ('canceled', 'rejected'):
                self.lifecycle.transition(
                    trade, TradeStatus.CANCELED,
                    trigger='cron_fill_check',
                    metadata={'reason': order.get('reason', 'unknown')}
                )
        
        # --- CLOSING trades: check if close order filled ---
        closing = self.db.query(PaperTrade).filter_by(
            status=TradeStatus.CLOSING.value
        ).all()
        
        for trade in closing:
            broker = BrokerFactory.get_broker(trade.user)
            order = broker.get_order(trade.close_order_id)
            
            if order['status'] == 'filled':
                trade.exit_price = float(order['avg_fill_price'])
                self.lifecycle.transition(
                    trade, TradeStatus.CLOSED,
                    trigger='cron_fill_check',
                    metadata={'fill_price': trade.exit_price}
                )
            elif order['status'] == 'rejected':
                self.lifecycle.transition(
                    trade, TradeStatus.OPEN,
                    trigger='cron_close_rejected',
                    metadata={'reason': order.get('reason', 'unknown')}
                )
        
        # --- OPEN trades: check for expiration ---
        open_trades = self.db.query(PaperTrade).filter(
            PaperTrade.status == TradeStatus.OPEN.value,
            PaperTrade.expiry_date <= date.today()
        ).all()
        
        for trade in open_trades:
            broker = BrokerFactory.get_broker(trade.user)
            quote = broker.get_quotes([trade.option_symbol])
            
            if float(quote['last']) <= 0.05:
                self.lifecycle.transition(
                    trade, TradeStatus.EXPIRED,
                    trigger='cron_expiry_check',
                    metadata={'last_price': quote['last']}
                )
    finally:
        self._release_lock(LOCK_ID_LIFECYCLE_SYNC)
```

---

### 🧊 Edge Cases

#### 1. The "Stuck in CLOSING" Problem
**Scenario:** Close order placed, but Tradier never fills it (illiquid option).
**Fix:** Add a `closing_timeout` (e.g., 30 minutes). If still CLOSING after timeout:
```python
# In lifecycle_sync cron
if trade.status == 'CLOSING':
    time_in_closing = datetime.utcnow() - trade.updated_at
    if time_in_closing > timedelta(minutes=30):
        # Alert the user — manual intervention needed
        send_notification(trade.user, 
            f"⚠️ Close order for {trade.ticker} hasn't filled in 30 min. "
            f"Check Tradier or cancel and retry."
        )
```

#### 2. The "After-Hours Fill" Problem
**Scenario:** User places order at 3:59 PM. Fills at 4:01 PM (after-hours).
**Fix:** We accept the fill regardless. The state machine doesn't care about market hours — only the cron job scheduling does (Point 5). If Tradier fills it, we record it.

#### 3. The "Partial Fill Cancel" Problem
**Scenario:** 5 contracts ordered, 3 filled, user cancels remaining 2.
**Fix:** Transition to OPEN with `quantity` updated to 3.
```python
if order['status'] == 'partially_filled' and user_requested_cancel:
    trade.quantity = order['filled_quantity']
    self.lifecycle.transition(trade, TradeStatus.OPEN, trigger='user_partial_cancel')
```

#### 4. The "Assignment" Problem
**Scenario:** Short option gets assigned by OCC before expiry.
**Fix:** Treat as equivalent to `CLOSED` with the assignment price as exit price.
```python
if order['status'] == 'assigned':
    trade.exit_price = order['assignment_price']
    self.lifecycle.transition(
        trade, TradeStatus.CLOSED,
        trigger='occ_assignment',
        metadata={'assignment_date': order['assignment_date']}
    )
```

---

### 🎨 UI State Mapping

Each state renders differently in the Portfolio tab (Point 3).

| State | Color | Icon | Badge Text | Tab |
|-------|-------|------|------------|-----|
| `PENDING` | 🟡 Yellow | Spinner | "Pending Fill" | Open |
| `OPEN` | 🟢 Green | Active dot | "Live" | Open |
| `PARTIALLY_FILLED` | 🟠 Orange | Half-fill icon | "Partial" | Open |
| `CLOSING` | 🔵 Blue | Spinner | "Closing..." | Open |
| `CLOSED` | ⚪ Gray | Checkmark | "Closed" | History |
| `EXPIRED` | 🔴 Red | X icon | "Expired" | History |
| `CANCELED` | ⚪ Gray | Slash icon | "Canceled" | History |

---

### 🔔 Notifications on State Change

Each transition triggers a user notification (toast + optional sound from Point 4).

| Transition | Notification | Sound |
|-----------|-------------|-------|
| PENDING → OPEN | "✅ {ticker} order filled at ${price}" | `success` |
| PENDING → CANCELED | "❌ {ticker} order was rejected" | `error` |
| OPEN → CLOSING | "🔄 Closing {ticker}..." | `click` |
| CLOSING → CLOSED | "✅ {ticker} closed. P&L: ${pnl}" | `success` or `error` |
| CLOSING → OPEN | "⚠️ Close rejected for {ticker}. Retry needed." | `warning` |
| OPEN → EXPIRED | "💀 {ticker} expired worthless" | `error` |

---

### ✅ Design Decisions (User Confirmed)

| Question | Decision |
|----------|----------|
| Auto-cancel stale PENDING? | **No.** Just poll until filled. No timeout on PENDING. |
| "Close All" batch button? | **No.** Individual close only. |
| Weekend PENDING orders? | **Fine.** They stay PENDING until market opens Monday. |
| Notification on every transition? | **Yes.** Toast + sound per transition. |

---

### 📋 Summary

| Component | Decision |
|-----------|----------|
| **States** | 7 states: PENDING, OPEN, PARTIALLY_FILLED, CLOSING, CLOSED, EXPIRED, CANCELED |
| **Transitions** | Strict whitelist (anything not listed = `InvalidTransitionError`) |
| **Guards** | Conditions checked before each transition |
| **Audit Trail** | `state_transitions` table logs every change |
| **Automation** | `lifecycle_sync` cron handles PENDING→OPEN, CLOSING→CLOSED, OPEN→EXPIRED |
| **Timeout** | CLOSING trades alert user after 30 min (PENDING has no timeout) |
| **Terminal States** | CLOSED, EXPIRED, CANCELED — no further transitions allowed |
| **UI Mapping** | Each state has a distinct color, icon, and tab placement |
| **Notifications** | Toast + sound on every state transition |

---

### 🗂️ Files Affected

```
backend/
├── models/
│   └── enums.py              # TradeStatus enum
├── database/
│   └── models.py             # StateTransition table
├── services/
│   ├── lifecycle.py          # LifecycleManager + VALID_TRANSITIONS
│   └── monitor_service.py    # lifecycle_sync cron job
frontend/
└── js/
    └── components/
        └── portfolio.js      # State-based rendering + notifications
```

---

# Point 12: Analytics & Performance Reporting ✅ FINALIZED

> **Deep Dive:** [point_12_analytics_deepdive.md](file:///C:/Users/olasu/.gemini/antigravity/brain/0f9f0645-7f4b-484c-bb93-cd378257c8d7/point_12_analytics_deepdive.md)

| Decision | Choice |
|----------|--------|
| **Core Metrics** | 10 metrics (Win Rate, Profit Factor, Expectancy, etc.) |
| **SQL Engine** | Raw Postgres with `FILTER` clauses |
| **Charts** | Chart.js (CDN) |
| **Export** | CSV + JSON |
| **Refresh** | Event-driven (on trade close) |

### 🎯 The Goal: "Know If You're Actually Good"
Pretty charts are useless without the right metrics.
This point defines exactly what we measure, how we calculate it, and how we display it.

---

### 📊 Core Metrics: The Numbers That Matter

#### Metric Definitions

| # | Metric | Formula | What It Tells You |
|---|--------|---------|-------------------|
| 1 | **Win Rate** | `wins / total_trades * 100` | % of trades that made money |
| 2 | **Profit Factor** | `gross_profit / gross_loss` | $ won per $ lost (>1.5 = good) |
| 3 | **Expectancy** | `(win_rate * avg_win) - (loss_rate * avg_loss)` | Expected $ per trade |
| 4 | **Avg Win** | `sum(pnl where pnl > 0) / count(wins)` | Mean profit on winners |
| 5 | **Avg Loss** | `sum(pnl where pnl < 0) / count(losses)` | Mean loss on losers |
| 6 | **Largest Win** | `max(pnl)` | Best single trade |
| 7 | **Largest Loss** | `min(pnl)` | Worst single trade |
| 8 | **Avg Hold Time** | `avg(closed_at - created_at)` | How long positions stay open |
| 9 | **Max Drawdown** | `max peak-to-trough decline` | Worst losing streak impact |
| 10 | **Total P&L** | `sum(realized_pnl)` | Net result |

---

### 🗄️ SQL Queries: The Engine Behind Each Metric

#### 1. Summary Stats (Single Query)

```sql
-- backend/queries/analytics.py
SUMMARY_STATS_QUERY = """
SELECT
    COUNT(*) AS total_trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
    COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,
    
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    
    ROUND(
        SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0)), 0), 2
    ) AS profit_factor,
    
    ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric, 2) AS avg_win,
    ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0)::numeric, 2) AS avg_loss,
    
    MAX(realized_pnl) AS largest_win,
    MIN(realized_pnl) AS largest_loss,
    
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    
    AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600)::numeric(10,1) 
        AS avg_hold_hours
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
"""
```

#### 2. Equity Curve (Cumulative P&L Over Time)

```sql
EQUITY_CURVE_QUERY = """
SELECT
    DATE(closed_at) AS trade_date,
    SUM(realized_pnl) AS daily_pnl,
    SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at)) AS cumulative_pnl
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
GROUP BY DATE(closed_at)
ORDER BY trade_date
"""
```

#### 3. Max Drawdown Calculation

```sql
MAX_DRAWDOWN_QUERY = """
WITH equity AS (
    SELECT
        DATE(closed_at) AS trade_date,
        SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at)) AS cumulative_pnl
    FROM paper_trades
    WHERE status IN ('CLOSED', 'EXPIRED')
      AND username = current_setting('app.current_user')
    GROUP BY DATE(closed_at)
),
peaks AS (
    SELECT
        trade_date,
        cumulative_pnl,
        MAX(cumulative_pnl) OVER (ORDER BY trade_date) AS running_peak
    FROM equity
)
SELECT
    MIN(cumulative_pnl - running_peak) AS max_drawdown,
    trade_date AS drawdown_date
FROM peaks
WHERE cumulative_pnl - running_peak < 0
GROUP BY trade_date
ORDER BY max_drawdown ASC
LIMIT 1
"""
```

#### 4. Per-Ticker Breakdown

```sql
TICKER_BREAKDOWN_QUERY = """
SELECT
    ticker,
    COUNT(*) AS trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
GROUP BY ticker
ORDER BY total_pnl DESC
"""
```

#### 5. Per-Strategy Breakdown (Using JSONB context from Point 6)

```sql
STRATEGY_BREAKDOWN_QUERY = """
SELECT
    trade_context->>'strategy_type' AS strategy,
    COUNT(*) AS trades,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric 
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(
        SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0)), 0), 2
    ) AS profit_factor
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
  AND trade_context->>'strategy_type' IS NOT NULL
GROUP BY trade_context->>'strategy_type'
ORDER BY total_pnl DESC
"""
```

#### 6. Monthly P&L Heatmap

```sql
MONTHLY_PNL_QUERY = """
SELECT
    TO_CHAR(closed_at, 'YYYY') AS year,
    TO_CHAR(closed_at, 'Mon') AS month,
    EXTRACT(MONTH FROM closed_at) AS month_num,
    ROUND(SUM(realized_pnl)::numeric, 2) AS monthly_pnl,
    COUNT(*) AS trade_count
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
GROUP BY year, month, month_num
ORDER BY year, month_num
"""
```

#### 7. MFE/MAE Analysis (Point 6 Integration)

```sql
MFE_MAE_QUERY = """
SELECT
    ticker,
    realized_pnl,
    trade_context->>'mfe' AS max_favorable_excursion,
    trade_context->>'mae' AS max_adverse_excursion,
    CASE
        WHEN realized_pnl > 0 AND (trade_context->>'mfe')::numeric > realized_pnl * 1.5
        THEN 'LEFT_MONEY'
        WHEN realized_pnl < 0 AND ABS((trade_context->>'mae')::numeric) > ABS(realized_pnl) * 1.5
        THEN 'HELD_TOO_LONG'
        ELSE 'OPTIMAL'
    END AS exit_quality
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user')
  AND trade_context->>'mfe' IS NOT NULL
ORDER BY closed_at DESC
"""
```

---

### 💻 Backend Service

```python
# backend/services/analytics_service.py

class AnalyticsService:
    def __init__(self, db_session):
        self.db = db_session
    
    def get_summary(self, username: str) -> dict:
        """Get all summary stats for a user."""
        result = self.db.execute(
            text(SUMMARY_STATS_QUERY)
        ).mappings().first()
        
        if not result or result['total_trades'] == 0:
            return self._empty_summary()
        
        # Calculate Expectancy
        win_rate = float(result['win_rate'] or 0) / 100
        avg_win = float(result['avg_win'] or 0)
        avg_loss = abs(float(result['avg_loss'] or 0))
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        return {
            **dict(result),
            'expectancy': round(expectancy, 2),
        }
    
    def get_equity_curve(self, username: str) -> list:
        """Get cumulative P&L data for charting."""
        rows = self.db.execute(
            text(EQUITY_CURVE_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_max_drawdown(self, username: str) -> dict:
        """Get worst peak-to-trough decline."""
        result = self.db.execute(
            text(MAX_DRAWDOWN_QUERY)
        ).mappings().first()
        return dict(result) if result else {'max_drawdown': 0}
    
    def get_ticker_breakdown(self, username: str) -> list:
        """Get per-ticker performance."""
        rows = self.db.execute(
            text(TICKER_BREAKDOWN_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_strategy_breakdown(self, username: str) -> list:
        """Get per-strategy performance."""
        rows = self.db.execute(
            text(STRATEGY_BREAKDOWN_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_monthly_pnl(self, username: str) -> list:
        """Get monthly P&L for heatmap."""
        rows = self.db.execute(
            text(MONTHLY_PNL_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def get_mfe_mae_analysis(self, username: str) -> list:
        """Get exit quality analysis."""
        rows = self.db.execute(
            text(MFE_MAE_QUERY)
        ).mappings().all()
        return [dict(r) for r in rows]
    
    def _empty_summary(self):
        return {
            'total_trades': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0, 'profit_factor': 0, 'expectancy': 0,
            'avg_win': 0, 'avg_loss': 0, 'largest_win': 0,
            'largest_loss': 0, 'total_pnl': 0, 'avg_hold_hours': 0,
        }
```

---

### 🌐 API Endpoints

```python
# backend/routes/analytics.py

@app.route('/api/analytics/summary')
def analytics_summary():
    service = AnalyticsService(db.session)
    return jsonify(service.get_summary(current_user.username))

@app.route('/api/analytics/equity-curve')
def analytics_equity_curve():
    service = AnalyticsService(db.session)
    return jsonify(service.get_equity_curve(current_user.username))

@app.route('/api/analytics/drawdown')
def analytics_drawdown():
    service = AnalyticsService(db.session)
    return jsonify(service.get_max_drawdown(current_user.username))

@app.route('/api/analytics/by-ticker')
def analytics_by_ticker():
    service = AnalyticsService(db.session)
    return jsonify(service.get_ticker_breakdown(current_user.username))

@app.route('/api/analytics/by-strategy')
def analytics_by_strategy():
    service = AnalyticsService(db.session)
    return jsonify(service.get_strategy_breakdown(current_user.username))

@app.route('/api/analytics/monthly')
def analytics_monthly():
    service = AnalyticsService(db.session)
    return jsonify(service.get_monthly_pnl(current_user.username))

@app.route('/api/analytics/mfe-mae')
def analytics_mfe_mae():
    service = AnalyticsService(db.session)
    return jsonify(service.get_mfe_mae_analysis(current_user.username))
```

---

### 🎨 Performance Tab UI Layout

#### Section 1: Summary Cards (Top Row)

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Total P&L│ │ Win Rate │ │ Profit   │ │Expectancy│ │   Max    │
│  +$2,450 │ │  62.5%   │ │ Factor   │ │  +$38.20 │ │ Drawdown │
│  🟢 ▲    │ │  25/40   │ │   1.85   │ │ per trade│ │  -$890   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

Each card shows:
- The metric value (large, bold)
- A subtitle (context)
- Color indicator (green if healthy, red if bad)

#### Section 2: Charts (Middle)

**Chart A: Equity Curve (Line Chart)**
- X-axis: Date
- Y-axis: Cumulative P&L ($)
- Line color: Green when above $0, Red when below
- Shaded area under the line

**Chart B: Monthly P&L Heatmap (Bar Chart)**
- X-axis: Month
- Y-axis: P&L ($)
- Green bars for profit months, Red bars for loss months

**Chart C: Win/Loss Distribution (Histogram)**
- X-axis: P&L buckets (-$500 to +$500 in $50 increments)
- Y-axis: Number of trades
- Shows the shape of your returns

#### Section 3: Breakdown Tables (Bottom)

**Table A: By Ticker**
| Ticker | Trades | Win Rate | Total P&L | Avg P&L |
|--------|--------|----------|-----------|---------|
| NVDA | 12 | 75% | +$1,200 | +$100 |
| AAPL | 8 | 50% | +$320 | +$40 |
| TSLA | 6 | 33% | -$480 | -$80 |

**Table B: By Strategy**
| Strategy | Trades | Win Rate | Profit Factor | Total P&L |
|----------|--------|----------|---------------|-----------|
| Momentum | 15 | 67% | 2.10 | +$1,800 |
| Mean Reversion | 10 | 60% | 1.50 | +$650 |
| Breakout | 5 | 40% | 0.80 | -$200 |

**Table C: MFE/MAE Exit Quality**
| Ticker | P&L | MFE | MAE | Exit Quality |
|--------|-----|-----|-----|-------------|
| NVDA | +$200 | +$450 | -$80 | LEFT_MONEY 🟡 |
| AAPL | -$150 | +$50 | -$300 | HELD_TOO_LONG 🔴 |
| META | +$180 | +$200 | -$30 | OPTIMAL 🟢 |

---

### 📈 Chart Library: Chart.js

We use [Chart.js](https://www.chartjs.org/) — lightweight, no build step, CDN-loadable.

```html
<!-- frontend/index.html -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

#### Equity Curve Implementation

```javascript
// frontend/js/components/performance.js

async function renderEquityCurve() {
    const data = await fetch('/api/analytics/equity-curve').then(r => r.json());
    
    const ctx = document.getElementById('equity-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.map(d => d.trade_date),
            datasets: [{
                label: 'Cumulative P&L',
                data: data.map(d => d.cumulative_pnl),
                borderColor: data.map(d => d.cumulative_pnl >= 0 ? '#22c55e' : '#ef4444'),
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `P&L: $${ctx.parsed.y.toFixed(2)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        callback: (val) => `$${val}`
                    }
                }
            }
        }
    });
}
```

#### Monthly P&L Bar Chart

```javascript
async function renderMonthlyPnl() {
    const data = await fetch('/api/analytics/monthly').then(r => r.json());
    
    const ctx = document.getElementById('monthly-chart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => `${d.month} ${d.year}`),
            datasets: [{
                label: 'Monthly P&L',
                data: data.map(d => d.monthly_pnl),
                backgroundColor: data.map(d => 
                    d.monthly_pnl >= 0 ? '#22c55e' : '#ef4444'
                ),
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    ticks: { callback: (val) => `$${val}` }
                }
            }
        }
    });
}
```

---

### 🔄 Auto-Refresh: When to Update Analytics

Analytics refresh on these triggers:

| Trigger | What Refreshes |
|---------|---------------|
| Trade transitions to CLOSED | Full summary + equity curve |
| Trade transitions to EXPIRED | Full summary + equity curve |
| User opens Performance tab | All data (lazy load) |
| Manual refresh button click | All data |

**No polling needed.** Analytics only change when a trade closes.

```javascript
// frontend/js/components/portfolio.js
// After a trade closes successfully:
if (newStatus === 'CLOSED' || newStatus === 'EXPIRED') {
    // Invalidate analytics cache
    analyticsCache = null;
    
    // If user is on Performance tab, refresh it
    if (currentTab === 'performance') {
        await renderPerformanceDashboard();
    }
}
```

---

### 📤 Export (CSV + JSON)

Users can export their trade history in either format.

#### CSV Export

```python
# backend/routes/analytics.py
import csv
import io

@app.route('/api/analytics/export/csv')
def export_trades_csv():
    trades = _get_closed_trades()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Ticker', 'Direction', 'Entry', 'Exit', 'Qty',
        'P&L', 'Hold Time (hrs)', 'Strategy', 'Opened', 'Closed'
    ])
    
    for t in trades:
        writer.writerow([
            t.ticker, t.direction, t.entry_price, t.exit_price,
            t.quantity, t.realized_pnl,
            round((t.closed_at - t.created_at).total_seconds() / 3600, 1),
            t.trade_context.get('strategy_type', 'N/A'),
            t.created_at.isoformat(), t.closed_at.isoformat()
        ])
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=paper_trades.csv'}
    )
```

#### JSON Export

```python
@app.route('/api/analytics/export/json')
def export_trades_json():
    trades = _get_closed_trades()
    
    data = [{
        'ticker': t.ticker,
        'direction': t.direction,
        'entry_price': float(t.entry_price),
        'exit_price': float(t.exit_price),
        'quantity': t.quantity,
        'realized_pnl': float(t.realized_pnl),
        'hold_time_hours': round(
            (t.closed_at - t.created_at).total_seconds() / 3600, 1
        ),
        'strategy': t.trade_context.get('strategy_type', 'N/A'),
        'status': t.status,
        'opened_at': t.created_at.isoformat(),
        'closed_at': t.closed_at.isoformat(),
        'trade_context': t.trade_context,  # Full JSONB context (MFE/MAE, etc.)
    } for t in trades]
    
    response = jsonify(data)
    response.headers['Content-Disposition'] = 'attachment;filename=paper_trades.json'
    return response


def _get_closed_trades():
    """Shared query for both export formats."""
    return db.session.query(PaperTrade).filter(
        PaperTrade.status.in_(['CLOSED', 'EXPIRED']),
        PaperTrade.username == current_setting('app.current_user')
    ).order_by(PaperTrade.closed_at.desc()).all()
```

#### Frontend Export Buttons

```javascript
// frontend/js/components/performance.js
function exportTradesCSV() {
    window.location.href = '/api/analytics/export/csv';
}

function exportTradesJSON() {
    window.location.href = '/api/analytics/export/json';
}
```

---

### 📋 Summary

| Component | Decision |
|-----------|----------|
| **Core Metrics** | 10 metrics: Win Rate, Profit Factor, Expectancy, Avg Win/Loss, Drawdown, etc. |
| **SQL Engine** | Raw Postgres queries with `FILTER` clauses (no ORM overhead) |
| **Charts** | Chart.js (CDN, no build step) — Equity Curve + Monthly P&L + Distribution |
| **Breakdown** | By Ticker, By Strategy, By Exit Quality (MFE/MAE) |
| **Refresh** | Event-driven (on trade close), not polled |
| **Export** | CSV + JSON download of full trade history |
| **RLS Integration** | All queries use `current_setting('app.current_user')` (Point 7) |
| **Performance** | Raw SQL + lazy loading = fast even with 1000+ trades |

---

### 🗂️ Files Affected

```
backend/
├── queries/
│   └── analytics.py          # All SQL query constants
├── services/
│   └── analytics_service.py  # AnalyticsService class
├── routes/
│   └── analytics.py          # API endpoints + CSV/JSON export
frontend/
├── js/
│   └── components/
│       └── performance.js    # Chart.js rendering + summary cards
└── css/
    └── performance.css       # Performance tab styles
```

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

---

## Test Accounts

Pre-configured test accounts in `backend/users.json` for multi-user testing:

| Username | Password | Purpose |
|----------|----------|---------|
| admin | admin123 | Primary user account |
| trader1 | TestPass1! | Test user 1 |
| trader2 | TestPass2! | Test user 2 |
| trader3 | TestPass3! | Test user 3 |
| demo | demo123 | Demo user |
| bull_trader | BullRun1! | Strategy test user |
| cash_only | CashOnly1! | Zero-positions test user |

## Database Reset (Testing)

During development/testing, you can wipe **all** trades for **all** users:

### Option 1: Batch File (Clickable)
Double-click `reset_paper_db.bat` in the project root.

### Option 2: Command Line
```bash
docker exec paper_trading_db psql -U paper_user -d paper_trading -c "DELETE FROM state_transitions; DELETE FROM paper_trades;"
```

### Option 3: Workflow
Use the `/reset-db` workflow command.

> **Note:** This uses `paper_user` (Postgres superuser) which bypasses RLS, so it clears all users' data across the entire database.

