"""
Point 2 Regression Tests: Polling & Price Cache
=================================================
Tests T-02-01 through T-02-25

Mix of:
  - Scheduler lifecycle tests (import-based)
  - Live Postgres integration tests (price snapshots, sync pipeline)
  - Mock-based resilience tests

Requires:
  - Docker Postgres running (docker compose -f docker-compose.paper.yml up -d)
  - Alembic migrations applied
  - apscheduler installed
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock
import psycopg2
from sqlalchemy import create_engine, text
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
                    sl_price=None, tp_price=None):
    """Insert an OPEN trade and return its id."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO paper_trades (
            username, ticker, option_type, strike, expiry, direction,
            entry_price, qty, status, version, trade_context,
            tradier_order_id, tradier_sl_order_id, tradier_tp_order_id,
            sl_price, tp_price
        ) VALUES (
            %s, %s, 'CALL', 150.0, '2026-06-20', %s,
            %s, %s, 'OPEN', 1, '{}',
            %s, %s, %s,
            %s, %s
        ) RETURNING id
    """, (username, ticker, direction, entry_price, qty,
          tradier_order_id, sl_order_id, tp_order_id,
          sl_price, tp_price))
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


print("\n" + "=" * 60)
print("Point 2 Tests: Polling & Price Cache")
print("=" * 60 + "\n")


# =========================================================================
# A. SCHEDULER LIFECYCLE (T-02-01 to T-02-03)
# =========================================================================


def t_02_01():
    """APScheduler imports and BackgroundScheduler can be created."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BackgroundScheduler(daemon=True)
    assert scheduler is not None, "BackgroundScheduler should be created"

    # Verify we can add test jobs
    scheduler.add_job(func=lambda: None, trigger=IntervalTrigger(seconds=60),
                      id='test_job', replace_existing=True)
    scheduler.start()
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1, f"Expected 1 job, got {len(jobs)}"
    scheduler.shutdown(wait=False)

test("T-02-01", "APScheduler starts with BackgroundScheduler", t_02_01)


def t_02_02():
    """Scheduler registers 4 jobs with correct IDs and intervals."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger
    import pytz

    EASTERN = pytz.timezone('US/Eastern')
    scheduler = BackgroundScheduler(daemon=True)

    # Replicate app.py job registration
    scheduler.add_job(func=lambda: None, trigger=IntervalTrigger(seconds=60),
                      id='sync_tradier_orders', name='Tradier Order Sync (60s)',
                      replace_existing=True, max_instances=1)
    scheduler.add_job(func=lambda: None, trigger=IntervalTrigger(seconds=40),
                      id='update_price_snapshots', name='ORATS Price Snapshots (40s)',
                      replace_existing=True, max_instances=1)
    scheduler.add_job(func=lambda: None,
                      trigger=CronTrigger(day_of_week='mon-fri', hour=9, minute=25, timezone=EASTERN),
                      id='pre_market_bookend', name='Pre-Market Bookend (9:25 AM ET)',
                      replace_existing=True)
    scheduler.add_job(func=lambda: None,
                      trigger=CronTrigger(day_of_week='mon-fri', hour=16, minute=5, timezone=EASTERN),
                      id='post_market_bookend', name='Post-Market Bookend (4:05 PM ET)',
                      replace_existing=True)

    scheduler.start()
    jobs = scheduler.get_jobs()
    job_ids = [j.id for j in jobs]
    assert len(jobs) == 4, f"Expected 4 jobs, got {len(jobs)}"
    assert 'sync_tradier_orders' in job_ids
    assert 'update_price_snapshots' in job_ids
    assert 'pre_market_bookend' in job_ids
    assert 'post_market_bookend' in job_ids
    scheduler.shutdown(wait=False)

test("T-02-02", "4 jobs registered: sync 60s, snapshots 40s, bookends cron", t_02_02)


def t_02_03():
    """max_instances=1 prevents concurrent job execution."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(func=lambda: None, trigger=IntervalTrigger(seconds=60),
                      id='test_max_1', max_instances=1, replace_existing=True)
    scheduler.start()
    job = scheduler.get_job('test_max_1')
    assert job.max_instances == 1, f"Expected max_instances=1, got {job.max_instances}"
    scheduler.shutdown(wait=False)

test("T-02-03", "max_instances=1 prevents concurrent runs", t_02_03)


# =========================================================================
# B. PRICE SNAPSHOT PIPELINE (T-02-04 to T-02-09)
# =========================================================================


def t_02_04():
    """update_price_snapshots writes to price_snapshots table."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    trade_id = seed_open_trade(conn, username='poll_test_user', ticker='NVDA', entry_price=5.0)

    try:
        ms = MonitorService()
        mock_quote = {'price': 155.0, 'bid': 154.5, 'ask': 155.5}

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    # Create a real session for the test
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session

                    ms.update_price_snapshots()

        # Verify snapshot was written
        cur = conn.cursor()
        cur.execute("SELECT mark_price, snapshot_type FROM price_snapshots WHERE trade_id = %s", (trade_id,))
        row = cur.fetchone()
        assert row is not None, "Snapshot should exist in DB"
        assert row[0] == 155.0, f"Expected mark_price=155.0, got {row[0]}"
        assert row[1] == 'PERIODIC', f"Expected type PERIODIC, got {row[1]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-04", "update_price_snapshots writes to price_snapshots table", t_02_04)


def t_02_05():
    """Snapshot has all columns populated: mark_price, bid, ask, underlying, type."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    trade_id = seed_open_trade(conn, username='poll_test_user', ticker='AAPL', entry_price=3.0)

    try:
        ms = MonitorService()
        mock_quote = {'price': 180.0, 'bid': 179.5, 'ask': 180.5}

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session
                    ms.update_price_snapshots()

        cur = conn.cursor()
        cur.execute("""
            SELECT mark_price, bid, ask, underlying, snapshot_type
            FROM price_snapshots WHERE trade_id = %s
        """, (trade_id,))
        row = cur.fetchone()
        assert row is not None, "Snapshot should exist"
        assert row[0] == 180.0, f"mark_price expected 180.0, got {row[0]}"
        assert row[1] == 179.5, f"bid expected 179.5, got {row[1]}"
        assert row[2] == 180.5, f"ask expected 180.5, got {row[2]}"
        assert row[3] == 180.0, f"underlying expected 180.0, got {row[3]}"
        assert row[4] == 'PERIODIC', f"type expected PERIODIC, got {row[4]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-05", "Snapshot has mark_price, bid, ask, underlying, type=PERIODIC", t_02_05)


def t_02_06():
    """PaperTrade.current_price updated after snapshot."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    trade_id = seed_open_trade(conn, username='poll_test_user', ticker='MSFT', entry_price=4.0)

    try:
        ms = MonitorService()
        mock_quote = {'price': 200.0, 'bid': 199.0, 'ask': 201.0}

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session
                    ms.update_price_snapshots()

        cur = conn.cursor()
        cur.execute("SELECT current_price FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 200.0, f"current_price expected 200.0, got {row[0]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-06", "PaperTrade.current_price updated after snapshot", t_02_06)


def t_02_07():
    """BUY direction: unrealized_pnl = (mark - entry) × qty × 100."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    # Entry 5.0, BUY, qty=2
    trade_id = seed_open_trade(conn, username='poll_test_user', ticker='NVDA',
                               entry_price=5.0, qty=2, direction='BUY')

    try:
        ms = MonitorService()
        # Mark = (7.0 + 8.0) / 2 = 7.5 → pnl = (7.5 - 5.0) × 2 × 100 = 500.0
        mock_quote = {'price': 160.0, 'bid': 7.0, 'ask': 8.0}

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session
                    ms.update_price_snapshots()

        cur = conn.cursor()
        cur.execute("SELECT unrealized_pnl FROM paper_trades WHERE id = %s", (trade_id,))
        pnl = cur.fetchone()[0]
        assert pnl == 500.0, f"BUY pnl expected 500.0, got {pnl}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-07", "BUY direction: unrealized_pnl = (mark - entry) × qty × 100", t_02_07)


def t_02_08():
    """SELL direction: unrealized_pnl = (entry - mark) × qty × 100."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    # Entry 8.0, SELL, qty=1
    trade_id = seed_open_trade(conn, username='poll_test_user', ticker='SPY',
                               entry_price=8.0, qty=1, direction='SELL')

    try:
        ms = MonitorService()
        # Mark = (5.0 + 6.0) / 2 = 5.5 → pnl = (5.5 - 8.0) × 1 × 100 × (-1) = 250.0
        mock_quote = {'price': 450.0, 'bid': 5.0, 'ask': 6.0}

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session
                    ms.update_price_snapshots()

        cur = conn.cursor()
        cur.execute("SELECT unrealized_pnl FROM paper_trades WHERE id = %s", (trade_id,))
        pnl = cur.fetchone()[0]
        assert pnl == 250.0, f"SELL pnl expected 250.0, got {pnl}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-08", "SELL direction: unrealized_pnl = (entry - mark) × qty × 100", t_02_08)


def t_02_09():
    """Multiple trades per ticker → per-trade option quote, N snapshots."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'poll_test_user')
    t1 = seed_open_trade(conn, username='poll_test_user', ticker='TSLA', entry_price=3.0)
    t2 = seed_open_trade(conn, username='poll_test_user', ticker='TSLA', entry_price=4.0)
    t3 = seed_open_trade(conn, username='poll_test_user', ticker='TSLA', entry_price=5.0)

    try:
        ms = MonitorService()
        mock_option_quote = {
            'mark': 6.5, 'bid': 6.0, 'ask': 7.0,
            'underlying': 250.0, 'delta': 0.65, 'theta': -0.04, 'iv': 0.35
        }
        call_count = 0

        def counting_option_quote(ticker, strike, expiry, opt_type):
            nonlocal call_count
            call_count += 1
            return mock_option_quote

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_option_quote', side_effect=counting_option_quote):
                ms.update_price_snapshots()

        # Each trade gets its own get_option_quote call (contract-specific pricing)
        assert call_count == 3, f"Expected 3 ORATS calls (per-trade), got {call_count}"

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM price_snapshots WHERE trade_id IN (%s, %s, %s)", (t1, t2, t3))
        snap_count = cur.fetchone()[0]
        assert snap_count == 3, f"Expected 3 snapshots, got {snap_count}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'poll_test_user')
        conn.close()

test("T-02-09", "Multiple trades per ticker → per-trade option quote, N snapshots", t_02_09)


# =========================================================================
# C. TRADIER ORDER SYNC → DB (T-02-10 to T-02-13)
# =========================================================================


def t_02_10():
    """Fill detected → trade CLOSED, P&L calculated, close_reason set."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'sync_test_user')

    # Seed open trade with brackets: SL=4.0, TP=7.0
    trade_id = seed_open_trade(conn, username='sync_test_user', ticker='AAPL',
                               entry_price=5.0, qty=1, direction='BUY',
                               tradier_order_id='FAKE_123',
                               sl_price=4.0, tp_price=7.0)

    try:
        ms = MonitorService()

        # Mock the DB session with a real one
        engine = create_engine(OWNER_URL)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Simulate _handle_fill directly against live DB
        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()

        order = {'avg_fill_price': '7.50', 'status': 'filled'}
        ms._handle_fill(session, trade, order)
        session.commit()

        # Verify in DB
        cur = conn.cursor()
        cur.execute("SELECT status, exit_price, realized_pnl, close_reason, version FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 'CLOSED', f"Expected CLOSED, got {row[0]}"
        assert row[1] == 7.5, f"Expected exit_price 7.5, got {row[1]}"
        assert row[2] == 250.0, f"Expected pnl 250.0, got {row[2]}"
        assert row[3] == 'TP_HIT', f"Expected TP_HIT, got {row[3]}"
        assert row[4] == 2, f"Expected version 2, got {row[4]}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'sync_test_user')
        conn.close()

test("T-02-10", "Fill → trade CLOSED, P&L=250, close_reason=TP_HIT, version=2", t_02_10)


def t_02_11():
    """Expiration detected → trade EXPIRED, exit=0, full loss."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'sync_test_user')
    trade_id = seed_open_trade(conn, username='sync_test_user', ticker='GOOG',
                               entry_price=4.0, qty=2, direction='BUY')

    try:
        ms = MonitorService()
        engine = create_engine(OWNER_URL)
        Session = sessionmaker(bind=engine)
        session = Session()

        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()
        ms._handle_expiration(session, trade)
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT status, exit_price, realized_pnl, close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 'EXPIRED', f"Expected EXPIRED, got {row[0]}"
        assert row[1] == 0.0, f"Expected exit 0.0, got {row[1]}"
        assert row[2] == -800.0, f"Expected pnl -800.0, got {row[2]}"
        assert row[3] == 'EXPIRED', f"Expected reason EXPIRED, got {row[3]}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'sync_test_user')
        conn.close()

test("T-02-11", "Expiration → trade EXPIRED, exit=0, pnl=-800 (full loss)", t_02_11)


def t_02_12():
    """Rejection detected → trade CANCELED, reason uppercased."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'sync_test_user')
    trade_id = seed_open_trade(conn, username='sync_test_user', ticker='TSLA',
                               entry_price=10.0, qty=1, direction='BUY')

    try:
        ms = MonitorService()
        engine = create_engine(OWNER_URL)
        Session = sessionmaker(bind=engine)
        session = Session()

        from backend.database.paper_models import PaperTrade
        trade = session.query(PaperTrade).filter_by(id=trade_id).first()
        ms._handle_cancellation(session, trade, 'rejected')
        session.commit()

        cur = conn.cursor()
        cur.execute("SELECT status, close_reason FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 'CANCELED', f"Expected CANCELED, got {row[0]}"
        assert row[1] == 'REJECTED', f"Expected REJECTED, got {row[1]}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'sync_test_user')
        conn.close()

test("T-02-12", "Rejection → trade CANCELED, reason=REJECTED", t_02_12)


def t_02_13():
    """Orphan guard: closed trade with bracket IDs → IDs nulled."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'orphan_test_user')

    # Seed a CLOSED trade that still has bracket order IDs (orphan scenario)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO paper_trades (
            username, ticker, option_type, strike, expiry, direction,
            entry_price, qty, status, version, trade_context,
            tradier_sl_order_id, tradier_tp_order_id
        ) VALUES (
            'orphan_test_user', 'AAPL', 'CALL', 150.0, '2026-06-20', 'BUY',
            5.0, 1, 'CLOSED', 2, '{}',
            'ORPHAN_SL_123', 'ORPHAN_TP_456'
        ) RETURNING id
    """)
    trade_id = cur.fetchone()[0]
    cur.close()

    try:
        ms = MonitorService()
        engine = create_engine(OWNER_URL)
        Session = sessionmaker(bind=engine)
        session = Session()

        # Mock broker that "succeeds" on cancel
        mock_broker = MagicMock()
        mock_broker.cancel_order.return_value = True

        ms._orphan_guard(session, mock_broker, 'orphan_test_user')
        session.commit()

        # Verify bracket IDs are nulled
        cur = conn.cursor()
        cur.execute("SELECT tradier_sl_order_id, tradier_tp_order_id FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] is None, f"SL order ID should be None, got {row[0]}"
        assert row[1] is None, f"TP order ID should be None, got {row[1]}"

        # Verify cancel was called for both
        assert mock_broker.cancel_order.call_count == 2, \
            f"Expected 2 cancel calls, got {mock_broker.cancel_order.call_count}"
        cur.close()
        session.close()
    finally:
        cleanup_test_data(conn, 'orphan_test_user')
        conn.close()

test("T-02-13", "Orphan guard: closed trade bracket IDs nulled after cancel", t_02_13)


# =========================================================================
# D. MARKET HOURS GUARD (T-02-14 to T-02-16)
# =========================================================================


def t_02_14():
    """update_price_snapshots no-ops when market is closed."""
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()
    with patch('backend.services.monitor_service.is_market_open', return_value=False):
        with patch('backend.services.monitor_service.get_paper_db') as mock_db:
            ms.update_price_snapshots()
            mock_db.assert_not_called()

test("T-02-14", "update_price_snapshots no-ops when market closed", t_02_14)


def t_02_15():
    """sync_tradier_orders no-ops when market is closed."""
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()
    with patch('backend.services.monitor_service.is_market_open', return_value=False):
        with patch('backend.services.monitor_service.get_paper_db') as mock_db:
            ms.sync_tradier_orders()
            mock_db.assert_not_called()

test("T-02-15", "sync_tradier_orders no-ops when market closed", t_02_15)


def t_02_16():
    """FORCE_MARKET_OPEN=1 overrides market hours guard."""
    from backend.utils.market_hours import is_market_open

    with patch.dict(os.environ, {'FORCE_MARKET_OPEN': '1'}):
        assert is_market_open() is True, "FORCE_MARKET_OPEN should bypass market hours"

test("T-02-16", "FORCE_MARKET_OPEN=1 overrides market hours guard", t_02_16)


# =========================================================================
# E. BOOKEND SNAPSHOTS (T-02-17 to T-02-19)
# =========================================================================


def t_02_17():
    """capture_bookend_snapshot('OPEN_BOOKEND') writes correct type."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'bookend_test_user')
    trade_id = seed_open_trade(conn, username='bookend_test_user', ticker='AAPL', entry_price=5.0)

    try:
        ms = MonitorService()
        mock_quote = {'price': 180.0, 'bid': 179.0, 'ask': 181.0}

        with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
            with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                engine = create_engine(OWNER_URL)
                Session = sessionmaker(bind=engine)
                session = Session()
                mock_get_db.return_value = session
                ms.capture_bookend_snapshot('OPEN_BOOKEND')

        cur = conn.cursor()
        cur.execute("SELECT snapshot_type FROM price_snapshots WHERE trade_id = %s", (trade_id,))
        row = cur.fetchone()
        assert row is not None, "Bookend snapshot should exist"
        assert row[0] == 'OPEN_BOOKEND', f"Expected OPEN_BOOKEND, got {row[0]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'bookend_test_user')
        conn.close()

test("T-02-17", "capture_bookend_snapshot('OPEN_BOOKEND') → correct type", t_02_17)


def t_02_18():
    """capture_bookend_snapshot('CLOSE_BOOKEND') writes correct type."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'bookend_test_user')
    trade_id = seed_open_trade(conn, username='bookend_test_user', ticker='SPY', entry_price=4.0)

    try:
        ms = MonitorService()
        mock_quote = {'price': 450.0, 'bid': 449.0, 'ask': 451.0}

        with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
            with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                engine = create_engine(OWNER_URL)
                Session = sessionmaker(bind=engine)
                session = Session()
                mock_get_db.return_value = session
                ms.capture_bookend_snapshot('CLOSE_BOOKEND')

        cur = conn.cursor()
        cur.execute("SELECT snapshot_type FROM price_snapshots WHERE trade_id = %s", (trade_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 'CLOSE_BOOKEND', f"Expected CLOSE_BOOKEND, got {row[0]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'bookend_test_user')
        conn.close()

test("T-02-18", "capture_bookend_snapshot('CLOSE_BOOKEND') → correct type", t_02_18)


def t_02_19():
    """Bookend also updates PaperTrade.current_price and unrealized_pnl."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'bookend_test_user')
    # Entry 3.0, BUY, qty=1
    trade_id = seed_open_trade(conn, username='bookend_test_user', ticker='MSFT',
                               entry_price=3.0, qty=1, direction='BUY')

    try:
        ms = MonitorService()
        # Mark = (5.0 + 6.0) / 2 = 5.5 → pnl = (5.5 - 3.0) × 1 × 100 = 250.0
        mock_quote = {'price': 400.0, 'bid': 5.0, 'ask': 6.0}

        with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
            with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                engine = create_engine(OWNER_URL)
                Session = sessionmaker(bind=engine)
                session = Session()
                mock_get_db.return_value = session
                ms.capture_bookend_snapshot('OPEN_BOOKEND')

        cur = conn.cursor()
        cur.execute("SELECT current_price, unrealized_pnl FROM paper_trades WHERE id = %s", (trade_id,))
        row = cur.fetchone()
        assert row[0] == 5.5, f"current_price expected 5.5, got {row[0]}"
        assert row[1] == 250.0, f"unrealized_pnl expected 250.0, got {row[1]}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'bookend_test_user')
        conn.close()

test("T-02-19", "Bookend updates PaperTrade.current_price and unrealized_pnl", t_02_19)


# =========================================================================
# F. ERROR RESILIENCE (T-02-20 to T-02-23)
# =========================================================================


def t_02_20():
    """ORATS returns None for unknown ticker → skip, no crash."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'err_test_user')
    trade_id = seed_open_trade(conn, username='err_test_user', ticker='FAKEXYZ', entry_price=5.0)

    try:
        ms = MonitorService()

        with patch('backend.services.monitor_service.is_market_open', return_value=True):
            with patch.object(ms.orats, 'get_quote', return_value=None):
                with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                    engine = create_engine(OWNER_URL)
                    Session = sessionmaker(bind=engine)
                    session = Session()
                    mock_get_db.return_value = session
                    # Should NOT raise
                    ms.update_price_snapshots()

        # No snapshot should be written
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM price_snapshots WHERE trade_id = %s", (trade_id,))
        count = cur.fetchone()[0]
        assert count == 0, f"Expected 0 snapshots for null quote, got {count}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'err_test_user')
        conn.close()

test("T-02-20", "ORATS returns None → skip ticker, no crash", t_02_20)


def t_02_21():
    """DB connection error in snapshot job → rollback, no crash."""
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    with patch('backend.services.monitor_service.is_market_open', return_value=True):
        with patch('backend.services.monitor_service.get_paper_db_system') as mock_get_db:
            mock_session = MagicMock()
            mock_session.query.side_effect = Exception("DB connection lost")
            mock_get_db.return_value = mock_session

            # Should NOT raise (internal try/except handles it)
            ms.update_price_snapshots()

            # Verify rollback was called
            mock_session.rollback.assert_called_once()

test("T-02-21", "DB exception → rollback, no crash", t_02_21)


def t_02_22():
    """BrokerAuthException for one user → other users still sync."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerAuthException

    ms = MonitorService()

    # Create mock user settings for two users
    user_a = MagicMock()
    user_a.username = 'user_a'
    user_b = MagicMock()
    user_b.username = 'user_b'

    sync_calls = []

    def mock_sync_user(db, user_settings):
        if user_settings.username == 'user_a':
            raise BrokerAuthException("Token expired for user_a")
        sync_calls.append(user_settings.username)

    with patch('backend.services.monitor_service.is_market_open', return_value=True):
        with patch('backend.services.monitor_service.get_paper_db_system') as mock_get_db:
            mock_session = MagicMock()
            # Return both users
            mock_query = MagicMock()
            mock_query.filter.return_value.all.return_value = [user_a, user_b]
            mock_session.query.return_value = mock_query
            mock_get_db.return_value = mock_session

            # Mock advisory lock to succeed
            with patch.object(ms, '_acquire_advisory_lock', return_value=True):
                with patch.object(ms, '_release_advisory_lock'):
                    with patch.object(ms, '_sync_user_orders', side_effect=mock_sync_user):
                        ms.sync_tradier_orders()

    # user_b should still have been called despite user_a's auth failure
    assert 'user_b' in sync_calls, f"user_b should have synced despite user_a auth failure"

test("T-02-22", "BrokerAuthException for one user → others still sync", t_02_22)


def t_02_23():
    """BrokerRateLimitException → graceful skip, retry next cycle."""
    from backend.services.monitor_service import MonitorService
    from backend.services.broker.exceptions import BrokerRateLimitException

    ms = MonitorService()

    user_a = MagicMock()
    user_a.username = 'rate_limited_user'

    def mock_sync_user(db, user_settings):
        raise BrokerRateLimitException("Rate limit hit")

    with patch('backend.services.monitor_service.is_market_open', return_value=True):
        with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
            mock_session = MagicMock()
            mock_query = MagicMock()
            mock_query.filter.return_value.all.return_value = [user_a]
            mock_session.query.return_value = mock_query
            mock_get_db.return_value = mock_session

            with patch.object(ms, '_sync_user_orders', side_effect=mock_sync_user):
                # Should NOT raise — rate limit is caught and logged
                ms.sync_tradier_orders()

test("T-02-23", "BrokerRateLimitException → graceful skip, no crash", t_02_23)


# =========================================================================
# G. EDGE CASES (T-02-24 to T-02-25)
# =========================================================================


def t_02_24():
    """No open trades → both jobs return immediately (no-op)."""
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    with patch('backend.services.monitor_service.is_market_open', return_value=True):
        with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
            mock_session = MagicMock()
            mock_query_result = MagicMock()
            mock_query_result.filter.return_value.all.return_value = []
            mock_session.query.return_value = mock_query_result
            mock_get_db.return_value = mock_session

            # Should exit early without doing anything
            ms.update_price_snapshots()

            # orats.get_quote should never be called
            with patch.object(ms.orats, 'get_quote') as mock_quote:
                ms.update_price_snapshots()
                mock_quote.assert_not_called()

test("T-02-24", "No open trades → immediate return (no ORATS calls)", t_02_24)


def t_02_25():
    """Multi-cycle snapshots: 3 cycles → ≥3 rows per trade."""
    from backend.services.monitor_service import MonitorService

    conn = get_owner_conn()
    cleanup_test_data(conn, 'multi_cycle_user')
    trade_id = seed_open_trade(conn, username='multi_cycle_user', ticker='AMD', entry_price=4.0)

    try:
        ms = MonitorService()
        prices = [
            {'price': 100.0, 'bid': 4.5, 'ask': 5.5},
            {'price': 102.0, 'bid': 5.0, 'ask': 6.0},
            {'price': 98.0, 'bid': 3.5, 'ask': 4.5},
        ]

        for i, mock_quote in enumerate(prices):
            with patch('backend.services.monitor_service.is_market_open', return_value=True):
                with patch.object(ms.orats, 'get_quote', return_value=mock_quote):
                    with patch('backend.services.monitor_service.get_paper_db') as mock_get_db:
                        engine = create_engine(OWNER_URL)
                        Session = sessionmaker(bind=engine)
                        session = Session()
                        mock_get_db.return_value = session
                        ms.update_price_snapshots()

        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM price_snapshots WHERE trade_id = %s", (trade_id,))
        count = cur.fetchone()[0]
        assert count >= 3, f"Expected ≥3 snapshots after 3 cycles, got {count}"

        # Verify the latest price is from the last cycle
        cur.execute("SELECT current_price FROM paper_trades WHERE id = %s", (trade_id,))
        latest_price = cur.fetchone()[0]
        last_mark = (3.5 + 4.5) / 2  # 4.0
        assert latest_price == last_mark, f"Expected {last_mark}, got {latest_price}"
        cur.close()
    finally:
        cleanup_test_data(conn, 'multi_cycle_user')
        conn.close()

test("T-02-25", "Multi-cycle: 3 cycles → ≥3 snapshots, latest price correct", t_02_25)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*60}")
print(f"Point 2 Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
