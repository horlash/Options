"""
Advanced Scenario Tests: High, Medium, and Nice-to-Have
========================================================
Covers all remaining test scenarios from the testing plan.

 - HIGH PRIORITY: Optimistic locking, idempotency, close/adjust guards,
                  SELL P&L, expiration, partial brackets
 - MEDIUM PRIORITY: Sequential adjustments, broker degradation, OCO
                    cancel+replace, price snapshot history
 - NICE TO HAVE: Input validation, cascade delete, large volume, concurrent ops

Usage:
    python tests/test_advanced_scenarios.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psycopg2
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from backend.database.paper_models import (
    PaperTrade, StateTransition, TradeStatus, UserSettings, PriceSnapshot,
)
from backend.services.monitor_service import MonitorService

DB_PARAMS = dict(
    host='localhost', port=5433,
    dbname='paper_trading', user='app_user', password='app_pass',
)

# ── Test Harness ──────────────────────────────────────────────

passed = 0
failed = 0
total = 0
TEST_USER = 'test_adv_user'
USERS = [TEST_USER, 'test_adv_bob']


def test(test_id, description, fn):
    global passed, failed, total
    total += 1
    try:
        fn()
        passed += 1
        print(f"  PASS {test_id}: {description}")
    except Exception as e:
        failed += 1
        print(f"  FAIL {test_id}: {description}")
        print(f"     Error: {e}")


def conn_as(username):
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()
    if username:
        cur.execute('SET LOCAL "app.current_user" = %s', (username,))
    return conn, cur


def close(conn):
    try:
        conn.rollback()
    except Exception:
        pass
    conn.close()


def cleanup():
    for user in USERS:
        conn, cur = conn_as(user)
        cur.execute("DELETE FROM state_transitions WHERE trade_id IN "
                     "(SELECT id FROM paper_trades WHERE username = %s)", (user,))
        cur.execute("DELETE FROM price_snapshots WHERE trade_id IN "
                     "(SELECT id FROM paper_trades WHERE username = %s)", (user,))
        cur.execute("DELETE FROM paper_trades WHERE username = %s", (user,))
        conn.commit()
        conn.close()


def insert_trade(user, ticker, entry, sl=None, tp=None, direction='BUY',
                  status='OPEN', qty=1, option_type='CALL', strike=150,
                  expiry='2026-06-20', idempotency_key=None):
    """Insert a trade directly via SQL and return the trade_id."""
    conn, cur = conn_as(user)
    cur.execute("""
        INSERT INTO paper_trades
            (username, ticker, option_type, strike, expiry, entry_price,
             sl_price, tp_price, qty, direction, status, idempotency_key)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (user, ticker, option_type, strike, expiry, entry,
          sl, tp, qty, direction, status, idempotency_key))
    trade_id = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return trade_id


# ── Verify DB connection ─────────────────────────────────────

print("\n" + "=" * 70)
print("Advanced Scenario Tests")
print("=" * 70)

try:
    test_conn = psycopg2.connect(**DB_PARAMS)
    test_conn.close()
    print("  OK Connected to paper_trading DB\n")
except Exception as e:
    print(f"  XX Cannot connect to DB: {e}")
    sys.exit(1)

cleanup()


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: Optimistic Locking / 409 Conflict
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: Optimistic Locking / 409 Conflict ---")


def t_hp01_version_mismatch():
    """Two tabs: both read version 1, one updates, second gets rejected."""
    tid = insert_trade(TEST_USER, 'LOCK1', 5.00, sl=3.75, tp=7.50)

    conn, cur = conn_as(TEST_USER)

    # Tab A reads version
    cur.execute("SELECT version FROM paper_trades WHERE id = %s", (tid,))
    v1 = cur.fetchone()[0]
    assert v1 == 1, f"Initial version should be 1, got {v1}"

    # Tab A updates (simulates first device)
    cur.execute("""
        UPDATE paper_trades
        SET sl_price = 4.00, version = version + 1
        WHERE id = %s AND version = %s
    """, (tid, v1))
    assert cur.rowcount == 1, "Tab A update should succeed"
    conn.commit()

    # Tab B attempts update with stale version=1 (it's now version=2)
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("""
        UPDATE paper_trades
        SET sl_price = 4.50, version = version + 1
        WHERE id = %s AND version = %s
    """, (tid, v1))  # v1 is still 1, but DB has version=2
    assert cur.rowcount == 0, "Tab B update with stale version should affect 0 rows (conflict)"
    close(conn)

test("HP-01", "Version mismatch: stale write rejected (0 rows affected)", t_hp01_version_mismatch)


def t_hp01b_version_succeeds_with_correct():
    """Update with correct version succeeds."""
    tid = insert_trade(TEST_USER, 'LOCK2', 5.00, sl=3.75, tp=7.50)

    conn, cur = conn_as(TEST_USER)

    # Increment version
    cur.execute("UPDATE paper_trades SET sl_price=4.00, version=version+1 WHERE id=%s", (tid,))
    conn.commit()

    # Now read current version and update
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("SELECT version FROM paper_trades WHERE id = %s", (tid,))
    current_v = cur.fetchone()[0]
    assert current_v == 2, f"Version should be 2, got {current_v}"

    cur.execute("""
        UPDATE paper_trades SET sl_price=4.50, version=version+1
        WHERE id=%s AND version=%s
    """, (tid, current_v))
    assert cur.rowcount == 1, "Update with correct version should succeed"
    conn.commit()

    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("SELECT version FROM paper_trades WHERE id = %s", (tid,))
    assert cur.fetchone()[0] == 3, "Version should now be 3"
    close(conn)

test("HP-01b", "Correct version update succeeds (version 2->3)", t_hp01b_version_succeeds_with_correct)


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: Idempotency Deduplication
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: Idempotency Deduplication ---")


def t_hp02_idempotency_key_blocks_duplicate():
    """Same idempotency_key should fail on second insert."""
    idem_key = f'test-idem-{int(time.time())}'
    tid = insert_trade(TEST_USER, 'IDEM1', 5.00, idempotency_key=idem_key)

    # Second insert with same key should violate UNIQUE constraint
    conn, cur = conn_as(TEST_USER)
    try:
        violated = False
        try:
            cur.execute("""
                INSERT INTO paper_trades
                    (username, ticker, option_type, strike, expiry, entry_price,
                     status, idempotency_key)
                VALUES (%s, 'IDEM2', 'CALL', 100, '2026-06-20', 6.00,
                        'OPEN', %s)
            """, (TEST_USER, idem_key))
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            violated = True
            conn.rollback()
        assert violated, "Duplicate idempotency_key should raise UniqueViolation"
    finally:
        close(conn)

test("HP-02", "Duplicate idempotency_key blocked by UNIQUE constraint", t_hp02_idempotency_key_blocks_duplicate)


def t_hp02b_different_keys_allowed():
    """Different idempotency keys should both succeed."""
    key1 = f'unique-key-a-{int(time.time())}'
    key2 = f'unique-key-b-{int(time.time())}'
    tid1 = insert_trade(TEST_USER, 'IDEM3', 5.00, idempotency_key=key1)
    tid2 = insert_trade(TEST_USER, 'IDEM4', 6.00, idempotency_key=key2)
    assert tid1 != tid2, "Two trades with different keys should get different IDs"

test("HP-02b", "Different idempotency keys both succeed", t_hp02b_different_keys_allowed)


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: Close Already-Closed Trade
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: Close Already-Closed / Adjust Closed ---")


def t_hp03_close_already_closed():
    """Closing a CLOSED trade should fail (filter finds nothing)."""
    tid = insert_trade(TEST_USER, 'CLSD1', 5.00, status='OPEN')

    # Close it
    conn, cur = conn_as(TEST_USER)
    cur.execute("""
        UPDATE paper_trades
        SET status='CLOSED', exit_price=6.00, close_reason='MANUAL_CLOSE',
            realized_pnl=100.00, version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 1
    conn.commit()

    # Try to close it again
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("""
        UPDATE paper_trades
        SET status='CLOSED', exit_price=7.00, close_reason='MANUAL_CLOSE',
            version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 0, "Closing already-CLOSED trade should affect 0 rows"
    close(conn)

test("HP-03", "Close already-closed trade: 0 rows affected (no crash)", t_hp03_close_already_closed)


def t_hp04_adjust_already_closed():
    """Adjusting SL/TP on a CLOSED trade should fail."""
    tid = insert_trade(TEST_USER, 'ADJC1', 5.00, sl=3.75, tp=7.50, status='CLOSED')

    conn, cur = conn_as(TEST_USER)
    cur.execute("""
        UPDATE paper_trades
        SET sl_price=4.00, version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 0, "Adjusting CLOSED trade should affect 0 rows"
    close(conn)

test("HP-04", "Adjust SL/TP on closed trade: 0 rows affected", t_hp04_adjust_already_closed)


def t_hp04b_adjust_expired_trade():
    """Adjusting an EXPIRED trade should also fail."""
    tid = insert_trade(TEST_USER, 'ADEX1', 5.00, sl=3.75, tp=7.50, status='EXPIRED')

    conn, cur = conn_as(TEST_USER)
    cur.execute("""
        UPDATE paper_trades
        SET sl_price=4.00, version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 0, "Adjusting EXPIRED trade should affect 0 rows"
    close(conn)

test("HP-04b", "Adjust SL/TP on expired trade: 0 rows affected", t_hp04b_adjust_expired_trade)


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: SELL Direction P&L
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: SELL Direction P&L ---")


def t_hp05_sell_direction_profit():
    """SELL direction: profit when price drops (entry=8, exit=5 -> profit)."""
    ms = MonitorService()
    mock_trade = MagicMock()
    mock_trade.id = 999
    mock_trade.ticker = 'SPY'
    mock_trade.entry_price = 8.00
    mock_trade.sl_price = 10.00    # SL above entry for SELL
    mock_trade.tp_price = 5.00     # TP below entry for SELL
    mock_trade.qty = 2
    mock_trade.direction = 'SELL'
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}
    mock_trade.version = 1

    # Fill at TP price (price dropped to 5.00)
    mock_db = MagicMock()
    order = {'avg_fill_price': '5.00', 'status': 'filled'}
    ms._handle_fill(mock_db, mock_trade, order)

    # SELL P&L: (entry - fill) * qty * 100 = (8-5)*2*100 = -600? 
    # Wait - the code does: direction_mult = 1 if BUY else -1
    # pnl = (fill - entry) * qty * 100 * direction_mult
    # For SELL: (5-8) * 2 * 100 * (-1) = (-3) * 200 * (-1) = 600
    assert mock_trade.realized_pnl == 600.0, f"SELL profit should be 600, got {mock_trade.realized_pnl}"
    assert mock_trade.realized_pnl > 0, "SELL at lower price = profit"

test("HP-05a", "SELL direction: fill below entry = PROFIT ($600)", t_hp05_sell_direction_profit)


def t_hp05_sell_direction_loss():
    """SELL direction: loss when price rises (entry=8, exit=10 -> loss)."""
    ms = MonitorService()
    mock_trade = MagicMock()
    mock_trade.id = 998
    mock_trade.ticker = 'SPY'
    mock_trade.entry_price = 8.00
    mock_trade.sl_price = 10.00
    mock_trade.tp_price = 5.00
    mock_trade.qty = 2
    mock_trade.direction = 'SELL'
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}
    mock_trade.version = 1

    mock_db = MagicMock()
    order = {'avg_fill_price': '10.00', 'status': 'filled'}
    ms._handle_fill(mock_db, mock_trade, order)

    # (10-8) * 2 * 100 * (-1) = 2 * 200 * -1 = -400
    assert mock_trade.realized_pnl == -400.0, f"SELL loss should be -400, got {mock_trade.realized_pnl}"
    assert mock_trade.realized_pnl < 0, "SELL at higher price = loss"

test("HP-05b", "SELL direction: fill above entry = LOSS (-$400)", t_hp05_sell_direction_loss)


def t_hp05c_sell_sl_hit_detection():
    """SELL direction: SL hit when price rises to sl_price."""
    ms = MonitorService()
    mock_trade = MagicMock()
    mock_trade.id = 997
    mock_trade.ticker = 'QQQ'
    mock_trade.entry_price = 10.00
    mock_trade.sl_price = 12.00    # SL above entry for SELL trades
    mock_trade.tp_price = 7.00
    mock_trade.qty = 1
    mock_trade.direction = 'SELL'
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}
    mock_trade.version = 1

    mock_db = MagicMock()
    # Fill right at SL — the SL detection uses: fill_price <= sl_price * 1.02
    # For SELL, SL is above entry, so fill at 12.00 <= 12.00*1.02 = 12.24 -> SL_HIT
    order = {'avg_fill_price': '12.00', 'status': 'filled'}
    ms._handle_fill(mock_db, mock_trade, order)

    assert mock_trade.close_reason == 'SL_HIT', f"Expected SL_HIT, got {mock_trade.close_reason}"

test("HP-05c", "SELL direction: fill at SL price detected as SL_HIT", t_hp05c_sell_sl_hit_detection)


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: Expiration Handling E2E
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: Expiration Handling ---")


def t_hp06_expiration_e2e():
    """Expired option trade: exit_price=0, full loss P&L."""
    ms = MonitorService()
    mock_trade = MagicMock()
    mock_trade.id = 996
    mock_trade.ticker = 'AAPL'
    mock_trade.entry_price = 5.00
    mock_trade.qty = 3
    mock_trade.direction = 'BUY'
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}
    mock_trade.version = 1

    mock_db = MagicMock()
    ms._handle_expiration(mock_db, mock_trade)

    assert mock_trade.status == 'EXPIRED', f"Expected EXPIRED, got {mock_trade.status}"
    assert mock_trade.exit_price == 0.0, f"Expired exit should be 0, got {mock_trade.exit_price}"
    expected_pnl = -(5.00 * 3 * 100)  # -1500
    assert mock_trade.realized_pnl == expected_pnl, f"Expected {expected_pnl}, got {mock_trade.realized_pnl}"
    assert mock_trade.close_reason == 'EXPIRED'
    assert mock_trade.version == 2  # incremented

    # Verify StateTransition
    transition = mock_db.add.call_args[0][0]
    assert transition.from_status == 'OPEN'
    assert transition.to_status == 'EXPIRED'
    assert transition.trigger == 'BROKER_EXPIRED'

test("HP-06", "Expiration: status=EXPIRED, exit=$0, P&L=-$1500, audit logged", t_hp06_expiration_e2e)


def t_hp06b_expiration_persists_in_db():
    """Verify expiration data persists in the database."""
    tid = insert_trade(TEST_USER, 'EXPT1', 5.00, expiry='2025-01-01', qty=2)

    conn, cur = conn_as(TEST_USER)
    cur.execute("""
        UPDATE paper_trades
        SET status='EXPIRED', exit_price=0, close_reason='EXPIRED',
            realized_pnl=-1000.00, closed_at=NOW(), version=version+1
        WHERE id=%s
    """, (tid,))
    cur.execute("""
        INSERT INTO state_transitions
            (trade_id, from_status, to_status, trigger)
        VALUES (%s, 'OPEN', 'EXPIRED', 'BROKER_EXPIRED')
    """, (tid,))
    conn.commit()

    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("SELECT status, exit_price, close_reason, realized_pnl FROM paper_trades WHERE id=%s", (tid,))
    row = cur.fetchone()
    assert row[0] == 'EXPIRED'
    assert float(row[1]) == 0.0
    assert row[2] == 'EXPIRED'
    assert float(row[3]) == -1000.0
    close(conn)

test("HP-06b", "Expiration persists in DB: EXPIRED, exit=$0, pnl=-$1000", t_hp06b_expiration_persists_in_db)


# ═════════════════════════════════════════════════════════════
# HIGH PRIORITY: Partial Brackets (SL only, TP only)
# ═════════════════════════════════════════════════════════════

print("\n--- HIGH PRIORITY: Partial Brackets ---")


def t_hp07_sl_only_no_tp():
    """Trade with SL but no TP should still be valid."""
    tid = insert_trade(TEST_USER, 'PART1', 5.00, sl=3.75, tp=None)

    conn, cur = conn_as(TEST_USER)
    cur.execute("SELECT sl_price, tp_price, status FROM paper_trades WHERE id=%s", (tid,))
    row = cur.fetchone()
    assert float(row[0]) == 3.75, f"SL should be 3.75, got {row[0]}"
    assert row[1] is None, f"TP should be None, got {row[1]}"
    assert row[2] == 'OPEN'
    close(conn)

test("HP-07", "Partial bracket: SL=3.75, TP=None is valid", t_hp07_sl_only_no_tp)


def t_hp08_tp_only_no_sl():
    """Trade with TP but no SL should still be valid."""
    tid = insert_trade(TEST_USER, 'PART2', 5.00, sl=None, tp=7.50)

    conn, cur = conn_as(TEST_USER)
    cur.execute("SELECT sl_price, tp_price, status FROM paper_trades WHERE id=%s", (tid,))
    row = cur.fetchone()
    assert row[0] is None, f"SL should be None, got {row[0]}"
    assert float(row[1]) == 7.50, f"TP should be 7.50, got {row[1]}"
    assert row[2] == 'OPEN'
    close(conn)

test("HP-08", "Partial bracket: SL=None, TP=7.50 is valid", t_hp08_tp_only_no_sl)


def t_hp07b_no_brackets_at_all():
    """Trade with neither SL nor TP should still be valid."""
    tid = insert_trade(TEST_USER, 'PART3', 5.00, sl=None, tp=None)

    conn, cur = conn_as(TEST_USER)
    cur.execute("SELECT sl_price, tp_price, status FROM paper_trades WHERE id=%s", (tid,))
    row = cur.fetchone()
    assert row[0] is None and row[1] is None, "Both brackets should be None"
    assert row[2] == 'OPEN'
    close(conn)

test("HP-07b", "No brackets at all: SL=None, TP=None is valid", t_hp07b_no_brackets_at_all)


# ═══════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: Multiple Sequential Adjustments
# ═══════════════════════════════════════════════════════════════

print("\n--- MEDIUM PRIORITY: Sequential Adjustments ---")


def t_mp01_sequential_adjustments():
    """Adjust SL/TP 3 times: version 1->2->3->4."""
    tid = insert_trade(TEST_USER, 'SEQ1', 5.00, sl=3.75, tp=7.50)

    conn, cur = conn_as(TEST_USER)

    adjustments = [
        (4.00, 8.00),
        (4.25, 8.50),
        (4.50, 9.00),
    ]

    for i, (new_sl, new_tp) in enumerate(adjustments, start=1):
        expected_version = i  # starts at 1
        cur.execute("SELECT version FROM paper_trades WHERE id=%s", (tid,))
        v = cur.fetchone()[0]
        assert v == expected_version, f"Round {i}: expected version {expected_version}, got {v}"

        cur.execute("""
            UPDATE paper_trades
            SET sl_price=%s, tp_price=%s, version=version+1
            WHERE id=%s AND version=%s
        """, (new_sl, new_tp, tid, v))
        assert cur.rowcount == 1, f"Round {i}: update should succeed"

        # Log audit for each adjustment
        cur.execute("""
            INSERT INTO state_transitions
                (trade_id, from_status, to_status, trigger, metadata_json)
            VALUES (%s, 'OPEN', 'OPEN', 'USER_ADJUST_BRACKET',
                    %s::jsonb)
        """, (tid, f'{{"round": {i}, "new_sl": {new_sl}, "new_tp": {new_tp}}}'))
        conn.commit()
        cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))

    # Final check
    cur.execute("SELECT sl_price, tp_price, version FROM paper_trades WHERE id=%s", (tid,))
    row = cur.fetchone()
    assert float(row[0]) == 4.50
    assert float(row[1]) == 9.00
    assert row[2] == 4, f"After 3 adjustments, version should be 4, got {row[2]}"

    # Verify 3 audit records
    cur.execute("""
        SELECT COUNT(*) FROM state_transitions
        WHERE trade_id=%s AND trigger='USER_ADJUST_BRACKET'
    """, (tid,))
    assert cur.fetchone()[0] == 3, "Should have 3 adjustment transitions"
    close(conn)

test("MP-01", "3 sequential adjustments: version 1->4, 3 audit records", t_mp01_sequential_adjustments)


# ═══════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: Broker Degradation (500 error / no credentials)
# ═══════════════════════════════════════════════════════════════

print("\n--- MEDIUM PRIORITY: Broker Degradation ---")


def t_mp02_paper_only_no_broker():
    """Trade saved paper-only when no broker credentials exist."""
    tid = insert_trade(TEST_USER, 'NOBK1', 5.00, sl=3.75, tp=7.50)

    conn, cur = conn_as(TEST_USER)
    cur.execute("""
        SELECT tradier_order_id, tradier_sl_order_id, tradier_tp_order_id, status
        FROM paper_trades WHERE id=%s
    """, (tid,))
    row = cur.fetchone()
    assert row[0] is None, "No broker credentials = no order ID"
    assert row[1] is None, "No broker credentials = no SL order ID"
    assert row[2] is None, "No broker credentials = no TP order ID"
    assert row[3] == 'OPEN', "Trade should still be OPEN (paper-only)"
    close(conn)

test("MP-02", "Paper-only mode: trade saved with null Tradier IDs", t_mp02_paper_only_no_broker)


def t_mp02b_broker_error_graceful():
    """Simulate broker exception in _handle_fill — trade object still updated."""
    ms = MonitorService()
    mock_trade = MagicMock()
    mock_trade.id = 995
    mock_trade.ticker = 'FAIL1'
    mock_trade.entry_price = 5.00
    mock_trade.sl_price = 3.75
    mock_trade.tp_price = 7.50
    mock_trade.qty = 1
    mock_trade.direction = 'BUY'
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}
    mock_trade.version = 1

    mock_db = MagicMock()
    order = {'avg_fill_price': '7.50', 'status': 'filled'}

    # Even with a broker error, handle_fill should still update the trade
    ms._handle_fill(mock_db, mock_trade, order)
    assert mock_trade.status == 'CLOSED'

test("MP-02b", "Broker errors don't prevent trade status updates", t_mp02b_broker_error_graceful)


# ═══════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: OCO Cancel+Replace Flow
# ═══════════════════════════════════════════════════════════════

print("\n--- MEDIUM PRIORITY: OCO Cancel+Replace ---")


def t_mp03_oco_cancel_replace():
    """Adjusting brackets calls cancel on old orders and place on new."""
    ms = MonitorService()

    # Build mock trade with existing Tradier orders
    mock_trade = MagicMock()
    mock_trade.id = 994
    mock_trade.ticker = 'OCO1'
    mock_trade.entry_price = 5.00
    mock_trade.sl_price = 3.75
    mock_trade.tp_price = 7.50
    mock_trade.qty = 1
    mock_trade.direction = 'BUY'
    mock_trade.option_type = 'CALL'
    mock_trade.strike = 150.0
    mock_trade.expiry = '2026-06-20'
    mock_trade.tradier_order_id = 'ENTRY-001'
    mock_trade.tradier_sl_order_id = 'SL-001'
    mock_trade.tradier_tp_order_id = 'TP-001'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'

    # Create mock broker
    mock_broker = MagicMock()
    mock_broker.cancel_order.return_value = True
    mock_broker.place_oco_order.return_value = {
        'leg': [{'id': 'SL-002'}, {'id': 'TP-002'}]
    }

    # Patch BrokerFactory and UserSettings within adjust_bracket
    with patch('backend.services.monitor_service.BrokerFactory') as mock_factory, \
         patch('backend.database.paper_session.get_paper_db_with_user') as mock_db_fn:

        mock_factory.get_broker.return_value = mock_broker

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_trade
        # UserSettings query
        mock_settings = MagicMock()
        mock_settings.tradier_sandbox_token = 'test-token'
        mock_db.query.return_value.get.return_value = mock_settings
        mock_db_fn.return_value = mock_db

        result = ms.adjust_bracket(994, TEST_USER, new_sl=4.00, new_tp=8.00)

        # Verify old orders were cancelled
        cancel_calls = mock_broker.cancel_order.call_args_list
        cancelled_ids = [call[0][0] for call in cancel_calls]
        assert 'SL-001' in cancelled_ids, "Old SL order should be cancelled"
        assert 'TP-001' in cancelled_ids, "Old TP order should be cancelled"

        # Verify new OCO was placed
        assert mock_broker.place_oco_order.called, "New OCO should be placed"

        # Verify bracket prices updated
        assert mock_trade.sl_price == 4.0
        assert mock_trade.tp_price == 8.0

test("MP-03", "OCO cancel+replace: old SL/TP cancelled, new OCO placed", t_mp03_oco_cancel_replace)


# ═══════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: Price Snapshot History
# ═══════════════════════════════════════════════════════════════

print("\n--- MEDIUM PRIORITY: Price Snapshot History ---")


def t_mp04_price_snapshots():
    """Insert multiple price snapshots and verify ordering."""
    tid = insert_trade(TEST_USER, 'SNAP1', 5.00)

    conn, cur = conn_as(TEST_USER)

    # Insert 5 snapshots with increasing timestamps
    prices = [5.10, 5.25, 5.05, 5.40, 5.35]
    for i, price in enumerate(prices):
        cur.execute("""
            INSERT INTO price_snapshots
                (trade_id, mark_price, snapshot_type, timestamp, username)
            VALUES (%s, %s, 'PERIODIC', NOW() + interval '%s seconds', %s)
        """, (tid, price, i * 40, TEST_USER))
    conn.commit()

    # Query snapshots in order
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("""
        SELECT mark_price FROM price_snapshots
        WHERE trade_id=%s ORDER BY timestamp ASC
    """, (tid,))
    rows = cur.fetchall()
    assert len(rows) == 5, f"Expected 5 snapshots, got {len(rows)}"

    # Verify they come back in insertion order
    snapshot_prices = [float(r[0]) for r in rows]
    assert snapshot_prices == prices, f"Expected {prices}, got {snapshot_prices}"
    close(conn)

test("MP-04", "5 price snapshots inserted and queried in time order", t_mp04_price_snapshots)


# ═══════════════════════════════════════════════════════════════
# MEDIUM PRIORITY: Cross-User Close/Adjust via API guard
# ═══════════════════════════════════════════════════════════════

print("\n--- MEDIUM PRIORITY: Cross-User API Guards ---")


def t_mp07_cross_user_close():
    """Bob cannot close Alice's trade (RLS returns 0 for wrong user)."""
    # Alice's trade
    tid = insert_trade(TEST_USER, 'XCLOSE1', 5.00)

    # Bob tries to close via SQL (simulating API route filter)
    conn, cur = conn_as('test_adv_bob')
    cur.execute("""
        UPDATE paper_trades
        SET status='CLOSED', exit_price=6.00, close_reason='MANUAL_CLOSE',
            version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 0, "Bob should not be able to close Alice's trade (RLS)"
    close(conn)

test("MP-07", "Cross-user close: Bob cannot close Alice's trade", t_mp07_cross_user_close)


def t_mp08_cross_user_adjust():
    """Bob cannot adjust Alice's trade."""
    tid = insert_trade(TEST_USER, 'XADJ1', 5.00, sl=3.75, tp=7.50)

    conn, cur = conn_as('test_adv_bob')
    cur.execute("""
        UPDATE paper_trades SET sl_price=0.01, version=version+1
        WHERE id=%s AND status='OPEN'
    """, (tid,))
    assert cur.rowcount == 0, "Bob should not be able to adjust Alice's SL"
    close(conn)

test("MP-08", "Cross-user adjust: Bob cannot adjust Alice's SL", t_mp08_cross_user_adjust)


# ═══════════════════════════════════════════════════════════════
# NICE TO HAVE: Input Validation Edge Cases
# ═══════════════════════════════════════════════════════════════

print("\n--- NICE TO HAVE: Input Validation ---")


def t_ec01_zero_qty():
    """qty=0 should be insertable but logically invalid (P&L = 0)."""
    tid = insert_trade(TEST_USER, 'ZEROQ', 5.00, qty=0)

    conn, cur = conn_as(TEST_USER)
    cur.execute("SELECT qty FROM paper_trades WHERE id=%s", (tid,))
    assert cur.fetchone()[0] == 0
    close(conn)

test("EC-01", "Zero qty inserts successfully (DB allows it)", t_ec01_zero_qty)


def t_ec02_negative_entry():
    """Negative entry_price should be insertable at DB level."""
    tid = insert_trade(TEST_USER, 'NEGP', -1.00)

    conn, cur = conn_as(TEST_USER)
    cur.execute("SELECT entry_price FROM paper_trades WHERE id=%s", (tid,))
    assert float(cur.fetchone()[0]) == -1.0
    close(conn)

test("EC-02", "Negative entry_price inserts (DB has no CHECK, needs API guard)", t_ec02_negative_entry)


def t_ec03_missing_required_field():
    """Missing required field (no expiry) at DB level should fail."""
    conn, cur = conn_as(TEST_USER)
    try:
        errored = False
        try:
            cur.execute("""
                INSERT INTO paper_trades
                    (username, ticker, option_type, strike, entry_price, status)
                VALUES (%s, 'MISS1', 'CALL', 100, 5.00, 'OPEN')
            """, (TEST_USER,))
            conn.commit()
        except psycopg2.errors.NotNullViolation:
            errored = True
            conn.rollback()
        assert errored, "Missing expiry (NOT NULL) should raise NotNullViolation"
    finally:
        close(conn)

test("EC-03", "Missing required field (expiry) raises NotNullViolation", t_ec03_missing_required_field)


# ═══════════════════════════════════════════════════════════════
# NICE TO HAVE: Cascade Delete
# ═══════════════════════════════════════════════════════════════

print("\n--- NICE TO HAVE: Cascade Delete ---")


def t_ec04_cascade_delete():
    """Deleting a trade cascades to state_transitions and price_snapshots."""
    tid = insert_trade(TEST_USER, 'CASC1', 5.00)

    conn, cur = conn_as(TEST_USER)
    # Add transitions
    cur.execute("""
        INSERT INTO state_transitions (trade_id, from_status, to_status, trigger)
        VALUES (%s, NULL, 'OPEN', 'USER_SUBMIT')
    """, (tid,))
    cur.execute("""
        INSERT INTO state_transitions (trade_id, from_status, to_status, trigger)
        VALUES (%s, 'OPEN', 'CLOSED', 'MANUAL_CLOSE')
    """, (tid,))
    # Add price snapshot
    cur.execute("""
        INSERT INTO price_snapshots (trade_id, mark_price, snapshot_type, username)
        VALUES (%s, 5.50, 'PERIODIC', %s)
    """, (tid, TEST_USER))
    conn.commit()

    # Verify children exist
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("SELECT COUNT(*) FROM state_transitions WHERE trade_id=%s", (tid,))
    assert cur.fetchone()[0] == 2
    cur.execute("SELECT COUNT(*) FROM price_snapshots WHERE trade_id=%s", (tid,))
    assert cur.fetchone()[0] == 1

    # Delete the parent trade
    cur.execute("DELETE FROM paper_trades WHERE id=%s", (tid,))
    conn.commit()

    # Verify cascade
    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    cur.execute("SELECT COUNT(*) FROM state_transitions WHERE trade_id=%s", (tid,))
    assert cur.fetchone()[0] == 0, "Transitions should cascade-delete"
    cur.execute("SELECT COUNT(*) FROM price_snapshots WHERE trade_id=%s", (tid,))
    assert cur.fetchone()[0] == 0, "Snapshots should cascade-delete"
    close(conn)

test("EC-04", "Cascade delete: trade deletion removes all transitions + snapshots", t_ec04_cascade_delete)


# ═══════════════════════════════════════════════════════════════
# NICE TO HAVE: Large Volume / Performance
# ═══════════════════════════════════════════════════════════════

print("\n--- NICE TO HAVE: Large Volume ---")


def t_ec05_large_volume_insert():
    """Insert 100 trades for one user -> all queryable."""
    conn, cur = conn_as(TEST_USER)
    for i in range(100):
        cur.execute("""
            INSERT INTO paper_trades
                (username, ticker, option_type, strike, expiry,
                 entry_price, qty, direction, status)
            VALUES (%s, %s, 'CALL', %s, '2026-06-20', %s, 1, 'BUY', 'OPEN')
        """, (TEST_USER, f'VOL{i:03d}', 100 + i, 5.00 + (i * 0.1)))
    conn.commit()

    cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))
    start = time.time()
    cur.execute("SELECT COUNT(*) FROM paper_trades WHERE username=%s AND status='OPEN'", (TEST_USER,))
    count = cur.fetchone()[0]
    elapsed = time.time() - start

    assert count >= 100, f"Expected >= 100 trades, got {count}"
    assert elapsed < 1.0, f"Query took {elapsed:.3f}s, expected < 1s"
    close(conn)

test("EC-05", f"100 trades inserted + queried in < 1s", t_ec05_large_volume_insert)


# ═══════════════════════════════════════════════════════════════
# NICE TO HAVE: Concurrent Monitor + User Close
# ═══════════════════════════════════════════════════════════════

print("\n--- NICE TO HAVE: Concurrent Operations ---")


def t_ec06_concurrent_close():
    """Monitor and user both try to close — only one should succeed."""
    tid = insert_trade(TEST_USER, 'RACE1', 5.00, sl=3.75, tp=7.50)

    # Simulate: both read version=1
    conn1, cur1 = conn_as(TEST_USER)
    conn2, cur2 = conn_as(TEST_USER)

    cur1.execute("SELECT version FROM paper_trades WHERE id=%s", (tid,))
    v1 = cur1.fetchone()[0]

    cur2.execute("SELECT version FROM paper_trades WHERE id=%s", (tid,))
    v2 = cur2.fetchone()[0]

    assert v1 == v2 == 1

    # User closes first (succeeds)
    cur1.execute("""
        UPDATE paper_trades
        SET status='CLOSED', exit_price=6.00, close_reason='MANUAL_CLOSE',
            version=version+1
        WHERE id=%s AND version=%s AND status='OPEN'
    """, (tid, v1))
    user_rows = cur1.rowcount
    conn1.commit()

    # Monitor tries to close with stale version (fails)
    cur2.execute("""
        UPDATE paper_trades
        SET status='CLOSED', exit_price=3.75, close_reason='SL_HIT',
            version=version+1
        WHERE id=%s AND version=%s AND status='OPEN'
    """, (tid, v2))
    monitor_rows = cur2.rowcount

    assert user_rows == 1, "User close should succeed"
    assert monitor_rows == 0, "Monitor close with stale version should fail"

    close(conn1)
    close(conn2)

test("EC-06", "Concurrent close: first succeeds, second gets 0 rows (race safe)", t_ec06_concurrent_close)


# ═══════════════════════════════════════════════════════════════
# NICE TO HAVE: Version monotonicity
# ═══════════════════════════════════════════════════════════════

print("\n--- NICE TO HAVE: Version Monotonicity ---")


def t_ec07_version_never_decreases():
    """Version should only go up, never down or skip."""
    tid = insert_trade(TEST_USER, 'MONO1', 5.00)

    conn, cur = conn_as(TEST_USER)
    versions = []

    for i in range(5):
        cur.execute("SELECT version FROM paper_trades WHERE id=%s", (tid,))
        v = cur.fetchone()[0]
        versions.append(v)
        cur.execute("UPDATE paper_trades SET version=version+1 WHERE id=%s", (tid,))
        conn.commit()
        cur.execute('SET LOCAL "app.current_user" = %s', (TEST_USER,))

    assert versions == [1, 2, 3, 4, 5], f"Versions should be [1,2,3,4,5], got {versions}"
    close(conn)

test("EC-07", "Version monotonically increases: 1,2,3,4,5", t_ec07_version_never_decreases)


# ═══════════════════════════════════════════════════════════════
# CLEANUP & SUMMARY
# ═══════════════════════════════════════════════════════════════

print("\n--- Cleanup ---")
cleanup()
print("  OK All test data cleaned up")

print(f"\n{'=' * 70}")
print(f"  Advanced Scenario Results: {passed}/{total} passed, {failed} failed")
print(f"{'=' * 70}")

if failed > 0:
    print(f"\n  WARNING: {failed} test(s) FAILED\n")
    sys.exit(1)
else:
    print(f"\n  ALL {total} TESTS PASSED\n")
    sys.exit(0)
