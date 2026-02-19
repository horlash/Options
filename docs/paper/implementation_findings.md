# Paper Trading — Implementation Findings & Decision Log

> **Status:** Living Document (updated with each Point implementation)  
> **Branch:** `feature/paper-trading`  
> **Last Updated:** Feb 19, 2026 (Point 9 added)

---

## Table of Contents

- [Point 1: Database Schema](#point-1-database-schema--models)
- [Point 7: Multi-User RLS Isolation](#point-7-multi-user-rls-isolation)
- [Point 9: Tradier Integration](#point-9-tradier-integration)
- [Architecture Decisions](#architecture-decisions)

---

## Point 1: Database Schema & Models

**Commit:** `4f09ede` | **Tests:** 10/10 PASS  
**Date:** Feb 19, 2026

### What Was Built

Four PostgreSQL tables via Alembic migration (`001_initial_paper_trading.py`):

| Table | Rows Per User | Purpose | Key Column Count |
|-------|--------------|---------|-----------------|
| `paper_trades` | ~5–50 active | Core trade lifecycle | 35+ columns |
| `state_transitions` | ~3–10 per trade | Audit trail (Point 11) | 7 columns |
| `price_snapshots` | ~50–500 per trade | Price history (Point 2/5) | 10 columns |
| `user_settings` | 1 per user | Broker config + risk | 15 columns |

### Files Created

| File | Purpose |
|------|---------|
| `backend/database/paper_models.py` | SQLAlchemy ORM models for all 4 tables |
| `backend/database/paper_session.py` | Separate Postgres engine/session (isolated from scanner SQLite) |
| `backend/config.py` | Updated with `PAPER_TRADE_DB_URL`, Tradier URLs, `ENCRYPTION_KEY` |
| `docker-compose.paper.yml` | Dev Postgres 16-alpine container |
| `alembic_paper.ini` | Alembic config pointing to `migrations/paper/` |
| `migrations/paper/env.py` | Alembic env with `include_name` filter (only paper tables) |
| `migrations/paper/versions/001_initial_paper_trading.py` | Initial migration |
| `tests/test_point_01_schema.py` | 10 regression tests |

### Design Decisions

#### 1. Separate Database Session
The paper trading system uses its own `paper_session.py` with a **dedicated Postgres engine**, completely independent from the scanner's SQLite database. This is intentional:

- **No risk of migration conflicts** — Alembic `env.py` uses `include_name` to only track paper trading tables
- **Different pooling needs** — Paper trading needs connection pooling (`pool_size=10`, `max_overflow=5`); scanner is single-user SQLite
- **Different isolation levels** — Paper trading uses `REPEATABLE_READ` to prevent phantom reads during concurrent trades

#### 2. JSONB `trade_context` Column
Instead of adding columns for every future analytics field, we use a JSONB column with a GIN index. This supports:

- `strategy_type`, `mfe` (max favorable excursion), `mae` (max adverse excursion)
- Entry/exit snapshots  
- Custom user annotations
- Future fields without schema migrations

**GIN Index:** `CREATE INDEX ix_paper_trades_context_gin ON paper_trades USING GIN (trade_context)` — enables fast queries like `WHERE trade_context @> '{"strategy_type": "momentum"}'`

#### 3. Version Column for Optimistic Locking (Point 8)
Every trade has a `version` integer (default 1). On update, the service will:
```sql
UPDATE paper_trades SET ..., version = version + 1 
WHERE id = :id AND version = :expected_version
```
If `rowcount == 0`, another device/tab modified the trade first → conflict error. This is cheaper than row-level locks for a read-heavy system.

#### 4. Idempotency Key (Point 10)
`idempotency_key` is `UNIQUE` and nullable. When a user submits a trade, the frontend generates a UUID and attaches it. If the request is retried (network issue), the DB rejects the duplicate and the service returns the existing trade. Prevents double-entries.

#### 5. Status CHECK Constraint
The 7-state enum (`PENDING → OPEN → PARTIALLY_FILLED → CLOSING → CLOSED / EXPIRED / CANCELED`) is enforced at the database level:
```sql
CHECK (status IN ('PENDING','OPEN','PARTIALLY_FILLED','CLOSING','CLOSED','EXPIRED','CANCELED'))
```
This prevents invalid states even from direct SQL or buggy code.

### Regression Test Results

| ID | Priority | Description | Result |
|----|----------|-------------|--------|
| T-01-01 | 🔴 | All 4 tables exist with correct columns | ✅ PASS |
| T-01-02 | 🔴 | JSONB trade_context stores/queries data | ✅ PASS |
| T-01-03 | 🔴 | idempotency_key UNIQUE rejects duplicates | ✅ PASS |
| T-01-04 | 🟡 | version defaults to 1 | ✅ PASS |
| T-01-05 | 🔴 | CHECK constraint rejects invalid status | ✅ PASS |
| T-01-06 | 🔴 | CASCADE delete removes child rows | ✅ PASS |
| T-01-07 | 🟡 | Composite index `(username, status)` exists | ✅ PASS |
| T-01-08 | 🟡 | `created_at` auto-populates via `now()` | ✅ PASS |
| T-01-09 | 🟡 | RLS policies exist on `paper_trades` | ✅ PASS |
| T-01-10 | 🟡 | `realized_pnl` accepts negative values | ✅ PASS |

### Bugs / Issues Found

> None — all tests passed on first proper run.

### Known Limitations

1. **No partitioning yet** — if `price_snapshots` grows >10M rows, consider partitioning by `trade_id` or `timestamp`
2. **`expiry` is VARCHAR(10)** — stored as `'YYYY-MM-DD'` string, not a DATE type. This was a deliberate choice to match Tradier's API format and avoid timezone conversion issues. Trade-off: no native date comparisons (will use Python's `datetime.strptime` in the expiry checker).

---

## Point 7: Multi-User RLS Isolation

**Commit:** `b91c53e` | **Tests:** 10/10 PASS  
**Date:** Feb 19, 2026

### What Was Built

PostgreSQL Row Level Security (RLS) ensures complete data isolation between users. Each user can only see, insert, update, and delete their own data.

### Files Created

| File | Purpose |
|------|---------|
| `migrations/paper/versions/002_force_rls.py` | `FORCE ROW LEVEL SECURITY` on all 4 tables |
| `scripts/init-app-user.sql` | Creates `app_user` (NOSUPERUSER) with table permissions |
| `docker-compose.paper.yml` | Updated — mounts init script to `/docker-entrypoint-initdb.d/` |
| `backend/config.py` | Updated — `PAPER_TRADE_DB_URL` now uses `app_user` |
| `tests/test_point_07_rls.py` | 10 isolation tests (alice vs bob) |

### Critical Finding: Superuser Bypass

> [!CAUTION]
> **PostgreSQL superusers bypass ALL Row Level Security policies, including `FORCE ROW LEVEL SECURITY`.**

This was the single most important discovery in Point 7 implementation. Here's what happened:

#### Timeline of Discovery

1. **Initial setup:** Docker's `POSTGRES_USER=paper_user` created `paper_user` as a superuser (this is default Docker Postgres behavior)
2. **Migration 001:** Applied RLS policies with `ENABLE ROW LEVEL SECURITY`
3. **First test run:** Alice saw 10 trades (her 5 + Bob's 5) — **RLS not filtering!**
4. **Added migration 002:** `FORCE ROW LEVEL SECURITY` on all tables
5. **Second test run:** Still 10 trades visible — FORCE didn't help
6. **Root cause query:**
   ```sql
   SELECT current_user, usesuper FROM pg_user WHERE usename = current_user;
   -- Result: paper_user | t    ← SUPERUSER!
   ```
7. **PostgreSQL docs confirmed:** Superusers bypass all RLS, always. `FORCE` only applies to the table owner — but **not if the owner is also a superuser**

#### The Fix: Two-User Architecture

| Role | Type | Purpose |
|------|------|---------|
| `paper_user` | Superuser (table owner) | Runs Alembic migrations, owns schema |
| `app_user` | NOSUPERUSER | Application connects as this user, RLS enforced |

```sql
-- scripts/init-app-user.sql (runs on first Docker start)
CREATE ROLE app_user WITH LOGIN PASSWORD 'app_pass' NOSUPERUSER;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES TO app_user;
```

#### Why This Matters for Production (Neon)

On Neon Postgres, the default user is also a superuser. The same two-user pattern must be applied:
- **Neon superuser** → runs migrations
- **Neon `app_user`** → Flask app connects with this, RLS enforced

This will be documented in the deployment guide when we reach that phase.

### How RLS Works

#### Policy Logic
```sql
-- On paper_trades (direct username match)
CREATE POLICY paper_trades_user_isolation ON paper_trades
    USING (username = current_setting('app.current_user', true))
    WITH CHECK (username = current_setting('app.current_user', true));

-- On state_transitions (join-based)
CREATE POLICY state_transitions_user_isolation ON state_transitions
    USING (trade_id IN (
        SELECT id FROM paper_trades
        WHERE username = current_setting('app.current_user', true)
    ));
```

#### Application Flow
```
Flask Request → middleware sets g.user → SQLAlchemy hook:
    SET LOCAL "app.current_user" = 'alice'
    ↓
    All queries auto-filtered by RLS
    Alice can only see her own data
```

#### PostgreSQL GUC Quoting
Custom session variables with dots (like `app.current_user`) must be quoted in `SET` statements:
```sql
-- ✅ Correct
SET LOCAL "app.current_user" = 'alice';

-- ❌ Wrong (syntax error: "current_user" is a reserved identifier)
SET LOCAL app.current_user = 'alice';
```

But the `current_setting()` function handles this internally:
```sql
-- ✅ Both work in current_setting()
current_setting('app.current_user', true)
```

### Regression Test Results

| ID | Priority | Description | Result |
|----|----------|-------------|--------|
| T-07-01 | 🔴 | Alice sees only her 5 trades (SELECT) | ✅ PASS |
| T-07-02 | 🔴 | Bob cannot see Alice's trades | ✅ PASS |
| T-07-03 | 🔴 | Bob can't INSERT with `username='alice'` (WITH CHECK) | ✅ PASS |
| T-07-04 | 🔴 | Bob's UPDATE on Alice's trades → 0 rows affected | ✅ PASS |
| T-07-05 | 🔴 | Bob's DELETE on Alice's trades → 0 rows affected | ✅ PASS |
| T-07-06 | 🟡 | Alice's data survived Bob's attacks | ✅ PASS |
| T-07-07 | 🔴 | No `app.current_user` set → 0 rows visible | ✅ PASS |
| T-07-08 | 🔴 | Cross-table: Bob can't see Alice's `state_transitions` | ✅ PASS |
| T-07-09 | 🟡 | `FORCE ROW LEVEL SECURITY` enabled on all 4 tables | ✅ PASS |
| T-07-10 | 🟡 | RLS policies exist on all 4 tables | ✅ PASS |

### Bugs / Issues Found

1. **SQLAlchemy `AUTOCOMMIT` + `SET LOCAL` incompatibility** — When using `isolation_level='AUTOCOMMIT'` on the engine, `SET LOCAL` only persists for the single implicit transaction of that statement. By the next `SELECT`, it's gone. Fix: either use `BEGIN`/`COMMIT` manually or use raw `psycopg2` connections (tests use raw psycopg2 for reliability).

2. **GUC quoting** — `SET LOCAL app.current_user = 'x'` fails because PostgreSQL parses `current_user` as the reserved keyword. Must use `SET LOCAL "app.current_user" = 'x'` with double quotes. This affected both `paper_session.py` and all test helpers.

### Known Limitations

1. **No BYPASSRLS backup user yet** — The backup strategy (dedicated `backup_service` role with `GRANT BYPASSRLS`) is documented in the deep dive but not yet implemented. Will be set up with the deployment pipeline.
2. **RLS on `price_snapshots` uses subquery** — The join-based policy (`trade_id IN (SELECT id FROM paper_trades WHERE ...)`) is slower than a direct column match. For high-frequency snapshot inserts, consider adding a `username` column directly to `price_snapshots` in a future migration.

---

## Architecture Decisions

### Decision Log

| # | Decision | Rationale | Date |
|---|----------|-----------|------|
| AD-01 | Separate Postgres from scanner SQLite | No migration conflicts, different pooling/isolation needs | Feb 19 |
| AD-02 | JSONB for trade_context | Flexible schema for analytics without migrations | Feb 19 |
| AD-03 | VARCHAR(10) for expiry instead of DATE | Matches Tradier API format, avoids timezone issues | Feb 19 |
| AD-04 | Two-user Postgres (superuser + app_user) | Superusers bypass all RLS — must use non-super for app | Feb 19 |
| AD-05 | Raw psycopg2 for RLS tests | SQLAlchemy AUTOCOMMIT mode breaks SET LOCAL persistence | Feb 19 |
| AD-06 | `init-app-user.sql` as Docker entrypoint | Auto-creates app_user on first container start | Feb 19 |
| AD-07 | Alembic migrations use superuser | Only superuser can CREATE/ALTER tables and policies | Feb 19 |
| AD-08 | CANCELED trades hard-deleted | No soft delete — reduces noise, keeps schema simple | Feb 19 |
| AD-09 | Provider Pattern (ABC → Concrete → Factory) | Enables future Schwab/IBKR integration without service changes | Feb 19 |
| AD-10 | 30s request timeout for Tradier | Sandbox chains endpoint is slow; 15s caused timeouts | Feb 19 |
| AD-11 | Post-placement order confirmation polling | Tradier "200 OK but rejected" gotcha requires status check | Feb 19 |
| AD-12 | Rate limiter at 50/min (not 60) | 10-call headroom below sandbox limit prevents 429 errors | Feb 19 |
| AD-13 | Fernet encryption for stored tokens | Tokens in DB encrypted at rest; key in env var only | Feb 19 |

### Environment Setup

#### Development
```bash
# 1. Start Postgres
docker compose -f docker-compose.paper.yml up -d

# 2. Run migrations (uses paper_user superuser via alembic_paper.ini)
$env:PYTHONPATH = "."
.venv/Scripts/alembic.exe -c alembic_paper.ini upgrade head

# 3. Run tests (uses app_user non-super for RLS)
.venv/Scripts/python.exe tests/test_point_01_schema.py
.venv/Scripts/python.exe tests/test_point_07_rls.py
.venv/Scripts/python.exe tests/test_point_09_tradier.py
```

#### Production (Neon — Future)
```
PAPER_TRADE_DB_URL=postgresql://app_user:xxx@ep-xxx.neon.tech/paper_trading
```
Migrations run via CI/CD with the Neon superuser connection string.

---

## Point 9: Tradier Integration

**Commit:** (pending) | **Tests:** 13/13 PASS  
**Date:** Feb 19, 2026  
**Sandbox Account:** VA81170223 (Olamide Olasupo, margin, active)

### What Was Built

A complete broker integration layer using the **Provider Pattern**:

```
BrokerProvider (ABC)        → Contract (11 abstract methods)
  └── TradierBroker         → Concrete implementation
       └── BrokerFactory    → Creates broker from UserSettings
```

### Files Created

| File | Purpose |
|------|---------|
| `backend/services/broker/base.py` | `BrokerProvider` ABC (11 methods: quotes, chains, expirations, orders, OCO, cancel, balance, positions, test_connection) |
| `backend/services/broker/tradier.py` | `TradierBroker` — full Tradier API client with rate limiting, retry, confirmation polling |
| `backend/services/broker/factory.py` | `BrokerFactory` — creates broker from UserSettings (decrypts tokens) |
| `backend/services/broker/exceptions.py` | 6 exception types: `BrokerException`, `BrokerAuthException`, `BrokerRateLimitException`, `BrokerOrderRejectedException`, `BrokerInsufficientFundsException`, `BrokerUnavailableException`, `BrokerTimeoutException` |
| `backend/services/broker/__init__.py` | Clean re-exports |
| `backend/security/crypto.py` | `encrypt()` / `decrypt()` using Fernet symmetric encryption |
| `backend/utils/rate_limiter.py` | Thread-safe sliding-window rate limiter (50/min default) |
| `tests/test_point_09_tradier.py` | 13 regression tests hitting live sandbox |

### Live Sandbox Validation

All tests hit the **real Tradier sandbox API** — no mocks:

| Data Point | Value |
|-----------|-------|
| Account holder | Olamide Olasupo |
| Account type | Margin |
| Account status | Active |
| Starting equity | $100,000 |
| AAPL quote | $260.58 (bid $260.45, ask $260.57) |
| Option expirations | 26 available (Feb 2026 → Dec 2028) |
| Option chain | 158 options for nearest expiry |
| Greeks | Available (delta=1.0 for deep ITM) |
| Order placed | ID 25610467 (AAPL buy 1 share, market, pending) |

### Design Decisions

#### 1. Provider Pattern (Broker-Agnostic)
The service layer calls `broker.get_quotes()`, `broker.place_order()` etc. It doesn't know or care if it's talking to Tradier, Schwab, or IBKR. Adding a new broker is just a new class implementing `BrokerProvider`.

#### 2. "200 OK but Rejected" Gotcha
> [!WARNING]
> **Tradier returns HTTP 200 for orders that are later rejected downstream** (margin violations, risk checks, invalid symbols). If you trust the 200, you'll record a trade that never executed.

Fix: `place_order()` automatically waits 1 second then polls `get_order()` to confirm the status isn't `rejected`. If rejected, it raises `BrokerOrderRejectedException` with the rejection reason.

```python
# Inside TradierBroker.place_order()
time.sleep(self.ORDER_CONFIRM_DELAY)  # Wait 1s
confirmation = self._confirm_order(order_id)
if confirmation.get("status") == "rejected":
    raise BrokerOrderRejectedException(...)
```

#### 3. Rate Limiter Strategy
- **Local sliding window:** 50/min (sandbox limit is 60, live is 120 — we use 50 for safety)
- **Tradier header integration:** If `X-Ratelimit-Available` header shows ≤5, we pad our local window to match
- **Thread-safe:** Uses `threading.Lock` for concurrent access

#### 4. Request Retry Strategy
Using `urllib3.util.retry.Retry` adapter:
- **2 retries** on 429, 500, 502, 503
- **Exponential backoff** (1s, 2s)
- **Only for idempotent methods** (GET, DELETE) — POST never retried to prevent double orders

#### 5. Fernet Token Encryption
Tokens stored in `user_settings.tradier_sandbox_token` are encrypted at rest:
```
Plaintext:  8A09vGkj...  (28 chars)
Ciphertext: gAAAAABpl5...  (120+ chars)
```
- Key stored in `ENCRYPTION_KEY` env var only (never in code or DB)
- Invalid key → clear error: "Re-enter your broker credentials"

### Regression Test Results

| ID | Priority | Description | Result |
|----|----------|-------------|--------|
| T-09-01 | 🔴 | Sandbox connection test (profile + account type) | ✅ PASS |
| T-09-02 | 🔴 | Stock quotes (AAPL, MSFT, SPY) with all fields | ✅ PASS |
| T-09-03 | 🔴 | Account balance with equity and buying power | ✅ PASS |
| T-09-04 | 🟡 | Option expirations for AAPL (26 dates) | ✅ PASS |
| T-09-05 | 🔴 | Option chain with greeks (158 options, delta available) | ✅ PASS |
| T-09-06 | 🔴 | Place sandbox market order (buy 1 AAPL) | ✅ PASS |
| T-09-07 | 🔴 | Get order status (confirm placement) | ✅ PASS |
| T-09-08 | 🟡 | Get positions (sandbox may be empty) | ✅ PASS |
| T-09-09 | 🔴 | Auth failure with invalid token → graceful error | ✅ PASS |
| T-09-10 | 🔴 | Fernet encrypt → decrypt round-trip | ✅ PASS |
| T-09-11 | 🟡 | Rate limiter blocks at limit (2.10s for 6 calls) | ✅ PASS |
| T-09-12 | 🟡 | Get all orders returns list | ✅ PASS |
| T-09-13 | 🔴 | Full factory flow: encrypt → store → factory → decrypt → connect | ✅ PASS |

### Bugs / Issues Found

1. **Sandbox chain timeout (15s)** — The `/markets/options/chains` endpoint is slow on the Tradier sandbox (sometimes >15s). Increased `REQUEST_TIMEOUT` from 15s to 30s. This is sandbox-specific; production should be faster.

2. **Sandbox ignores `option_type` filter** — When requesting `option_type=call` on the chains endpoint, the sandbox sometimes returns puts too. The test was made resilient to this by searching for calls within the result rather than assuming the first result is always a call. This is a known sandbox limitation.

3. **Tradier returns dict for single item, list for multiple** — `get_quotes(['AAPL'])` returns a dict, `get_quotes(['AAPL','MSFT'])` returns a list. All handlers now normalize this: `if isinstance(data, dict): data = [data]`.

### Sandbox Gotchas (Documented for Future Reference)

| Gotcha | Impact | Our Mitigation |
|--------|--------|----------------|
| 15-min delayed quotes | Prices stale | Use ORATS for real-time (Point 2) |
| No streaming API | Can't use WebSocket | Polling only (our V1 strategy) |
| Weekly data wipes | Test trades disappear | Our DB is source of truth |
| Slower endpoints | Chains timeout at 15s | Increased to 30s timeout |
| Mixed option types | Filter param ignored | Client-side filtering |
| Tokens not interchangeable | 401 on wrong env | Factory pattern prevents this |

### Known Limitations

1. **OCO orders not yet tested live** — The `place_oco_order()` method is implemented per Tradier docs but not tested against sandbox (requires an open position to exit). Will be tested in Point 4 (Bracket Enforcement).
2. **No WebSocket streaming** — Sandbox doesn't support it. Live streaming will be added in Phase 3 if needed.
3. **No token refresh** — Tradier tokens don't expire (unlike OAuth), so refresh isn't needed. If this changes, add a refresh mechanism.

---

*This document is updated after each Point implementation. Next sections: Phase 2 (UI) and Phase 3 (Engine).*
