"""
Regression Tests for Point 1: Database Schema
==============================================
Tests T-01-01 through T-01-10 from regression_testing_plan.md
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Test database URL
DB_URL = 'postgresql://paper_user:paper_pass@localhost:5432/paper_trading'

engine = create_engine(DB_URL, isolation_level='AUTOCOMMIT')
Session = sessionmaker(bind=engine)

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
    """Create a fresh session with RLS user context set."""
    s = Session()
    s.execute(text("BEGIN"))
    s.execute(text(f"SET LOCAL \"app.current_user\" = '{username}'"))
    return s


def cleanup(session):
    """Rollback and close to clean up test data."""
    try:
        session.execute(text("ROLLBACK"))
    except Exception:
        pass
    session.close()


# =========================================================================
# T-01-01: paper_trades table exists with correct columns
# =========================================================================
def t_01_01():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert 'paper_trades' in tables, f"paper_trades not found. Tables: {tables}"
    assert 'state_transitions' in tables, f"state_transitions not found"
    assert 'price_snapshots' in tables, f"price_snapshots not found"
    assert 'user_settings' in tables, f"user_settings not found"

    columns = {c['name'] for c in inspector.get_columns('paper_trades')}
    required = {
        'id', 'username', 'idempotency_key', 'ticker', 'option_type',
        'strike', 'expiry', 'direction', 'entry_price', 'qty',
        'sl_price', 'tp_price', 'strategy', 'card_score', 'ai_score',
        'ai_verdict', 'gate_verdict', 'technical_score', 'sentiment_score',
        'delta_at_entry', 'iv_at_entry', 'current_price', 'unrealized_pnl',
        'status', 'exit_price', 'realized_pnl', 'close_reason',
        'trade_context', 'broker_mode', 'tradier_order_id',
        'tradier_sl_order_id', 'tradier_tp_order_id',
        'broker_fill_price', 'broker_fill_time',
        'version', 'is_locked', 'created_at', 'updated_at', 'closed_at',
    }
    missing = required - columns
    assert not missing, f"Missing columns: {missing}"

test("T-01-01", "paper_trades table exists with all columns", t_01_01)


# =========================================================================
# T-01-02: JSONB trade_context stores arbitrary data
# =========================================================================
def t_01_02():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, trade_context)
            VALUES ('test_user', 'NVDA', 'CALL', 150.0, '2026-06-20', 5.50,
                    '{"strategy_type": "momentum", "mfe": 150}'::jsonb)
        """))
        result = s.execute(text("""
            SELECT trade_context->>'strategy_type' AS strat
            FROM paper_trades WHERE ticker = 'NVDA' AND username = 'test_user'
        """)).fetchone()
        assert result[0] == 'momentum', f"Expected 'momentum', got '{result[0]}'"
    finally:
        cleanup(s)

test("T-01-02", "JSONB trade_context stores and queries arbitrary data", t_01_02)


# =========================================================================
# T-01-03: idempotency_key UNIQUE constraint
# =========================================================================
def t_01_03():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, idempotency_key)
            VALUES ('test_user', 'AAPL', 'CALL', 200.0, '2026-06-20', 3.00, 'idem-test-001')
        """))
        raised = False
        try:
            s.execute(text("""
                INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, idempotency_key)
                VALUES ('test_user', 'AAPL', 'PUT', 180.0, '2026-06-20', 2.00, 'idem-test-001')
            """))
        except Exception:
            raised = True
        assert raised, "Should have raised IntegrityError for duplicate idempotency_key"
    finally:
        cleanup(s)

test("T-01-03", "idempotency_key UNIQUE constraint rejects duplicates", t_01_03)


# =========================================================================
# T-01-04: version column defaults to 1
# =========================================================================
def t_01_04():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price)
            VALUES ('test_user', 'TSLA', 'PUT', 300.0, '2026-06-20', 8.00)
        """))
        result = s.execute(text("""
            SELECT version FROM paper_trades WHERE ticker = 'TSLA' AND username = 'test_user'
        """)).fetchone()
        assert result[0] == 1, f"Expected version=1, got {result[0]}"
    finally:
        cleanup(s)

test("T-01-04", "version column defaults to 1", t_01_04)


# =========================================================================
# T-01-05: status CHECK constraint rejects invalid values
# =========================================================================
def t_01_05():
    s = fresh_session()
    try:
        raised = False
        try:
            s.execute(text("""
                INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, status)
                VALUES ('test_user', 'META', 'CALL', 500.0, '2026-06-20', 10.00, 'INVALID')
            """))
        except Exception:
            raised = True
        assert raised, "Should have rejected INVALID status"
    finally:
        cleanup(s)

test("T-01-05", "status CHECK constraint rejects 'INVALID'", t_01_05)


# =========================================================================
# T-01-06: Cascade delete on state_transitions
# =========================================================================
def t_01_06():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (id, username, ticker, option_type, strike, expiry, entry_price)
            VALUES (99999, 'test_user', 'GOOG', 'CALL', 180.0, '2026-06-20', 6.00)
        """))
        s.execute(text("""
            INSERT INTO state_transitions (trade_id, from_status, to_status, trigger)
            VALUES (99999, NULL, 'PENDING', 'user_submit')
        """))
        # Verify transition exists
        count_before = s.execute(text(
            "SELECT COUNT(*) FROM state_transitions WHERE trade_id = 99999"
        )).fetchone()[0]
        assert count_before == 1, f"Expected 1 transition, got {count_before}"

        # Delete the trade
        s.execute(text("DELETE FROM paper_trades WHERE id = 99999"))

        # Verify transition is gone (CASCADE)
        count_after = s.execute(text(
            "SELECT COUNT(*) FROM state_transitions WHERE trade_id = 99999"
        )).fetchone()[0]
        assert count_after == 0, f"Expected 0 orphans after cascade, got {count_after}"
    finally:
        cleanup(s)

test("T-01-06", "Cascade delete removes state_transitions", t_01_06)


# =========================================================================
# T-01-07: Index on (username, status) exists
# =========================================================================
def t_01_07():
    s = Session()
    result = s.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'paper_trades' AND indexname = 'ix_paper_trades_username_status'
    """)).fetchone()
    s.close()
    assert result is not None, "Composite index ix_paper_trades_username_status not found"

test("T-01-07", "Index ix_paper_trades_username_status exists", t_01_07)


# =========================================================================
# T-01-08: created_at auto-populates
# =========================================================================
def t_01_08():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price)
            VALUES ('test_user', 'AMD', 'CALL', 160.0, '2026-06-20', 4.00)
        """))
        result = s.execute(text("""
            SELECT created_at FROM paper_trades WHERE ticker = 'AMD' AND username = 'test_user'
        """)).fetchone()
        assert result[0] is not None, "created_at should auto-populate"
        assert isinstance(result[0], datetime), f"Expected datetime, got {type(result[0])}"
    finally:
        cleanup(s)

test("T-01-08", "created_at auto-populates with now()", t_01_08)


# =========================================================================
# T-01-09: RLS policies active
# =========================================================================
def t_01_09():
    s = Session()
    result = s.execute(text("""
        SELECT COUNT(*) FROM pg_policies WHERE tablename = 'paper_trades'
    """)).fetchone()
    s.close()
    assert result[0] > 0, "No RLS policies found on paper_trades"

test("T-01-09", "RLS policies are active on paper_trades", t_01_09)


# =========================================================================
# T-01-10: realized_pnl accepts negative values
# =========================================================================
def t_01_10():
    s = fresh_session()
    try:
        s.execute(text("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, realized_pnl, status)
            VALUES ('test_user', 'MSFT', 'PUT', 400.0, '2026-06-20', 12.00, -500.00, 'CLOSED')
        """))
        result = s.execute(text("""
            SELECT realized_pnl FROM paper_trades WHERE ticker = 'MSFT' AND username = 'test_user'
        """)).fetchone()
        assert result[0] == -500.00, f"Expected -500.00, got {result[0]}"
    finally:
        cleanup(s)

test("T-01-10", "realized_pnl accepts negative values (-500.00)", t_01_10)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*50}")
print(f"Point 1 Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)
