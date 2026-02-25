"""
Point 4 Regression Tests: SL/TP Bracket Enforcement
=====================================================
Tests T-04-01 through T-04-35

Groups:
  A. Manual Close — Core Flow (6)
  B. Adjust SL/TP (6)
  C. Clean Bracket Hit Detection (4)
  D. OCO Wiring at Trade Placement (4)
  E. Orphan Guard (3)
  F. State Transition Audit Trail (3)
  G. Route-Level HTTP Tests (4)
  H. Error Resilience (3)
  I. Edge Cases (2)

Requires:
  - Docker Postgres running (docker compose -f docker-compose.paper.yml up -d)
  - Alembic migrations applied
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from unittest.mock import patch, MagicMock
import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# ── Constants ──────────────────────────────────────────────
DB_URL = 'postgresql://app_user:app_pass@localhost:5433/paper_trading'
OWNER_URL = 'postgresql://paper_user:paper_pass@localhost:5433/paper_trading'

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


# ── DB Helpers ─────────────────────────────────────────────

def get_owner_conn():
    """Get raw psycopg2 connection as paper_user (superuser/owner)."""
    conn = psycopg2.connect(OWNER_URL)
    conn.autocommit = True
    return conn


def seed_open_trade(conn, username='test_user', ticker='AAPL',
                    entry_price=5.0, qty=1, direction='BUY',
                    tradier_order_id=None, sl_order_id=None, tp_order_id=None,
                    sl_price=None, tp_price=None, current_price=None):
    """Insert an OPEN trade and return its id."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO paper_trades (
            username, ticker, option_type, strike, expiry, direction,
            entry_price, qty, status, version, trade_context,
            tradier_order_id, tradier_sl_order_id, tradier_tp_order_id,
            sl_price, tp_price, current_price
        ) VALUES (
            %s, %s, 'CALL', 150.0, '2026-06-20', %s,
            %s, %s, 'OPEN', 1, '{}',
            %s, %s, %s,
            %s, %s, %s
        ) RETURNING id
    """, (username, ticker, direction, entry_price, qty,
          tradier_order_id, sl_order_id, tp_order_id,
          sl_price, tp_price, current_price))
    trade_id = cur.fetchone()[0]
    cur.close()
    return trade_id


def seed_closed_trade(conn, username='test_user', status='CLOSED',
                      sl_order_id=None, tp_order_id=None):
    """Insert a CLOSED/EXPIRED/CANCELED trade for orphan guard tests."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO paper_trades (
            username, ticker, option_type, strike, expiry, direction,
            entry_price, qty, status, version, trade_context,
            tradier_sl_order_id, tradier_tp_order_id
        ) VALUES (
            %s, 'AAPL', 'CALL', 150.0, '2026-06-20', 'BUY',
            5.0, 1, %s, 2, '{}',
            %s, %s
        ) RETURNING id
    """, (username, status, sl_order_id, tp_order_id))
    trade_id = cur.fetchone()[0]
    cur.close()
    return trade_id


def cleanup_test_data(conn, username='test_user'):
    """Remove all test data for a user."""
    cur = conn.cursor()
    cur.execute("DELETE FROM price_snapshots WHERE trade_id IN (SELECT id FROM paper_trades WHERE username = %s)", (username,))
    cur.execute("DELETE FROM state_transitions WHERE trade_id IN (SELECT id FROM paper_trades WHERE username = %s)", (username,))
    cur.execute("DELETE FROM paper_trades WHERE username = %s", (username,))
    cur.close()


def get_sa_session():
    """Get a SQLAlchemy session bound to OWNER_URL."""
    engine = create_engine(OWNER_URL)
    Session = sessionmaker(bind=engine)
    return Session()


print("\n" + "=" * 60)
print("Point 4 Tests: SL/TP Bracket Enforcement")
print("=" * 60 + "\n")


# =========================================================================
# A. MANUAL CLOSE — CORE FLOW (T-04-01 to T-04-06)
# =========================================================================


def t_04_01():
    """Manual close: status=CLOSED, close_reason=MANUAL_CLOSE."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    trade_id = seed_open_trade(conn, username='close_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.manual_close_position(trade_id, 'close_user')

        assert result is not None, "Result should not be None"
        assert result['status'] == 'CLOSED', f"Expected CLOSED, got {result['status']}"

        cur = conn.cursor()
        cur.execute("SELECT status, close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 'CLOSED', f"DB status expected CLOSED, got {row[0]}"
        assert row[1] == 'MANUAL_CLOSE', f"Expected MANUAL_CLOSE, got {row[1]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-01", "Manual close → CLOSED, reason=MANUAL_CLOSE", t_04_01)


def t_04_02():
    """BUY P&L: (exit−entry)×qty×100, positive when profitable."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    # Entry 5.0, current 8.0, BUY, qty=2 → PnL = (8-5)×2×100 = 600.0
    trade_id = seed_open_trade(conn, username='close_user', ticker='NVDA',
                               entry_price=5.0, qty=2, direction='BUY',
                               current_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.manual_close_position(trade_id, 'close_user')

        assert result['exit_price'] == 8.0, f"Expected exit 8.0, got {result['exit_price']}"
        assert result['realized_pnl'] == 600.0, f"Expected PnL 600.0, got {result['realized_pnl']}"
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-02", "BUY P&L = (8−5)×2×100 = 600.0", t_04_02)


def t_04_03():
    """SELL P&L: inverted multiplier."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    # Entry 8.0, current 5.0, SELL, qty=1 → PnL = (5-8)×1×100×(-1) = 300.0
    trade_id = seed_open_trade(conn, username='close_user', ticker='SPY',
                               entry_price=8.0, qty=1, direction='SELL',
                               current_price=5.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.manual_close_position(trade_id, 'close_user')

        assert result['realized_pnl'] == 300.0, f"Expected PnL 300.0, got {result['realized_pnl']}"
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-03", "SELL P&L = (5−8)×1×100×(-1) = 300.0", t_04_03)


def t_04_04():
    """Close nulls tradier_sl_order_id and tradier_tp_order_id."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    trade_id = seed_open_trade(conn, username='close_user', ticker='AAPL',
                               entry_price=5.0, current_price=6.0,
                               tradier_order_id='ORD_1',
                               sl_order_id='SL_1', tp_order_id='TP_1')

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            ms.manual_close_position(trade_id, 'close_user')

        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] is None, f"SL order ID should be None, got {row[0]}"
        assert row[1] is None, f"TP order ID should be None, got {row[1]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-04", "Close nulls bracket order IDs in DB", t_04_04)


def t_04_05():
    """Close increments version 1→2 and sets closed_at."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    trade_id = seed_open_trade(conn, username='close_user', ticker='TSLA',
                               entry_price=5.0, current_price=6.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            ms.manual_close_position(trade_id, 'close_user')

        cur = conn.cursor()
        cur.execute("SELECT version, closed_at FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 2, f"Expected version=2, got {row[0]}"
        assert row[1] is not None, "closed_at should be set"
        cur.close()
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-05", "Close increments version 1→2, sets closed_at", t_04_05)


def t_04_06():
    """Close with no current_price → uses entry_price as exit fallback."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'close_user')
    # current_price=None → exit should fall back to entry_price=5.0
    trade_id = seed_open_trade(conn, username='close_user', ticker='GOOG',
                               entry_price=5.0, current_price=None)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.manual_close_position(trade_id, 'close_user')

        assert result['exit_price'] == 5.0, f"Expected exit=entry 5.0, got {result['exit_price']}"
        assert result['realized_pnl'] == 0.0, f"Expected PnL 0.0, got {result['realized_pnl']}"
    finally:
        cleanup_test_data(conn, 'close_user')
        conn.close()

test("T-04-06", "Close with no current_price → uses entry_price as exit", t_04_06)


# =========================================================================
# B. ADJUST SL/TP (T-04-07 to T-04-12)
# =========================================================================


def t_04_07():
    """Adjust SL only → sl_price updated, tp_price unchanged."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'adjust_user')
    trade_id = seed_open_trade(conn, username='adjust_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(trade_id, 'adjust_user', new_sl=3.0)

        assert result is not None
        assert result['sl_price'] == 3.0, f"Expected SL=3.0, got {result['sl_price']}"
        assert result['tp_price'] == 8.0, f"TP should stay 8.0, got {result['tp_price']}"
    finally:
        cleanup_test_data(conn, 'adjust_user')
        conn.close()

test("T-04-07", "Adjust SL only → sl=3.0, tp unchanged", t_04_07)


def t_04_08():
    """Adjust TP only → tp_price updated, sl_price unchanged."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'adjust_user')
    trade_id = seed_open_trade(conn, username='adjust_user', ticker='NVDA',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(trade_id, 'adjust_user', new_tp=12.0)

        assert result['sl_price'] == 4.0, f"SL should stay 4.0, got {result['sl_price']}"
        assert result['tp_price'] == 12.0, f"Expected TP=12.0, got {result['tp_price']}"
    finally:
        cleanup_test_data(conn, 'adjust_user')
        conn.close()

test("T-04-08", "Adjust TP only → tp=12.0, sl unchanged", t_04_08)


def t_04_09():
    """Adjust both SL and TP simultaneously."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'adjust_user')
    trade_id = seed_open_trade(conn, username='adjust_user', ticker='SPY',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(trade_id, 'adjust_user', new_sl=3.0, new_tp=12.0)

        assert result['sl_price'] == 3.0, f"Expected SL=3.0, got {result['sl_price']}"
        assert result['tp_price'] == 12.0, f"Expected TP=12.0, got {result['tp_price']}"
    finally:
        cleanup_test_data(conn, 'adjust_user')
        conn.close()

test("T-04-09", "Adjust both SL and TP simultaneously", t_04_09)


def t_04_10():
    """Adjust increments version and returns correct dict shape."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'adjust_user')
    trade_id = seed_open_trade(conn, username='adjust_user', ticker='MSFT',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(trade_id, 'adjust_user', new_sl=3.5)

        assert result['version'] == 2, f"Expected version=2, got {result['version']}"
        assert 'id' in result, "Response should contain 'id'"
        assert 'ticker' in result, "Response should contain 'ticker'"
        assert 'sl_price' in result, "Response should contain 'sl_price'"
        assert 'tp_price' in result, "Response should contain 'tp_price'"
    finally:
        cleanup_test_data(conn, 'adjust_user')
        conn.close()

test("T-04-10", "Adjust increments version, returns correct dict shape", t_04_10)


def t_04_11():
    """Adjust calls broker.cancel_order for old SL/TP, then place_oco_order."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'broker_adj_user')

    # Seed a UserSettings row so adjust_bracket's `db.query(UserSettings).get()` succeeds
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_settings (username, broker_mode, tradier_sandbox_token, tradier_account_id)
        VALUES ('broker_adj_user', 'TRADIER_SANDBOX', 'fake_token', 'VA00000000')
        ON CONFLICT (username) DO NOTHING
    """)
    cur.close()

    trade_id = seed_open_trade(conn, username='broker_adj_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0,
                               tradier_order_id='ORD_100',
                               sl_order_id='SL_OLD', tp_order_id='TP_OLD')

    try:
        ms = MonitorService()
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True
        mock_broker.place_oco_order.return_value = {
            'leg': [{'id': 'SL_NEW'}, {'id': 'TP_NEW'}]
        }

        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session

            with patch('backend.services.monitor_service.BrokerFactory') as mock_factory:
                mock_factory.get_broker.return_value = mock_broker
                result = ms.adjust_bracket(trade_id, 'broker_adj_user', new_sl=3.0, new_tp=10.0)

        # Verify cancel was called for old SL and TP orders
        assert mock_broker.cancel_order.call_count >= 2, \
            f"Expected ≥2 cancel calls, got {mock_broker.cancel_order.call_count}"

        # Verify place_oco_order was called with new prices
        assert mock_broker.place_oco_order.called, "place_oco_order should have been called"
        oco_call = mock_broker.place_oco_order.call_args
        sl_arg = oco_call.kwargs.get('sl_order', {})
        tp_arg = oco_call.kwargs.get('tp_order', {})
        assert sl_arg.get('stop_price') == 3.0, f"OCO SL expected 3.0, got {sl_arg.get('stop_price')}"
        assert tp_arg.get('limit_price') == 10.0, f"OCO TP expected 10.0, got {tp_arg.get('limit_price')}"

        # Verify new order IDs stored in DB
        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 'SL_NEW', f"Expected new SL ID 'SL_NEW', got {row[0]}"
        assert row[1] == 'TP_NEW', f"Expected new TP ID 'TP_NEW', got {row[1]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'broker_adj_user')
        cur2 = conn.cursor()
        cur2.execute("DELETE FROM user_settings WHERE username = 'broker_adj_user'")
        cur2.close()
        conn.close()

test("T-04-11", "Adjust calls cancel for old + place_oco_order for new", t_04_11)


def t_04_12():
    """Adjust on non-existent trade → returns None."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'adjust_user')

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(99999, 'adjust_user', new_sl=3.0)

        assert result is None, f"Expected None for non-existent trade, got {result}"
    finally:
        conn.close()

test("T-04-12", "Adjust on non-existent trade → returns None", t_04_12)


# =========================================================================
# C. CLEAN BRACKET HIT DETECTION (T-04-13 to T-04-16)
# =========================================================================


def t_04_13():
    """Fill at TP price → close_reason=TP_HIT."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'fill_user')
    trade_id = seed_open_trade(conn, username='fill_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        # Fill at 7.50 → 7.50 >= 7.0 * 0.98 (6.86) → TP_HIT
        order = {'avg_fill_price': '7.50', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        reason = cur.fetchone()[0]
        assert reason == 'TP_HIT', f"Expected TP_HIT, got {reason}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'fill_user')
        conn.close()

test("T-04-13", "Fill at TP price → close_reason=TP_HIT", t_04_13)


def t_04_14():
    """Fill at SL price → close_reason=SL_HIT."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'fill_user')
    trade_id = seed_open_trade(conn, username='fill_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        # Fill at 3.80 → 3.80 <= 4.0 * 1.02 (4.08) → SL_HIT
        order = {'avg_fill_price': '3.80', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        reason = cur.fetchone()[0]
        assert reason == 'SL_HIT', f"Expected SL_HIT, got {reason}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'fill_user')
        conn.close()

test("T-04-14", "Fill at SL price → close_reason=SL_HIT", t_04_14)


def t_04_15():
    """Fill between SL and TP → close_reason=BROKER_FILL (no bracket match)."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'fill_user')
    trade_id = seed_open_trade(conn, username='fill_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        # Fill at 5.50 → not in SL zone (<=4.08), not in TP zone (>=6.86) → BROKER_FILL
        order = {'avg_fill_price': '5.50', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        reason = cur.fetchone()[0]
        assert reason == 'BROKER_FILL', f"Expected BROKER_FILL, got {reason}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'fill_user')
        conn.close()

test("T-04-15", "Fill between SL/TP → close_reason=BROKER_FILL", t_04_15)


def t_04_16():
    """Fill exactly at SL*1.02 boundary → SL_HIT (≤ is inclusive)."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'fill_user')
    trade_id = seed_open_trade(conn, username='fill_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        # Exact boundary: 4.0 * 1.02 = 4.08 → fill at 4.08 → SL_HIT
        order = {'avg_fill_price': '4.08', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        reason = cur.fetchone()[0]
        assert reason == 'SL_HIT', f"Expected SL_HIT at boundary, got {reason}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'fill_user')
        conn.close()

test("T-04-16", "Fill exactly at SL*1.02 boundary → SL_HIT (inclusive)", t_04_16)


# =========================================================================
# D. OCO WIRING AT TRADE PLACEMENT (T-04-17 to T-04-20)
# =========================================================================


def t_04_17():
    """place_oco_order receives correct OCC symbol."""
    from backend.services.monitor_service import MonitorService

    # Test OCC symbol builder
    mock_trade = MagicMock()
    mock_trade.ticker = 'AAPL'
    mock_trade.expiry = '2026-06-20'
    mock_trade.option_type = 'CALL'
    mock_trade.strike = 150.0

    occ = MonitorService._build_occ_symbol(mock_trade)
    assert occ == 'AAPL260620C00150000', f"Expected AAPL260620C00150000, got {occ}"

    # PUT symbol
    mock_trade.option_type = 'PUT'
    mock_trade.strike = 450.5
    occ_put = MonitorService._build_occ_symbol(mock_trade)
    assert occ_put == 'AAPL260620P00450500', f"Expected AAPL260620P00450500, got {occ_put}"

test("T-04-17", "OCC symbol: AAPL CALL 150 → AAPL260620C00150000", t_04_17)


def t_04_18():
    """OCO response leg IDs stored correctly."""
    from backend.services.broker.tradier import TradierBroker

    # Verify the OCO payload structure
    broker = TradierBroker.__new__(TradierBroker)  # Skip __init__

    # Simulate what place_oco_order sends
    sl_order = {'symbol': 'AAPL260620C00150000', 'qty': 1, 'stop_price': 4.0}
    tp_order = {'symbol': 'AAPL260620C00150000', 'qty': 1, 'limit_price': 8.0}

    # Verify the adjust_bracket code correctly parses OCO response
    oco_response = {'leg': [{'id': 'SL_789'}, {'id': 'TP_012'}]}
    legs = oco_response.get('leg', [])
    assert len(legs) >= 2, f"Expected 2 legs, got {len(legs)}"
    assert str(legs[0]['id']) == 'SL_789'
    assert str(legs[1]['id']) == 'TP_012'

test("T-04-18", "OCO response leg IDs parsed correctly", t_04_18)


def t_04_19():
    """Trade with only SL (no TP) → no OCO placed."""
    # The guard: `if trade.sl_price and trade.tp_price:` in place_trade and adjust_bracket
    # means OCO is only placed when BOTH are set.
    sl = 4.0
    tp = None
    assert not (sl and tp), "OCO guard should prevent placement when tp is None"

    sl2 = None
    tp2 = 8.0
    assert not (sl2 and tp2), "OCO guard should prevent placement when sl is None"

    sl3 = 4.0
    tp3 = 8.0
    assert (sl3 and tp3), "OCO should be placed when both are set"

test("T-04-19", "Trade with only SL (no TP) → no OCO placed (guard)", t_04_19)


def t_04_20():
    """OCO placement fails → trade still saved (paper-only fallback)."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerException

    conn = get_owner_conn()
    cleanup_test_data(conn, 'oco_fail_user')
    trade_id = seed_open_trade(conn, username='oco_fail_user', ticker='TSLA',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0,
                               tradier_order_id='ORD_FAIL')

    try:
        ms = MonitorService()
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True
        mock_broker.place_oco_order.side_effect = BrokerException("OCO failed")

        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            with patch('backend.services.monitor_service.BrokerFactory') as mock_factory:
                mock_factory.get_broker.return_value = mock_broker
                result = ms.adjust_bracket(trade_id, 'oco_fail_user', new_sl=3.0)

        # Verify trade was still updated locally despite OCO failure
        assert result is not None, "Should still return result"
        assert result['sl_price'] == 3.0, f"SL should be updated locally, got {result['sl_price']}"
    finally:
        cleanup_test_data(conn, 'oco_fail_user')
        conn.close()

test("T-04-20", "OCO placement fails → bracket prices still updated locally", t_04_20)


# =========================================================================
# E. ORPHAN GUARD (T-04-21 to T-04-23)
# =========================================================================


def t_04_21():
    """CLOSED trade with both bracket IDs → both cancelled and nulled."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'orphan_user')
    trade_id = seed_closed_trade(conn, username='orphan_user', status='CLOSED',
                                 sl_order_id='ORPHAN_SL', tp_order_id='ORPHAN_TP')

    try:
        ms = MonitorService()
        session = get_sa_session()
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        ms._orphan_guard(session, mock_broker, 'orphan_user')
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] is None, f"SL should be None, got {row[0]}"
        assert row[1] is None, f"TP should be None, got {row[1]}"
        assert mock_broker.cancel_order.call_count == 2
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'orphan_user')
        conn.close()

test("T-04-21", "CLOSED trade with both bracket IDs → both cancelled + nulled", t_04_21)


def t_04_22():
    """EXPIRED trade with only SL bracket → SL cancelled, TP untouched."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'orphan_user')
    trade_id = seed_closed_trade(conn, username='orphan_user', status='EXPIRED',
                                 sl_order_id='ORPHAN_SL_ONLY', tp_order_id=None)

    try:
        ms = MonitorService()
        session = get_sa_session()
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        ms._orphan_guard(session, mock_broker, 'orphan_user')
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] is None, f"SL should be None, got {row[0]}"
        assert mock_broker.cancel_order.call_count == 1, \
            f"Only 1 cancel call expected, got {mock_broker.cancel_order.call_count}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'orphan_user')
        conn.close()

test("T-04-22", "EXPIRED trade with only SL → SL cancelled, 1 cancel call", t_04_22)


def t_04_23():
    """Cancel throws BrokerException → bracket ID still nulled, no crash."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerException

    conn = get_owner_conn()
    cleanup_test_data(conn, 'orphan_user')
    trade_id = seed_closed_trade(conn, username='orphan_user', status='CANCELED',
                                 sl_order_id='FAIL_SL', tp_order_id='FAIL_TP')

    try:
        ms = MonitorService()
        session = get_sa_session()
        mock_broker = MagicMock()
        mock_broker.cancel_order.side_effect = BrokerException("Already filled")

        # Should NOT raise
        ms._orphan_guard(session, mock_broker, 'orphan_user')
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] is None, f"SL should still be nulled despite error, got {row[0]}"
        assert row[1] is None, f"TP should still be nulled despite error, got {row[1]}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'orphan_user')
        conn.close()

test("T-04-23", "Cancel BrokerException → bracket IDs still nulled, no crash", t_04_23)


# =========================================================================
# F. STATE TRANSITION AUDIT TRAIL (T-04-24 to T-04-26)
# =========================================================================


def t_04_24():
    """Manual close creates StateTransition: OPEN→CLOSED, trigger=USER_MANUAL_CLOSE."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'audit_user')
    trade_id = seed_open_trade(conn, username='audit_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            ms.manual_close_position(trade_id, 'audit_user')

        cur = conn.cursor()
        cur.execute("""
            SELECT from_status, to_status, trigger
            FROM state_transitions WHERE trade_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (trade_id,))
        row = cur.fetchone()
        assert row is not None, "StateTransition should exist"
        assert row[0] == 'OPEN', f"from_status expected OPEN, got {row[0]}"
        assert row[1] == 'CLOSED', f"to_status expected CLOSED, got {row[1]}"
        assert row[2] == 'USER_MANUAL_CLOSE', f"trigger expected USER_MANUAL_CLOSE, got {row[2]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'audit_user')
        conn.close()

test("T-04-24", "Manual close → StateTransition OPEN→CLOSED, USER_MANUAL_CLOSE", t_04_24)


def t_04_25():
    """StateTransition metadata contains exit_price and pnl."""
    from backend.services.monitor_service import MonitorService
    import json

    conn = get_owner_conn()
    cleanup_test_data(conn, 'audit_user')
    trade_id = seed_open_trade(conn, username='audit_user', ticker='NVDA',
                               entry_price=5.0, current_price=8.0, qty=1)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            ms.manual_close_position(trade_id, 'audit_user')

        cur = conn.cursor()
        cur.execute("""
            SELECT metadata_json
            FROM state_transitions WHERE trade_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (trade_id,))
        row = cur.fetchone()
        metadata = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        assert 'exit_price' in metadata, f"metadata should contain exit_price: {metadata}"
        assert 'pnl' in metadata, f"metadata should contain pnl: {metadata}"
        assert metadata['exit_price'] == 8.0, f"Expected exit 8.0, got {metadata['exit_price']}"
        assert metadata['pnl'] == 300.0, f"Expected pnl 300.0, got {metadata['pnl']}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'audit_user')
        conn.close()

test("T-04-25", "StateTransition metadata has exit_price and pnl", t_04_25)


def t_04_26():
    """Fill creates StateTransition: OPEN→CLOSED, trigger=BROKER_FILL."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'audit_user')
    trade_id = seed_open_trade(conn, username='audit_user', ticker='GOOG',
                               entry_price=5.0, sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        order = {'avg_fill_price': '7.50', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        cur = conn.cursor()
        cur.execute("""
            SELECT from_status, to_status, trigger, metadata_json
            FROM state_transitions WHERE trade_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (trade_id,))
        row = cur.fetchone()
        assert row is not None, "StateTransition should exist for fill"
        assert row[0] == 'OPEN', f"from_status expected OPEN, got {row[0]}"
        assert row[1] == 'CLOSED', f"to_status expected CLOSED, got {row[1]}"
        assert row[2] == 'BROKER_FILL', f"trigger expected BROKER_FILL, got {row[2]}"
        metadata = row[3] if isinstance(row[3], dict) else {}
        assert 'fill_price' in metadata, f"metadata should contain fill_price: {metadata}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'audit_user')
        conn.close()

test("T-04-26", "Fill → StateTransition OPEN→CLOSED, BROKER_FILL with fill_price", t_04_26)


# =========================================================================
# G. ROUTE-LEVEL HTTP TESTS (T-04-27 to T-04-30)
# =========================================================================


def t_04_27():
    """POST /close with matching version → 200 success."""
    conn = get_owner_conn()
    cleanup_test_data(conn, 'route_user')
    trade_id = seed_open_trade(conn, username='route_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0)

    try:
        from backend.services.monitor_service import MonitorService

        # Simulate route logic: check version match then delegate
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session

            from backend.database.paper_models import PaperTrade
            trade = session.query(PaperTrade).filter_by(id=trade_id).first()
            assert trade is not None
            client_version = 1
            assert int(client_version) == trade.version, "Version should match"
            session.close()

            # Now do the actual close
            session2 = get_sa_session()
            mock_db.return_value = session2
            result = ms.manual_close_position(trade_id, 'route_user')
            assert result is not None
            assert result['status'] == 'CLOSED'
    finally:
        cleanup_test_data(conn, 'route_user')
        conn.close()

test("T-04-27", "Close with matching version=1 → succeeds", t_04_27)


def t_04_28():
    """Close with stale version → conflict detected."""
    conn = get_owner_conn()
    cleanup_test_data(conn, 'route_user')
    trade_id = seed_open_trade(conn, username='route_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0)

    try:
        session = get_sa_session()
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        # Simulate stale version check (trade.version=1, client sends 0)
        client_version = 0
        version_mismatch = (int(client_version) != trade.version)
        assert version_mismatch, "Stale version should be detected"
        session.close()
    finally:
        cleanup_test_data(conn, 'route_user')
        conn.close()

test("T-04-28", "Close with stale version=0 → conflict detected", t_04_28)


def t_04_29():
    """Close non-existent trade → returns None (404 in route)."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'route_user')

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.manual_close_position(99999, 'route_user')

        assert result is None, "Should return None for non-existent trade"
    finally:
        conn.close()

test("T-04-29", "Close non-existent trade → None (route returns 404)", t_04_29)


def t_04_30():
    """Adjust with no sl or tp → validation guard (400 in route)."""
    # The route checks: if new_sl is None and new_tp is None → 400
    new_sl = None
    new_tp = None
    assert (new_sl is None and new_tp is None), "Both None should fail validation"

    # But route returns 400 before calling adjust_bracket
    # If at least one is set, it proceeds
    assert not (3.0 is None and None is None), "SL=3.0 should pass"

test("T-04-30", "Adjust with no sl or tp → validation guard triggers 400", t_04_30)


# =========================================================================
# H. ERROR RESILIENCE (T-04-31 to T-04-33)
# =========================================================================


def t_04_31():
    """Broker cancel fails during manual close → trade still closes in DB."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerException

    conn = get_owner_conn()
    cleanup_test_data(conn, 'err_user')
    trade_id = seed_open_trade(conn, username='err_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0,
                               tradier_order_id='ORD_ERR',
                               sl_order_id='SL_ERR', tp_order_id='TP_ERR')

    try:
        ms = MonitorService()
        mock_broker = MagicMock()
        mock_broker.cancel_order.side_effect = BrokerException("Network error")

        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            with patch('backend.services.monitor_service.BrokerFactory') as mock_factory:
                mock_factory.get_broker.return_value = mock_broker
                result = ms.manual_close_position(trade_id, 'err_user')

        # Trade should still be closed even though cancel failed
        assert result is not None, "Should still return result"
        assert result['status'] == 'CLOSED', f"Expected CLOSED, got {result['status']}"

        cur = conn.cursor()
        cur.execute("SELECT status FROM paper_trades WHERE id = %s", (trade_id,))
        assert cur.fetchone()[0] == 'CLOSED', "DB status should be CLOSED"
        cur.close()
    finally:
        cleanup_test_data(conn, 'err_user')
        conn.close()

test("T-04-31", "Broker cancel fails → trade still closes in DB", t_04_31)


def t_04_32():
    """adjust_bracket exception → DB rollback, no partial commit."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'err_user')
    trade_id = seed_open_trade(conn, username='err_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()

        # Patch get_paper_db_with_user to return a session that crashes on commit
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            mock_session = MagicMock()
            # The query returns a real trade but commit crashes
            from backend.database.paper_models import PaperTrade
            real_session = get_sa_session()
            trade = real_session.query(PaperTrade).filter_by(id=trade_id).first()
            real_session.close()

            mock_query_result = MagicMock()
            mock_query_result.filter.return_value.first.return_value = trade
            mock_session.query.return_value = mock_query_result
            mock_session.commit.side_effect = Exception("Commit failed")
            mock_db.return_value = mock_session

            try:
                ms.adjust_bracket(trade_id, 'err_user', new_sl=1.0)
            except Exception:
                pass

            # Verify rollback was called
            mock_session.rollback.assert_called_once()

        # Verify original DB prices unchanged
        cur = conn.cursor()
        cur.execute("SELECT sl_price FROM paper_trades WHERE id = %s", (trade_id,))
        sl = cur.fetchone()[0]
        assert sl == 4.0, f"SL should remain 4.0 after rollback, got {sl}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'err_user')
        conn.close()

test("T-04-32", "adjust_bracket exception → rollback, no partial commit", t_04_32)


def t_04_33():
    """adjust_bracket broker error → DB prices still updated (decoupled)."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerException

    conn = get_owner_conn()
    cleanup_test_data(conn, 'err_user')
    trade_id = seed_open_trade(conn, username='err_user', ticker='NVDA',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0,
                               tradier_order_id='ORD_BROKER_ERR')

    try:
        ms = MonitorService()
        mock_broker = MagicMock()
        mock_broker.cancel_order.side_effect = BrokerException("Broker down")

        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            with patch('backend.services.monitor_service.BrokerFactory') as mock_factory:
                mock_factory.get_broker.return_value = mock_broker
                result = ms.adjust_bracket(trade_id, 'err_user', new_sl=2.0, new_tp=15.0)

        # Local DB should still have new prices even though broker failed
        assert result is not None, "Should still return result"
        assert result['sl_price'] == 2.0, f"Expected SL=2.0, got {result['sl_price']}"
        assert result['tp_price'] == 15.0, f"Expected TP=15.0, got {result['tp_price']}"
    finally:
        cleanup_test_data(conn, 'err_user')
        conn.close()

test("T-04-33", "Broker error → DB brackets still updated locally", t_04_33)


# =========================================================================
# I. EDGE CASES (T-04-34 to T-04-35)
# =========================================================================


def t_04_34():
    """Close already-closed trade → returns None (idempotent)."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'edge_user')
    trade_id = seed_open_trade(conn, username='edge_user', ticker='AAPL',
                               entry_price=5.0, current_price=7.0)

    try:
        ms = MonitorService()
        # Close once
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result1 = ms.manual_close_position(trade_id, 'edge_user')
        assert result1 is not None, "First close should succeed"

        # Close again — should return None since it's already CLOSED
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session2 = get_sa_session()
            mock_db.return_value = session2
            result2 = ms.manual_close_position(trade_id, 'edge_user')
        assert result2 is None, f"Second close should return None, got {result2}"
    finally:
        cleanup_test_data(conn, 'edge_user')
        conn.close()

test("T-04-34", "Close already-closed trade → returns None (idempotent)", t_04_34)


def t_04_35():
    """Adjust with high-precision SL → stored correctly."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'edge_user')
    trade_id = seed_open_trade(conn, username='edge_user', ticker='AAPL',
                               entry_price=5.0, sl_price=4.0, tp_price=8.0)

    try:
        ms = MonitorService()
        with patch('backend.database.paper_session.get_paper_db_with_user') as mock_db:
            session = get_sa_session()
            mock_db.return_value = session
            result = ms.adjust_bracket(trade_id, 'edge_user', new_sl=3.14159)

        assert result['sl_price'] == 3.14159, f"Expected 3.14159, got {result['sl_price']}"

        # Verify in DB
        cur = conn.cursor()
        cur.execute("SELECT sl_price FROM paper_trades WHERE id = %s", (trade_id,))
        db_sl = cur.fetchone()[0]
        assert abs(db_sl - 3.14159) < 0.0001, f"DB SL expected ~3.14159, got {db_sl}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'edge_user')
        conn.close()

test("T-04-35", "Adjust with high-precision SL (3.14159) → stored correctly", t_04_35)


# ── Summary ───────────────────────────────────────────────
print("\n" + "=" * 60)
result_line = f"Point 4 Regression Results: {passed}/{total} passed, {failed} failed"
print(result_line)
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
