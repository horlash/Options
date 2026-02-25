"""
Phase 3 Regression Tests: Paper Routes API
===========================================
Tests T-PR-01 through T-PR-09

Integration tests for the /api/paper/* REST endpoints.
Requires: Docker Postgres running (paper_trading DB).
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ─── DB Setup ─────────────────────────────────────────────────
DB_URL = 'postgresql://app_user:app_pass@localhost:5433/paper_trading'

try:
    engine = create_engine(DB_URL, isolation_level='AUTOCOMMIT')
    Session = sessionmaker(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    DB_AVAILABLE = True
except Exception as e:
    DB_AVAILABLE = False
    print(f"\n⚠ Cannot connect to paper_trading DB: {e}")
    print("  Skipping paper routes tests (start Docker Postgres first).\n")

passed = 0
failed = 0
total = 0


def test(test_id, description, func):
    global passed, failed, total
    total += 1
    try:
        func()
        print(f"  PASS {test_id}: {description}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {test_id}: {description}")
        print(f"     Error: {e}")
        failed += 1


def fresh_session(username='test_user'):
    s = Session()
    s.execute(text("BEGIN"))
    s.execute(text(f"SET LOCAL \"app.current_user\" = '{username}'"))
    return s


def cleanup(session):
    try:
        session.execute(text("ROLLBACK"))
    except Exception:
        pass
    session.close()


print("\n" + "=" * 60)
print("Phase 3 Tests: Paper Trading API Routes")
print("=" * 60 + "\n")

if not DB_AVAILABLE:
    print(f"\n{'='*60}")
    print(f"Paper Routes Results: SKIPPED (no DB connection)")
    print(f"{'='*60}")
    sys.exit(0)


# =========================================================================
# T-PR-01: Blueprint imports and has correct prefix
# =========================================================================
def t_pr_01():
    from backend.api.paper_routes import paper_bp
    assert paper_bp.url_prefix == '/api/paper', f"Expected /api/paper, got {paper_bp.url_prefix}"
    assert paper_bp.name == 'paper', f"Expected 'paper', got {paper_bp.name}"

test("T-PR-01", "paper_bp Blueprint has correct name and prefix", t_pr_01)


# =========================================================================
# T-PR-02: _trade_to_dict serializes all expected fields
# =========================================================================
def t_pr_02():
    from backend.api.paper_routes import _trade_to_dict
    from unittest.mock import MagicMock
    from datetime import datetime

    trade = MagicMock()
    trade.id = 1
    trade.ticker = 'NVDA'
    trade.option_type = 'CALL'
    trade.strike = 150.0
    trade.expiry = '2026-06-20'
    trade.direction = 'BUY'
    trade.entry_price = 5.50
    trade.qty = 1
    trade.sl_price = 4.00
    trade.tp_price = 7.00
    trade.strategy = 'LEAP'
    trade.card_score = 85
    trade.ai_score = 90
    trade.ai_verdict = 'BUY'
    trade.gate_verdict = 'PASS'
    trade.technical_score = 75
    trade.sentiment_score = 80
    trade.delta_at_entry = 0.65
    trade.iv_at_entry = 42.0
    trade.current_price = 6.00
    trade.unrealized_pnl = 50.0
    trade.status = 'OPEN'
    trade.exit_price = None
    trade.realized_pnl = None
    trade.close_reason = None
    trade.broker_mode = 'TRADIER_SANDBOX'
    trade.tradier_order_id = None
    trade.version = 1
    trade.created_at = datetime(2026, 2, 18, 10, 0)
    trade.updated_at = datetime(2026, 2, 18, 11, 0)
    trade.closed_at = None

    result = _trade_to_dict(trade)

    expected_keys = {
        'id', 'ticker', 'option_type', 'strike', 'expiry', 'direction',
        'entry_price', 'qty', 'sl_price', 'tp_price', 'strategy',
        'card_score', 'ai_score', 'ai_verdict', 'gate_verdict',
        'technical_score', 'sentiment_score', 'delta_at_entry', 'iv_at_entry',
        'current_price', 'unrealized_pnl', 'status', 'exit_price',
        'realized_pnl', 'close_reason', 'broker_mode', 'tradier_order_id',
        'version', 'created_at', 'updated_at', 'closed_at',
    }
    missing = expected_keys - set(result.keys())
    assert not missing, f"Missing keys: {missing}"
    assert result['ticker'] == 'NVDA'
    assert result['strike'] == 150.0
    assert result['created_at'] == '2026-02-18T10:00:00'

test("T-PR-02", "_trade_to_dict serializes all 30 fields correctly", t_pr_02)


# =========================================================================
# T-PR-03: _snapshot_to_dict serializes price snapshot
# =========================================================================
def t_pr_03():
    from backend.api.paper_routes import _snapshot_to_dict
    from unittest.mock import MagicMock
    from datetime import datetime

    snap = MagicMock()
    snap.id = 1
    snap.trade_id = 42
    snap.timestamp = datetime(2026, 2, 18, 10, 30)
    snap.mark_price = 5.75
    snap.bid = 5.60
    snap.ask = 5.90
    snap.delta = 0.65
    snap.iv = 42.0
    snap.underlying = 148.50
    snap.snapshot_type = 'PERIODIC'

    result = _snapshot_to_dict(snap)

    assert result['mark_price'] == 5.75
    assert result['snapshot_type'] == 'PERIODIC'
    assert result['timestamp'] == '2026-02-18T10:30:00'

test("T-PR-03", "_snapshot_to_dict serializes snapshot correctly", t_pr_03)


# =========================================================================
# T-PR-04: Direct DB — place trade via SQL, verify it's queryable
# =========================================================================
def t_pr_04():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (
                username, ticker, option_type, strike, expiry,
                entry_price, qty, status, direction
            ) VALUES (
                'test_user', 'MSFT', 'CALL', 400.0, '2026-06-20',
                12.00, 1, 'OPEN', 'BUY'
            )
        """))

        result = s.execute(text("""
            SELECT ticker, status, entry_price
            FROM paper_trades
            WHERE username = 'test_user' AND ticker = 'MSFT'
        """)).fetchone()

        assert result is not None, "Trade not found"
        assert result[0] == 'MSFT'
        assert result[1] == 'OPEN'
        assert float(result[2]) == 12.00
    finally:
        cleanup(s)

test("T-PR-04", "Trade INSERT and SELECT via raw SQL works with RLS", t_pr_04)


# =========================================================================
# T-PR-05: RLS isolation — user A can't see user B's trades
# =========================================================================
def t_pr_05():
    s_a = fresh_session('user_alpha')
    try:
        s_a.execute(text("""
            INSERT INTO paper_trades (
                username, ticker, option_type, strike, expiry,
                entry_price, qty, status, direction
            ) VALUES (
                'user_alpha', 'AMZN', 'PUT', 200.0, '2026-06-20',
                8.00, 1, 'OPEN', 'BUY'
            )
        """))

        # Switch context to user_beta
        s_a.execute(text("SET LOCAL \"app.current_user\" = 'user_beta'"))

        count = s_a.execute(text(
            "SELECT COUNT(*) FROM paper_trades WHERE ticker = 'AMZN'"
        )).fetchone()[0]

        assert count == 0, f"user_beta should see 0 trades, saw {count}"
    finally:
        cleanup(s_a)

test("T-PR-05", "RLS isolation: user_beta cannot see user_alpha's trades", t_pr_05)


# =========================================================================
# T-PR-06: Idempotency key prevents duplicate inserts
# =========================================================================
def t_pr_06():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (
                username, ticker, option_type, strike, expiry,
                entry_price, qty, status, direction, idempotency_key
            ) VALUES (
                'test_user', 'GOOG', 'CALL', 180.0, '2026-06-20',
                6.00, 1, 'OPEN', 'BUY', 'idem-phase3-test'
            )
        """))

        raised = False
        try:
            s.execute(text("""
                INSERT INTO paper_trades (
                    username, ticker, option_type, strike, expiry,
                    entry_price, qty, status, direction, idempotency_key
                ) VALUES (
                    'test_user', 'GOOG', 'CALL', 180.0, '2026-06-20',
                    6.00, 1, 'OPEN', 'BUY', 'idem-phase3-test'
                )
            """))
        except Exception:
            raised = True

        assert raised, "Duplicate idempotency_key should raise error"
    finally:
        cleanup(s)

test("T-PR-06", "Idempotency key UNIQUE constraint prevents duplicates", t_pr_06)


# =========================================================================
# T-PR-07: Version column increments correctly
# =========================================================================
def t_pr_07():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (
                username, ticker, option_type, strike, expiry,
                entry_price, qty, status, direction
            ) VALUES (
                'test_user', 'META', 'CALL', 500.0, '2026-06-20',
                15.00, 1, 'OPEN', 'BUY'
            )
        """))

        v1 = s.execute(text(
            "SELECT version FROM paper_trades WHERE ticker = 'META' AND username = 'test_user'"
        )).fetchone()[0]
        assert v1 == 1, f"Expected version=1, got {v1}"

        s.execute(text("""
            UPDATE paper_trades
            SET version = version + 1, sl_price = 12.00
            WHERE ticker = 'META' AND username = 'test_user'
        """))

        v2 = s.execute(text(
            "SELECT version FROM paper_trades WHERE ticker = 'META' AND username = 'test_user'"
        )).fetchone()[0]
        assert v2 == 2, f"Expected version=2 after increment, got {v2}"
    finally:
        cleanup(s)

test("T-PR-07", "Version column starts at 1 and increments correctly", t_pr_07)


# =========================================================================
# T-PR-08: Price snapshots FK constraint links to trade
# =========================================================================
def t_pr_08():
    s = fresh_session()
    try:
        # Insert a trade
        s.execute(text("""
            INSERT INTO paper_trades (
                id, username, ticker, option_type, strike, expiry,
                entry_price, qty, status, direction
            ) VALUES (
                88888, 'test_user', 'TSLA', 'PUT', 300.0, '2026-06-20',
                10.00, 1, 'OPEN', 'BUY'
            )
        """))

        # Insert a snapshot for that trade
        s.execute(text("""
            INSERT INTO price_snapshots (trade_id, mark_price, underlying, snapshot_type, username)
            VALUES (88888, 9.50, 305.00, 'PERIODIC', 'test_user')
        """))

        result = s.execute(text(
            "SELECT mark_price, snapshot_type FROM price_snapshots WHERE trade_id = 88888"
        )).fetchone()

        assert result is not None, "Snapshot not found"
        assert float(result[0]) == 9.50
        assert result[1] == 'PERIODIC'
    finally:
        cleanup(s)

test("T-PR-08", "Price snapshots insert and query with FK to trade", t_pr_08)


# =========================================================================
# T-PR-09: Status CHECK constraint rejects invalid status
# =========================================================================
def t_pr_09():
    s = fresh_session()
    try:
        raised = False
        try:
            s.execute(text("""
                INSERT INTO paper_trades (
                    username, ticker, option_type, strike, expiry,
                    entry_price, qty, status, direction
                ) VALUES (
                    'test_user', 'AMD', 'CALL', 160.0, '2026-06-20',
                    4.00, 1, 'BOGUS', 'BUY'
                )
            """))
        except Exception:
            raised = True

        assert raised, "Should reject invalid status 'BOGUS'"
    finally:
        cleanup(s)

test("T-PR-09", "Status CHECK constraint rejects 'BOGUS' status", t_pr_09)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*60}")
print(f"Paper Routes Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
