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

## Detailed Implementation Steps

### Step 1.1: Create SQLAlchemy Models
- **File:** `backend/database/models.py`
- **Task:** Define the following classes:
    1.  **`PaperTrade`**: The core table.
        - Fields: `id`, `user_id`, `ticker`, `type`, `entry_price`, `sl`, `tp`, `status`, `tradier_order_ids`.
        - Context: `scanner_score`, `ai_score`, `greeks` (at entry).
    2.  **`PriceSnapshot`**: For P&L charts.
        - Fields: `trade_id`, `timestamp`, `mark_price`, `underlying_price`.
    3.  **`UserSettings`**: For API keys and preferences.
        - Fields: `user_id`, `tradier_access_token`, `risk_settings`.

### Step 1.2: Update Config
- **File:** `backend/config.py`
- **Task:** Add `TRADIER_SANDBOX_URL` and `TRADIER_LIVE_URL` constants.
- **Task:** Implement `get_db_url()` logic to read `DATABASE_URL` env var or default to local SQLite.

### Step 1.3: Create Neon Project
- **Action:** Sign up at [neon.tech](https://neon.tech).
- **Action:** Create project `tradeoptions`.
- **Action:** Get connection string: `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require`.
- **Action:** Add to `.env.production` (do not commit to git).

### Step 1.4: Add API Routes
- **File:** `backend/app.py`
- **Task:** Implement CRUD endpoints:
    - `POST /api/trades` (Place trade)
    - `GET /api/trades` (List open/closed)
    - `GET /api/trades/<id>` (Detail view)
    - `PUT /api/settings` (Update configuration)

---

## Schema Design (Reference)

```sql
CREATE TABLE paper_trades (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    ticker VARCHAR(10) NOT NULL,
    option_type VARCHAR(4) CHECK (option_type IN ('CALL', 'PUT')),
    strike NUMERIC(10, 2),
    expiry DATE,
    entry_price NUMERIC(10, 2),
    current_price NUMERIC(10, 2),
    status VARCHAR(20) DEFAULT 'OPEN',
    -- Tradier Integration
    tradier_order_id VARCHAR(50),
    tradier_sl_order_id VARCHAR(50),
    tradier_tp_order_id VARCHAR(50),
    -- Context
    ai_score INT,
    card_score INT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## Migration Plan

1. **Dev:** `alembic revision --autogenerate -m "add paper trade models"`
2. **Dev:** `alembic upgrade head` (updates local SQLite)
3. **Prod:** `export DATABASE_URL=...` → `alembic upgrade head` (updates Neon)
