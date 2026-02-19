# Point 1: Database Persistence Strategy — FINALIZED ✅

> **Status:** Approved | **Date:** Feb 17, 2026

---

## Final Decisions

| Decision | Choice |
|----------|--------|
| **Production DB** | **Neon PostgreSQL** (Cloud, free tier, 500MB) |
| **Development DB** | **SQLite** (Local file for speed/offline) |
| **Switching Mechanism** | **Environment Variable** (`DATABASE_URL`) |
| **ORM** | **SQLAlchemy** (Standard in current stack) |
| **Migrations** | **Alembic** (For schema changes) |
| **Data Protection** | **Immutability Flag** (`is_locked=True` on close) |

---

## Why Neon Over Alternatives

| Factor | Neon ✅ | Supabase | AWS RDS | Azure SQL |
|--------|---------|----------|---------|-----------|
| Always free | ✅ | ✅ (pauses after 7 days) | ❌ 12 months | ✅ (complex setup) |
| Lock-in | Minimal — pure PostgreSQL | Moderate — proprietary features | Minimal | Moderate |
| DB branching | ✅ Free | Paid only | ❌ | ❌ |
| Auto-wake | ✅ Scales to zero, wakes on demand | ❌ Must manually unpause | N/A | N/A |

---

## Detailed Implementation Steps

### Step 1.1: Create SQLAlchemy Models
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

### Step 1.2: Update Config
- **File:** `backend/config.py`
- Add `TRADIER_SANDBOX_URL` and `TRADIER_LIVE_URL` constants.
- Implement `get_db_url()` logic to read `DATABASE_URL` env var or default to local SQLite.

### Step 1.3: Create Neon Project
- Sign up at [neon.tech](https://neon.tech).
- Create project `tradeoptions`.
- Get connection string: `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`.
- Add to `.env.production`.

### Step 1.4: Add API Routes
**File:** `backend/app.py`
- `POST /api/trades` (Place trade)
- `GET /api/trades` (List open/closed)
- `GET /api/trades/<id>` (Detail view)
- `PUT /api/settings` (Update configuration)

---

## Migration Plan

1. **Dev:** `alembic revision --autogenerate -m "add paper trade models"`
2. **Dev:** `alembic upgrade head` (updates local SQLite)
3. **Prod:** `export DATABASE_URL=...` → `alembic upgrade head` (updates Neon)
