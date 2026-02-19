# Paper Trading — Implementation Findings & Decision Log

> **Status:** Living Document (updated with each Point implementation)  
> **Branch:** `feature/paper-trading`  
> **Last Updated:** Feb 19, 2026

---

## Table of Contents

- [Point 1: Database Schema](#point-1-database-schema--models)
- [Point 7: Multi-User RLS Isolation](#point-7-multi-user-rls-isolation)
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
```

#### Production (Neon — Future)
```
PAPER_TRADE_DB_URL=postgresql://app_user:xxx@ep-xxx.neon.tech/paper_trading
```
Migrations run via CI/CD with the Neon superuser connection string.

---

*This document is updated after each Point implementation. Future sections will be added for Points 9, 2, 3, 4, etc. as they are built.*
