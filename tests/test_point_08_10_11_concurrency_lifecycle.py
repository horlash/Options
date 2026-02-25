"""
Points 8+10+11 Integration Tests
==================================
40 tests across 10 groups (all service-level, no Flask test client):
  A. Optimistic Locking - Version Column (T-08-01..06)
  B. Version Column DB Mechanics (T-08-07..10)
  C. Idempotency Keys DB Level (T-10-01..06)
  D. Connection Pool Config (T-10-07..09)
  E. TradeStatus Enum (T-11-01..04)
  F. Lifecycle Transitions (T-11-05..10)
  G. StateTransition Audit Trail (T-11-11..16)
  H. LifecycleManager Unit Tests (T-11-17..19)
  I. Status CHECK Constraint Edge Cases (T-11-20..22)
  J. Cross-Point Integration (T-MIX-01..03)
"""

import os, sys, json, uuid, logging
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.WARNING)

DB_URL = 'postgresql://app_user:app_pass@localhost:5433/paper_trading'
OWNER_URL = 'postgresql://paper_user:paper_pass@localhost:5433/paper_trading'

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# -- helpers --
def get_conn():
    return psycopg2.connect(OWNER_URL, cursor_factory=RealDictCursor)

def get_sa_session():
    engine = create_engine(OWNER_URL)
    Session = sessionmaker(bind=engine)
    return Session()

def clean(conn, username):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM state_transitions WHERE trade_id IN (SELECT id FROM paper_trades WHERE username=%s)", (username,))
        cur.execute("DELETE FROM price_snapshots WHERE trade_id IN (SELECT id FROM paper_trades WHERE username=%s)", (username,))
        cur.execute("DELETE FROM paper_trades WHERE username=%s", (username,))
        cur.execute("DELETE FROM user_settings WHERE username=%s", (username,))
    conn.commit()

def insert_trade(conn, username, status='OPEN', version=1, **kw):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO paper_trades (username, ticker, option_type, strike, expiry,
                entry_price, qty, status, version, direction, idempotency_key,
                sl_price, tp_price, current_price, tradier_order_id)
            VALUES (%s,'AAPL','CALL',150,'2026-06-20',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (
            username,
            kw.get('entry_price', 5.0),
            kw.get('qty', 1),
            status, version,
            kw.get('direction', 'BUY'),
            kw.get('idempotency_key'),
            kw.get('sl_price'),
            kw.get('tp_price'),
            kw.get('current_price'),
            kw.get('tradier_order_id'),
        ))
        conn.commit()
        return cur.fetchone()['id']

def get_trade(conn, trade_id):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM paper_trades WHERE id=%s", (trade_id,))
        return cur.fetchone()

def get_transitions(conn, trade_id):
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM state_transitions WHERE trade_id=%s ORDER BY created_at", (trade_id,))
        return cur.fetchall()


# -- test runner --
results = {'pass': 0, 'fail': 0, 'errors': []}

def test(test_id, description):
    def decorator(fn):
        def wrapper():
            try:
                fn()
                results['pass'] += 1
                print(f"  PASS {test_id}: {description}")
            except Exception as e:
                results['fail'] += 1
                results['errors'].append((test_id, str(e)))
                print(f"  FAIL {test_id}: {description}")
                import traceback; traceback.print_exc()
        wrapper._test_id = test_id
        wrapper._desc = description
        return wrapper
    return decorator


# ================================================================
# A. Optimistic Locking - Version Column (T-08-01..06)
# ================================================================

@test("T-08-01", "New trade starts with version=1")
def t08_01():
    conn = get_conn()
    try:
        clean(conn, 'ver_user')
        tid = insert_trade(conn, 'ver_user')
        t = get_trade(conn, tid)
        assert t['version'] == 1, f"Expected 1, got {t['version']}"
    finally:
        clean(conn, 'ver_user'); conn.close()

@test("T-08-02", "_handle_fill increments version 1->2")
def t08_02():
    conn = get_conn()
    try:
        clean(conn, 'ver_fill')
        tid = insert_trade(conn, 'ver_fill', entry_price=5.0)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2, f"Expected 2, got {t['version']}"
        assert t['status'] == 'CLOSED'
    finally:
        clean(conn, 'ver_fill'); conn.close()

@test("T-08-03", "_handle_expiration increments version 1->2")
def t08_03():
    conn = get_conn()
    try:
        clean(conn, 'ver_exp')
        tid = insert_trade(conn, 'ver_exp', entry_price=5.0)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_expiration(db, trade)
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2
        assert t['status'] == 'EXPIRED'
    finally:
        clean(conn, 'ver_exp'); conn.close()

@test("T-08-04", "_handle_cancellation increments version 1->2")
def t08_04():
    conn = get_conn()
    try:
        clean(conn, 'ver_can')
        tid = insert_trade(conn, 'ver_can')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_cancellation(db, trade, 'canceled')
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2
        assert t['status'] == 'CANCELED'
    finally:
        clean(conn, 'ver_can'); conn.close()

@test("T-08-05", "Version column via _handle_fill + verify version bump")
def t08_05():
    conn = get_conn()
    try:
        clean(conn, 'ver_mc')
        tid = insert_trade(conn, 'ver_mc', entry_price=5.0, current_price=6.0)
        from backend.database.paper_models import PaperTrade
        from backend.services.monitor_service import MonitorService
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2
        assert t['status'] == 'CLOSED'
    finally:
        clean(conn, 'ver_mc'); conn.close()

@test("T-08-06", "Version bump via raw SQL update")
def t08_06():
    conn = get_conn()
    try:
        clean(conn, 'ver_adj')
        tid = insert_trade(conn, 'ver_adj', sl_price=3.0, tp_price=8.0)
        with conn.cursor() as cur:
            cur.execute("UPDATE paper_trades SET version = version + 1, sl_price = 2.5, tp_price = 9.0 WHERE id = %s", (tid,))
        conn.commit()
        t = get_trade(conn, tid)
        assert t['version'] == 2
        assert float(t['sl_price']) == 2.5
        assert float(t['tp_price']) == 9.0
    finally:
        clean(conn, 'ver_adj'); conn.close()


# ================================================================
# B. Version Column DB Mechanics (T-08-07..10)
# ================================================================

@test("T-08-07", "Stale version UPDATE affects 0 rows (optimistic lock)")
def t08_07():
    conn = get_conn()
    try:
        clean(conn, 'opt_lock')
        tid = insert_trade(conn, 'opt_lock', current_price=6.0)
        # Version is 1, try to update with WHERE version=0
        with conn.cursor() as cur:
            cur.execute("UPDATE paper_trades SET status='CLOSED', version=version+1 WHERE id=%s AND version=0", (tid,))
            assert cur.rowcount == 0, f"Expected 0 rows affected, got {cur.rowcount}"
        conn.rollback()
        t = get_trade(conn, tid)
        assert t['status'] == 'OPEN'  # Unchanged
    finally:
        clean(conn, 'opt_lock'); conn.close()

@test("T-08-08", "Matching version UPDATE affects 1 row")
def t08_08():
    conn = get_conn()
    try:
        clean(conn, 'opt_match')
        tid = insert_trade(conn, 'opt_match', current_price=6.0)
        with conn.cursor() as cur:
            cur.execute("UPDATE paper_trades SET status='CLOSED', version=version+1 WHERE id=%s AND version=1", (tid,))
            assert cur.rowcount == 1, f"Expected 1 row affected, got {cur.rowcount}"
        conn.commit()
        t = get_trade(conn, tid)
        assert t['status'] == 'CLOSED'
        assert t['version'] == 2
    finally:
        clean(conn, 'opt_match'); conn.close()

@test("T-08-09", "Double version bump: 1->2->3")
def t08_09():
    conn = get_conn()
    try:
        clean(conn, 'ver_double')
        tid = insert_trade(conn, 'ver_double')
        with conn.cursor() as cur:
            cur.execute("UPDATE paper_trades SET version=version+1 WHERE id=%s AND version=1 RETURNING version", (tid,))
            row = cur.fetchone()
            assert row['version'] == 2
            cur.execute("UPDATE paper_trades SET version=version+1 WHERE id=%s AND version=2 RETURNING version", (tid,))
            row = cur.fetchone()
            assert row['version'] == 3
        conn.commit()
    finally:
        clean(conn, 'ver_double'); conn.close()

@test("T-08-10", "Version column default is 1")
def t08_10():
    conn = get_conn()
    try:
        clean(conn, 'ver_default')
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, status)
                VALUES ('ver_default','AAPL','CALL',150,'2026-06-20',5.0,'OPEN')
                RETURNING version
            """)
            conn.commit()
            row = cur.fetchone()
            assert row['version'] == 1
    finally:
        clean(conn, 'ver_default'); conn.close()


# ================================================================
# C. Idempotency Keys DB Level (T-10-01..06)
# ================================================================

@test("T-10-01", "Insert trade with idempotency_key succeeds")
def t10_01():
    conn = get_conn()
    try:
        clean(conn, 'idem_user')
        key = str(uuid.uuid4())
        tid = insert_trade(conn, 'idem_user', idempotency_key=key)
        t = get_trade(conn, tid)
        assert t['idempotency_key'] == key
    finally:
        clean(conn, 'idem_user'); conn.close()

@test("T-10-02", "Duplicate idempotency_key -> UniqueViolation")
def t10_02():
    conn = get_conn()
    try:
        clean(conn, 'idem_dup')
        key = 'dup-test-key-001'
        insert_trade(conn, 'idem_dup', idempotency_key=key)
        try:
            insert_trade(conn, 'idem_dup', idempotency_key=key)
            assert False, "Should have raised UniqueViolation"
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
    finally:
        clean(conn, 'idem_dup'); conn.close()

@test("T-10-03", "NULL idempotency_key allows multiple inserts")
def t10_03():
    conn = get_conn()
    try:
        clean(conn, 'idem_null')
        t1 = insert_trade(conn, 'idem_null', idempotency_key=None)
        t2 = insert_trade(conn, 'idem_null', idempotency_key=None)
        assert t1 != t2
    finally:
        clean(conn, 'idem_null'); conn.close()

@test("T-10-04", "Two different idempotency keys create 2 distinct trades")
def t10_04():
    conn = get_conn()
    try:
        clean(conn, 'idem_two')
        t1 = insert_trade(conn, 'idem_two', idempotency_key='key-a')
        t2 = insert_trade(conn, 'idem_two', idempotency_key='key-b')
        assert t1 != t2
    finally:
        clean(conn, 'idem_two'); conn.close()

@test("T-10-05", "Idempotency key stored as-is in DB")
def t10_05():
    conn = get_conn()
    try:
        clean(conn, 'idem_stored')
        key = 'my-special-key-123'
        tid = insert_trade(conn, 'idem_stored', idempotency_key=key)
        t = get_trade(conn, tid)
        assert t['idempotency_key'] == key
    finally:
        clean(conn, 'idem_stored'); conn.close()

@test("T-10-06", "Idempotency key uniqueness is per-table (cross-user OK if different key)")
def t10_06():
    conn = get_conn()
    try:
        clean(conn, 'idem_u1')
        clean(conn, 'idem_u2')
        t1 = insert_trade(conn, 'idem_u1', idempotency_key='shared-key')
        t2 = insert_trade(conn, 'idem_u2', idempotency_key='shared-key-2')
        assert t1 != t2
    finally:
        clean(conn, 'idem_u1')
        clean(conn, 'idem_u2')
        conn.close()


# ================================================================
# D. Connection Pool Config (T-10-07..09)
# ================================================================

@test("T-10-07", "paper_engine pool_size == 10")
def t10_07():
    from backend.database.paper_session import paper_engine
    assert paper_engine.pool.size() == 10, f"Got {paper_engine.pool.size()}"

@test("T-10-08", "Engine isolation level is REPEATABLE_READ")
def t10_08():
    from backend.database.paper_session import paper_engine
    conn = paper_engine.connect()
    try:
        result = conn.execute(__import__('sqlalchemy').text("SHOW transaction_isolation")).scalar()
        assert 'repeatable' in result.lower(), f"Got {result}"
    finally:
        conn.close()

@test("T-10-09", "pool_pre_ping is enabled")
def t10_09():
    from backend.database.paper_session import paper_engine
    assert paper_engine.pool._pre_ping is True


# ================================================================
# E. TradeStatus Enum (T-11-01..04)
# ================================================================

@test("T-11-01", "TradeStatus has exactly 7 members")
def t11_01():
    from backend.database.paper_models import TradeStatus
    assert len(TradeStatus) == 7, f"Got {len(TradeStatus)}"

@test("T-11-02", "All 7 status values accepted by DB CHECK constraint")
def t11_02():
    conn = get_conn()
    try:
        clean(conn, 'enum_check')
        for s in ['PENDING','OPEN','PARTIALLY_FILLED','CLOSING','CLOSED','EXPIRED','CANCELED']:
            tid = insert_trade(conn, 'enum_check', status=s)
            t = get_trade(conn, tid)
            assert t['status'] == s
    finally:
        clean(conn, 'enum_check'); conn.close()

@test("T-11-03", "INVALID status rejected by DB CHECK constraint")
def t11_03():
    conn = get_conn()
    try:
        clean(conn, 'enum_bad')
        try:
            insert_trade(conn, 'enum_bad', status='INVALID')
            assert False, "Should have raised CheckViolation"
        except psycopg2.errors.CheckViolation:
            conn.rollback()
    finally:
        clean(conn, 'enum_bad'); conn.close()

@test("T-11-04", "Default status is PENDING")
def t11_04():
    conn = get_conn()
    try:
        clean(conn, 'enum_default')
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, version)
                VALUES ('enum_default','AAPL','CALL',150,'2026-06-20',5.0,1)
                RETURNING id, status
            """)
            conn.commit()
            row = cur.fetchone()
            assert row['status'] == 'PENDING', f"Got {row['status']}"
    finally:
        clean(conn, 'enum_default'); conn.close()


# ================================================================
# F. Lifecycle Transitions (T-11-05..10)
# ================================================================

@test("T-11-05", "_handle_fill -> status=CLOSED, close_reason set")
def t11_05():
    conn = get_conn()
    try:
        clean(conn, 'lc_fill')
        tid = insert_trade(conn, 'lc_fill', entry_price=5.0, sl_price=3.0, tp_price=8.0)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 8.5})
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['status'] == 'CLOSED'
        assert t['close_reason'] == 'TP_HIT'
    finally:
        clean(conn, 'lc_fill'); conn.close()

@test("T-11-06", "_handle_expiration -> status=EXPIRED, exit_price=0, P&L=full loss")
def t11_06():
    conn = get_conn()
    try:
        clean(conn, 'lc_exp')
        tid = insert_trade(conn, 'lc_exp', entry_price=5.0, qty=2)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_expiration(db, trade)
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['status'] == 'EXPIRED'
        assert t['exit_price'] == 0.0
        assert t['realized_pnl'] == -1000.0  # -(5.0 * 2 * 100)
    finally:
        clean(conn, 'lc_exp'); conn.close()

@test("T-11-07", "_handle_cancellation('rejected') -> CANCELED, reason=REJECTED")
def t11_07():
    conn = get_conn()
    try:
        clean(conn, 'lc_rej')
        tid = insert_trade(conn, 'lc_rej')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_cancellation(db, trade, 'rejected')
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['status'] == 'CANCELED'
        assert t['close_reason'] == 'REJECTED'
    finally:
        clean(conn, 'lc_rej'); conn.close()

@test("T-11-08", "_handle_cancellation('canceled') -> CANCELED, reason=CANCELED")
def t11_08():
    conn = get_conn()
    try:
        clean(conn, 'lc_can2')
        tid = insert_trade(conn, 'lc_can2')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_cancellation(db, trade, 'canceled')
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['status'] == 'CANCELED'
        assert t['close_reason'] == 'CANCELED'
    finally:
        clean(conn, 'lc_can2'); conn.close()

@test("T-11-09", "Expired trade P&L = -(entry_price * qty * 100)")
def t11_09():
    conn = get_conn()
    try:
        clean(conn, 'lc_pnl')
        tid = insert_trade(conn, 'lc_pnl', entry_price=3.50, qty=3)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_expiration(db, trade)
        db.commit(); db.close()
        t = get_trade(conn, tid)
        expected = -(3.50 * 3 * 100)
        assert t['realized_pnl'] == expected, f"Expected {expected}, got {t['realized_pnl']}"
    finally:
        clean(conn, 'lc_pnl'); conn.close()

@test("T-11-10", "All 3 handlers set closed_at timestamp")
def t11_10():
    conn = get_conn()
    try:
        clean(conn, 'lc_ts')
        t1 = insert_trade(conn, 'lc_ts')
        t2 = insert_trade(conn, 'lc_ts')
        t3 = insert_trade(conn, 'lc_ts')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade1 = db.query(PaperTrade).filter_by(id=t1).first()
        ms._handle_fill(db, trade1, {'avg_fill_price': 6.0})
        trade2 = db.query(PaperTrade).filter_by(id=t2).first()
        ms._handle_expiration(db, trade2)
        trade3 = db.query(PaperTrade).filter_by(id=t3).first()
        ms._handle_cancellation(db, trade3, 'canceled')
        db.commit(); db.close()
        for tid in [t1, t2, t3]:
            t = get_trade(conn, tid)
            assert t['closed_at'] is not None, f"Trade {tid} closed_at is None"
    finally:
        clean(conn, 'lc_ts'); conn.close()


# ================================================================
# G. StateTransition Audit Trail (T-11-11..16)
# ================================================================

@test("T-11-11", "_handle_fill creates StateTransition OPEN->CLOSED")
def t11_11():
    conn = get_conn()
    try:
        clean(conn, 'audit_fill2')
        tid = insert_trade(conn, 'audit_fill2')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        assert len(transitions) >= 1
        last = transitions[-1]
        assert last['from_status'] == 'OPEN'
        assert last['to_status'] == 'CLOSED'
        assert last['trigger'] == 'BROKER_FILL'
    finally:
        clean(conn, 'audit_fill2'); conn.close()

@test("T-11-12", "_handle_fill transition trigger=BROKER_FILL")
def t11_12():
    conn = get_conn()
    try:
        clean(conn, 'audit_fill')
        tid = insert_trade(conn, 'audit_fill')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        assert len(transitions) >= 1
        last = transitions[-1]
        assert last['from_status'] == 'OPEN'
        assert last['to_status'] == 'CLOSED'
        assert last['trigger'] == 'BROKER_FILL'
    finally:
        clean(conn, 'audit_fill'); conn.close()

@test("T-11-13", "_handle_expiration -> transition OPEN->EXPIRED, trigger=BROKER_EXPIRED")
def t11_13():
    conn = get_conn()
    try:
        clean(conn, 'audit_exp')
        tid = insert_trade(conn, 'audit_exp')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_expiration(db, trade)
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        last = transitions[-1]
        assert last['from_status'] == 'OPEN'
        assert last['to_status'] == 'EXPIRED'
        assert last['trigger'] == 'BROKER_EXPIRED'
    finally:
        clean(conn, 'audit_exp'); conn.close()

@test("T-11-14", "_handle_cancellation -> transition OPEN->CANCELED")
def t11_14():
    conn = get_conn()
    try:
        clean(conn, 'audit_can')
        tid = insert_trade(conn, 'audit_can')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_cancellation(db, trade, 'canceled')
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        last = transitions[-1]
        assert last['from_status'] == 'OPEN'
        assert last['to_status'] == 'CANCELED'
    finally:
        clean(conn, 'audit_can'); conn.close()

@test("T-11-15", "Fill audit metadata contains fill_price, close_reason, pnl")
def t11_15():
    conn = get_conn()
    try:
        clean(conn, 'audit_meta')
        tid = insert_trade(conn, 'audit_meta', entry_price=5.0)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 7.0})
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        last = transitions[-1]
        meta = last['metadata_json'] if isinstance(last['metadata_json'], dict) else json.loads(last['metadata_json'])
        assert 'fill_price' in meta
        assert 'close_reason' in meta
        assert 'pnl' in meta
    finally:
        clean(conn, 'audit_meta'); conn.close()

@test("T-11-16", "CASCADE DELETE: deleting trade removes state transitions")
def t11_16():
    conn = get_conn()
    try:
        clean(conn, 'audit_cascade')
        tid = insert_trade(conn, 'audit_cascade')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        transitions = get_transitions(conn, tid)
        assert len(transitions) >= 1
        with conn.cursor() as cur:
            cur.execute("DELETE FROM paper_trades WHERE id=%s", (tid,))
        conn.commit()
        transitions = get_transitions(conn, tid)
        assert len(transitions) == 0
    finally:
        clean(conn, 'audit_cascade'); conn.close()


# ================================================================
# H. LifecycleManager Unit Tests (T-11-17..19)
# ================================================================

@test("T-11-17", "LifecycleManager.can_transition validates OPEN->CLOSED")
def t11_17():
    from backend.services.lifecycle import LifecycleManager
    lm = LifecycleManager(None)
    assert lm.can_transition('OPEN', 'CLOSED') is True

@test("T-11-18", "LifecycleManager.can_transition rejects CLOSED->OPEN")
def t11_18():
    from backend.services.lifecycle import LifecycleManager
    lm = LifecycleManager(None)
    assert lm.can_transition('CLOSED', 'OPEN') is False

@test("T-11-19", "LifecycleManager.get_allowed_transitions returns correct set")
def t11_19():
    from backend.services.lifecycle import LifecycleManager
    from backend.database.paper_models import TradeStatus
    lm = LifecycleManager(None)
    allowed = lm.get_allowed_transitions('OPEN')
    assert TradeStatus.CLOSED in allowed
    assert TradeStatus.EXPIRED in allowed
    assert TradeStatus.CANCELED in allowed
    assert TradeStatus.PENDING not in allowed


# ================================================================
# I. Status CHECK Constraint Edge Cases (T-11-20..22)
# ================================================================

@test("T-11-20", "Insert PARTIALLY_FILLED status -> accepted")
def t11_20():
    conn = get_conn()
    try:
        clean(conn, 'ck_pf')
        tid = insert_trade(conn, 'ck_pf', status='PARTIALLY_FILLED')
        t = get_trade(conn, tid)
        assert t['status'] == 'PARTIALLY_FILLED'
    finally:
        clean(conn, 'ck_pf'); conn.close()

@test("T-11-21", "Insert CLOSING status -> accepted")
def t11_21():
    conn = get_conn()
    try:
        clean(conn, 'ck_cl')
        tid = insert_trade(conn, 'ck_cl', status='CLOSING')
        t = get_trade(conn, tid)
        assert t['status'] == 'CLOSING'
    finally:
        clean(conn, 'ck_cl'); conn.close()

@test("T-11-22", "Insert empty string status -> rejected by CHECK")
def t11_22():
    conn = get_conn()
    try:
        clean(conn, 'ck_empty')
        try:
            insert_trade(conn, 'ck_empty', status='')
            assert False, "Should have raised CheckViolation"
        except psycopg2.errors.CheckViolation:
            conn.rollback()
    finally:
        clean(conn, 'ck_empty'); conn.close()


# ================================================================
# J. Cross-Point Integration (T-MIX-01..03)
# ================================================================

@test("T-MIX-01", "Fill: version bumps AND status=CLOSED AND transition logged simultaneously")
def tmix_01():
    conn = get_conn()
    try:
        clean(conn, 'mix_fill')
        tid = insert_trade(conn, 'mix_fill', entry_price=5.0)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_fill(db, trade, {'avg_fill_price': 6.0})
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2, "Version should be 2"
        assert t['status'] == 'CLOSED', "Status should be CLOSED"
        transitions = get_transitions(conn, tid)
        assert len(transitions) >= 1, "Should have audit record"
        assert transitions[-1]['to_status'] == 'CLOSED'
    finally:
        clean(conn, 'mix_fill'); conn.close()

@test("T-MIX-02", "Expiration + cancellation: different terminal states, both audited")
def tmix_02():
    conn = get_conn()
    try:
        clean(conn, 'mix_multi')
        t1 = insert_trade(conn, 'mix_multi', entry_price=5.0)
        t2 = insert_trade(conn, 'mix_multi')
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade1 = db.query(PaperTrade).filter_by(id=t1).first()
        ms._handle_expiration(db, trade1)
        trade2 = db.query(PaperTrade).filter_by(id=t2).first()
        ms._handle_cancellation(db, trade2, 'canceled')
        db.commit(); db.close()
        tr1 = get_transitions(conn, t1)
        tr2 = get_transitions(conn, t2)
        assert tr1[-1]['to_status'] == 'EXPIRED'
        assert tr2[-1]['to_status'] == 'CANCELED'
    finally:
        clean(conn, 'mix_multi'); conn.close()

@test("T-MIX-03", "Expired trade: version=2, status=EXPIRED, transition logged, P&L negative")
def tmix_03():
    conn = get_conn()
    try:
        clean(conn, 'mix_exp')
        tid = insert_trade(conn, 'mix_exp', entry_price=4.0, qty=2)
        from backend.services.monitor_service import MonitorService
        from backend.database.paper_models import PaperTrade
        ms = MonitorService()
        db = get_sa_session()
        trade = db.query(PaperTrade).filter_by(id=tid).first()
        ms._handle_expiration(db, trade)
        db.commit(); db.close()
        t = get_trade(conn, tid)
        assert t['version'] == 2
        assert t['status'] == 'EXPIRED'
        assert t['realized_pnl'] < 0
        transitions = get_transitions(conn, tid)
        assert any(tr['to_status'] == 'EXPIRED' for tr in transitions)
    finally:
        clean(conn, 'mix_exp'); conn.close()


# ================================================================
# Run all tests
# ================================================================

if __name__ == '__main__':
    all_tests = [v for v in globals().values() if callable(v) and hasattr(v, '_test_id')]
    all_tests.sort(key=lambda f: f._test_id)

    print("\n" + "=" * 60)
    print("Points 8+10+11: Concurrency, Sync & Lifecycle Tests")
    print("=" * 60 + "\n")

    for t in all_tests:
        t()

    print("\n" + "=" * 60)
    total = results['pass'] + results['fail']
    print(f"Results: {results['pass']}/{total} passed, {results['fail']} failed")
    print("=" * 60)

    if results['errors']:
        print("\nFailures:")
        for tid, err in results['errors']:
            print(f"  {tid}: {err}")

    sys.exit(0 if results['fail'] == 0 else 1)
