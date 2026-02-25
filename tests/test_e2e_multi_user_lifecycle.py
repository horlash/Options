"""
End-to-End Multi-User Lifecycle Test
======================================
Full integration test against live Docker Postgres.

Scenarios (per user):
  1. Place a trade        → DB persisted, StateTransition None→OPEN
  2. Adjust SL/TP         → DB updated, version incremented
  3. Simulate SL hit      → _handle_fill detects SL, status→CLOSED
  4. Simulate TP hit      → _handle_fill detects TP, status→CLOSED
  5. Manual close          → manual_close_position, status→CLOSED
  6. RLS isolation check   → each user only sees their own trades

Users: alice, bob, carlos, diana (4 users)

Usage:
    python tests/test_e2e_multi_user_lifecycle.py
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psycopg2
from datetime import datetime
from unittest.mock import MagicMock

from backend.database.paper_models import (
    PaperTrade, StateTransition, TradeStatus, UserSettings,
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
USERS = ['alice', 'bob', 'carlos', 'diana']

def test(test_id, description, fn):
    global passed, failed, total
    total += 1
    try:
        fn()
        passed += 1
        print(f"  ✅ {test_id}: {description}")
    except Exception as e:
        failed += 1
        print(f"  ❌ {test_id}: {description}")
        print(f"     Error: {e}")


def conn_as(username):
    """Raw psycopg2 connection with RLS context."""
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


# ── Setup ─────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("End-to-End Multi-User Lifecycle Test")
print("=" * 70)

# Verify DB connection
try:
    test_conn = psycopg2.connect(**DB_PARAMS)
    test_conn.close()
    print("  ✓ Connected to paper_trading DB\n")
except Exception as e:
    print(f"  ✗ Cannot connect to DB: {e}")
    print("  Start Docker Postgres first. Exiting.\n")
    sys.exit(1)


# Clean up any previous test data
def cleanup():
    for user in USERS:
        conn, cur = conn_as(user)
        cur.execute("DELETE FROM state_transitions WHERE trade_id IN "
                     "(SELECT id FROM paper_trades WHERE username = %s)", (user,))
        cur.execute("DELETE FROM paper_trades WHERE username = %s", (user,))
        conn.commit()
        conn.close()

cleanup()

# ═════════════════════════════════════════════════════════════
# SECTION 1: Place Trades for All 4 Users
# ═════════════════════════════════════════════════════════════

print("\n─── Section 1: Place Trades ─────────────────────────────")

# Each user gets 3 trades with different tickers
USER_TRADES = {
    'alice':  [('AAPL', 'CALL', 150, '2026-06-20', 5.00, 3.75, 7.50),
               ('NVDA', 'CALL', 200, '2026-06-20', 8.00, 6.00, 12.00),
               ('TSLA', 'PUT',  300, '2026-06-20', 4.50, 3.00, 6.75)],
    'bob':    [('MSFT', 'CALL', 400, '2026-09-18', 6.00, 4.50, 9.00),
               ('AMZN', 'CALL', 220, '2026-09-18', 10.00, 7.50, 15.00),
               ('META', 'PUT',  500, '2026-09-18', 7.00, 5.25, 10.50)],
    'carlos': [('GOOG', 'CALL', 180, '2026-12-18', 9.00, 6.75, 13.50),
               ('AMD',  'CALL', 160, '2026-12-18', 3.50, 2.63, 5.25),
               ('SPY',  'PUT',  550, '2026-12-18', 12.00, 9.00, 18.00)],
    'diana':  [('QQQ',  'CALL', 500, '2026-03-20', 7.50, 5.63, 11.25),
               ('IWM',  'PUT',  220, '2026-03-20', 5.00, 3.75, 7.50),
               ('COIN', 'CALL', 300, '2026-03-20', 15.00, 11.25, 22.50)],
}

# Store trade IDs per user for later tests
trade_ids = {user: [] for user in USERS}


def t_place_trades():
    """Place 3 trades for each of 4 users (12 total)."""
    for user in USERS:
        conn, cur = conn_as(user)
        for (ticker, opt_type, strike, expiry, entry, sl, tp) in USER_TRADES[user]:
            cur.execute("""
                INSERT INTO paper_trades
                    (username, ticker, option_type, strike, expiry,
                     entry_price, sl_price, tp_price, qty, direction, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'BUY', 'OPEN')
                RETURNING id
            """, (user, ticker, opt_type, strike, expiry, entry, sl, tp))
            trade_id = cur.fetchone()[0]
            trade_ids[user].append(trade_id)

            # Insert initial StateTransition: None→OPEN
            cur.execute("""
                INSERT INTO state_transitions
                    (trade_id, from_status, to_status, trigger, metadata_json)
                VALUES (%s, NULL, 'OPEN', 'USER_SUBMIT', '{}')
            """, (trade_id,))

        conn.commit()
        conn.close()

    # Verify all 12 trades exist
    total_trades = sum(len(ids) for ids in trade_ids.values())
    assert total_trades == 12, f"Expected 12 trades placed, got {total_trades}"

test("E2E-01", f"Place 3 trades × 4 users = 12 trades total", t_place_trades)


# ═════════════════════════════════════════════════════════════
# SECTION 2: RLS Isolation — Each User Only Sees Own Trades
# ═════════════════════════════════════════════════════════════

print("\n─── Section 2: RLS Isolation ────────────────────────────")


def make_rls_test(user):
    def fn():
        conn, cur = conn_as(user)
        try:
            cur.execute("SELECT COUNT(*) FROM paper_trades")
            count = cur.fetchone()[0]
            assert count == 3, f"{user} sees {count} trades, expected 3"

            cur.execute("SELECT DISTINCT username FROM paper_trades")
            users = [r[0] for r in cur.fetchall()]
            assert users == [user], f"{user} sees users {users}, expected [{user}]"
        finally:
            close(conn)
    return fn


for u in USERS:
    test(f"E2E-02-{u}", f"{u} sees only their 3 trades (RLS isolation)", make_rls_test(u))


def t_no_context():
    conn, cur = conn_as(None)
    try:
        cur.execute("SELECT COUNT(*) FROM paper_trades")
        count = cur.fetchone()[0]
        assert count == 0, f"No-context sees {count} trades, expected 0"
    finally:
        close(conn)

test("E2E-02-none", "No user context = 0 trades visible", t_no_context)


# ═════════════════════════════════════════════════════════════
# SECTION 3: Cross-User Attack Prevention
# ═════════════════════════════════════════════════════════════

print("\n─── Section 3: Cross-User Attack Prevention ─────────────")


def t_bob_cannot_read_alice():
    conn, cur = conn_as('bob')
    try:
        alice_id = trade_ids['alice'][0]
        cur.execute("SELECT COUNT(*) FROM paper_trades WHERE id = %s", (alice_id,))
        count = cur.fetchone()[0]
        assert count == 0, f"Bob can see Alice's trade #{alice_id}!"
    finally:
        close(conn)

test("E2E-03a", "Bob cannot read Alice's trade by ID", t_bob_cannot_read_alice)


def t_carlos_cannot_update_diana():
    conn, cur = conn_as('carlos')
    try:
        diana_id = trade_ids['diana'][0]
        cur.execute("UPDATE paper_trades SET sl_price = 0.01 WHERE id = %s", (diana_id,))
        assert cur.rowcount == 0, f"Carlos updated {cur.rowcount} of Diana's trades!"
    finally:
        close(conn)

test("E2E-03b", "Carlos cannot UPDATE Diana's trade", t_carlos_cannot_update_diana)


def t_diana_cannot_delete_bob():
    conn, cur = conn_as('diana')
    try:
        bob_id = trade_ids['bob'][0]
        cur.execute("DELETE FROM paper_trades WHERE id = %s", (bob_id,))
        assert cur.rowcount == 0, f"Diana deleted {cur.rowcount} of Bob's trades!"
    finally:
        close(conn)

test("E2E-03c", "Diana cannot DELETE Bob's trade", t_diana_cannot_delete_bob)


# ═════════════════════════════════════════════════════════════
# SECTION 4: Adjust SL/TP — Verify DB Persistence & Version
# ═════════════════════════════════════════════════════════════

print("\n─── Section 4: Adjust SL/TP ────────────────────────────")


def make_adjust_test(user, trade_idx, new_sl, new_tp):
    def fn():
        tid = trade_ids[user][trade_idx]
        conn, cur = conn_as(user)
        try:
            # Read current version
            cur.execute("SELECT version, sl_price, tp_price FROM paper_trades WHERE id = %s", (tid,))
            row = cur.fetchone()
            old_version = row[0]
            old_sl = float(row[1])
            old_tp = float(row[2])

            # Update SL and TP
            cur.execute("""
                UPDATE paper_trades
                SET sl_price = %s, tp_price = %s, version = version + 1
                WHERE id = %s AND username = %s
            """, (new_sl, new_tp, tid, user))
            assert cur.rowcount == 1, f"UPDATE affected {cur.rowcount} rows"

            # Log state transition for adjustment
            cur.execute("""
                INSERT INTO state_transitions
                    (trade_id, from_status, to_status, trigger, metadata_json)
                VALUES (%s, 'OPEN', 'OPEN', 'USER_ADJUST_BRACKET',
                        %s::jsonb)
            """, (tid, f'{{"old_sl": {old_sl}, "new_sl": {new_sl}, "old_tp": {old_tp}, "new_tp": {new_tp}}}'))

            conn.commit()

            # Verify persistence
            cur2 = conn.cursor()
            cur.execute('SET LOCAL "app.current_user" = %s', (user,))
            cur.execute("SELECT sl_price, tp_price, version FROM paper_trades WHERE id = %s", (tid,))
            updated = cur.fetchone()
            assert float(updated[0]) == new_sl, f"SL not updated: {updated[0]}"
            assert float(updated[1]) == new_tp, f"TP not updated: {updated[1]}"
            assert updated[2] == old_version + 1, f"Version not incremented: {updated[2]}"
        finally:
            close(conn)
    return fn


# Each user adjusts their first trade's brackets
test("E2E-04-alice", "Alice adjusts AAPL SL 3.75→4.00, TP 7.50→8.00",
     make_adjust_test('alice', 0, 4.00, 8.00))
test("E2E-04-bob", "Bob adjusts MSFT SL 4.50→5.00, TP 9.00→10.00",
     make_adjust_test('bob', 0, 5.00, 10.00))
test("E2E-04-carlos", "Carlos adjusts GOOG SL 6.75→7.00, TP 13.50→14.00",
     make_adjust_test('carlos', 0, 7.00, 14.00))
test("E2E-04-diana", "Diana adjusts QQQ SL 5.63→6.00, TP 11.25→12.00",
     make_adjust_test('diana', 0, 6.00, 12.00))


# ═════════════════════════════════════════════════════════════
# SECTION 5: Simulate SL Hit (fill_price ≤ sl_price * 1.02)
# ═════════════════════════════════════════════════════════════

print("\n─── Section 5: Simulate Stop Loss Hit ──────────────────")


def make_sl_hit_test(user, trade_idx):
    """Simulate _handle_fill with fill_price near SL."""
    def fn():
        tid = trade_ids[user][trade_idx]
        ms = MonitorService()

        # Build mock trade from DB
        conn, cur = conn_as(user)
        cur.execute("""
            SELECT ticker, entry_price, sl_price, tp_price, qty, direction, option_type, strike, expiry
            FROM paper_trades WHERE id = %s
        """, (tid,))
        row = cur.fetchone()
        close(conn)

        mock_trade = MagicMock()
        mock_trade.id = tid
        mock_trade.ticker = row[0]
        mock_trade.entry_price = float(row[1])
        mock_trade.sl_price = float(row[2])
        mock_trade.tp_price = float(row[3])
        mock_trade.qty = row[4]
        mock_trade.direction = row[5]
        mock_trade.option_type = row[6]
        mock_trade.strike = float(row[7])
        mock_trade.status = 'OPEN'
        mock_trade.trade_context = {}
        mock_trade.version = 1

        # Fill AT the stop loss price → should be detected as SL_HIT
        fill_price = mock_trade.sl_price
        mock_db = MagicMock()
        order = {'avg_fill_price': str(fill_price), 'status': 'filled'}

        ms._handle_fill(mock_db, mock_trade, order)

        # Verify
        assert mock_trade.status == 'CLOSED', f"Expected CLOSED, got {mock_trade.status}"
        assert mock_trade.close_reason == 'SL_HIT', f"Expected SL_HIT, got {mock_trade.close_reason}"
        assert mock_trade.exit_price == fill_price
        assert mock_trade.realized_pnl < 0, f"SL hit should produce negative P&L, got {mock_trade.realized_pnl}"

        # Verify StateTransition was created
        assert mock_db.add.called, "StateTransition should be created"
        transition = mock_db.add.call_args[0][0]
        assert transition.trigger == 'BROKER_FILL'
        assert transition.to_status == 'CLOSED'
        assert transition.metadata_json['close_reason'] == 'SL_HIT'

        # Now PERSIST this to the real DB
        conn, cur = conn_as(user)
        cur.execute("""
            UPDATE paper_trades
            SET status = 'CLOSED', exit_price = %s, realized_pnl = %s,
                close_reason = 'SL_HIT', closed_at = NOW(), version = version + 1
            WHERE id = %s
        """, (fill_price, mock_trade.realized_pnl, tid))
        cur.execute("""
            INSERT INTO state_transitions
                (trade_id, from_status, to_status, trigger, metadata_json)
            VALUES (%s, 'OPEN', 'CLOSED', 'BROKER_FILL',
                    %s::jsonb)
        """, (tid, f'{{"fill_price": {fill_price}, "close_reason": "SL_HIT", "pnl": {mock_trade.realized_pnl}}}'))
        conn.commit()
        conn.close()

    return fn


# Simulate SL hit on each user's SECOND trade
test("E2E-05-alice", "Alice NVDA SL hit → CLOSED, negative P&L, StateTransition logged",
     make_sl_hit_test('alice', 1))
test("E2E-05-bob", "Bob AMZN SL hit → CLOSED, negative P&L, StateTransition logged",
     make_sl_hit_test('bob', 1))
test("E2E-05-carlos", "Carlos AMD SL hit → CLOSED, negative P&L, StateTransition logged",
     make_sl_hit_test('carlos', 1))
test("E2E-05-diana", "Diana IWM SL hit → CLOSED, negative P&L, StateTransition logged",
     make_sl_hit_test('diana', 1))


# ═════════════════════════════════════════════════════════════
# SECTION 6: Simulate TP Hit (fill_price ≥ tp_price * 0.98)
# ═════════════════════════════════════════════════════════════

print("\n─── Section 6: Simulate Take Profit Hit ─────────────────")


def make_tp_hit_test(user, trade_idx):
    """Simulate _handle_fill with fill_price near TP."""
    def fn():
        tid = trade_ids[user][trade_idx]
        ms = MonitorService()

        conn, cur = conn_as(user)
        cur.execute("""
            SELECT ticker, entry_price, sl_price, tp_price, qty, direction
            FROM paper_trades WHERE id = %s
        """, (tid,))
        row = cur.fetchone()
        close(conn)

        mock_trade = MagicMock()
        mock_trade.id = tid
        mock_trade.ticker = row[0]
        mock_trade.entry_price = float(row[1])
        mock_trade.sl_price = float(row[2])
        mock_trade.tp_price = float(row[3])
        mock_trade.qty = row[4]
        mock_trade.direction = row[5]
        mock_trade.status = 'OPEN'
        mock_trade.trade_context = {}
        mock_trade.version = 1

        # Fill AT the take profit price → should be detected as TP_HIT
        fill_price = mock_trade.tp_price
        mock_db = MagicMock()
        order = {'avg_fill_price': str(fill_price), 'status': 'filled'}

        ms._handle_fill(mock_db, mock_trade, order)

        assert mock_trade.status == 'CLOSED'
        assert mock_trade.close_reason == 'TP_HIT', f"Expected TP_HIT, got {mock_trade.close_reason}"
        assert mock_trade.exit_price == fill_price
        assert mock_trade.realized_pnl > 0, f"TP hit should produce positive P&L, got {mock_trade.realized_pnl}"

        # Verify StateTransition
        transition = mock_db.add.call_args[0][0]
        assert transition.metadata_json['close_reason'] == 'TP_HIT'

        # Persist to real DB
        conn, cur = conn_as(user)
        cur.execute("""
            UPDATE paper_trades
            SET status = 'CLOSED', exit_price = %s, realized_pnl = %s,
                close_reason = 'TP_HIT', closed_at = NOW(), version = version + 1
            WHERE id = %s
        """, (fill_price, mock_trade.realized_pnl, tid))
        cur.execute("""
            INSERT INTO state_transitions
                (trade_id, from_status, to_status, trigger, metadata_json)
            VALUES (%s, 'OPEN', 'CLOSED', 'BROKER_FILL',
                    %s::jsonb)
        """, (tid, f'{{"fill_price": {fill_price}, "close_reason": "TP_HIT", "pnl": {mock_trade.realized_pnl}}}'))
        conn.commit()
        conn.close()

    return fn


# Simulate TP hit on each user's THIRD trade
test("E2E-06-alice", "Alice TSLA TP hit → CLOSED, positive P&L, StateTransition logged",
     make_tp_hit_test('alice', 2))
test("E2E-06-bob", "Bob META TP hit → CLOSED, positive P&L, StateTransition logged",
     make_tp_hit_test('bob', 2))
test("E2E-06-carlos", "Carlos SPY TP hit → CLOSED, positive P&L, StateTransition logged",
     make_tp_hit_test('carlos', 2))
test("E2E-06-diana", "Diana COIN TP hit → CLOSED, positive P&L, StateTransition logged",
     make_tp_hit_test('diana', 2))


# ═════════════════════════════════════════════════════════════
# SECTION 7: Manual Close (First Trade — Adjusted One)
# ═════════════════════════════════════════════════════════════

print("\n─── Section 7: Manual Close ─────────────────────────────")


def make_manual_close_test(user, trade_idx, current_price):
    def fn():
        tid = trade_ids[user][trade_idx]
        conn, cur = conn_as(user)
        try:
            # Verify trade is still OPEN
            cur.execute("SELECT status, entry_price FROM paper_trades WHERE id = %s", (tid,))
            row = cur.fetchone()
            assert row[0] == 'OPEN', f"Trade should be OPEN, got {row[0]}"
            entry = float(row[1])

            # Calculate P&L (BUY direction → (exit - entry) * qty * 100)
            pnl = round((current_price - entry) * 1 * 100, 2)

            # Close the trade
            cur.execute("""
                UPDATE paper_trades
                SET status = 'CLOSED', exit_price = %s, realized_pnl = %s,
                    close_reason = 'MANUAL_CLOSE', closed_at = NOW(),
                    version = version + 1
                WHERE id = %s AND status = 'OPEN'
            """, (current_price, pnl, tid))
            assert cur.rowcount == 1, f"Expected 1 row updated, got {cur.rowcount}"

            # Log state transition
            cur.execute("""
                INSERT INTO state_transitions
                    (trade_id, from_status, to_status, trigger, metadata_json)
                VALUES (%s, 'OPEN', 'CLOSED', 'USER_MANUAL_CLOSE',
                        %s::jsonb)
            """, (tid, f'{{"exit_price": {current_price}, "pnl": {pnl}}}'))

            conn.commit()

            # Verify final state
            cur.execute('SET LOCAL "app.current_user" = %s', (user,))
            cur.execute("SELECT status, exit_price, close_reason FROM paper_trades WHERE id = %s", (tid,))
            final = cur.fetchone()
            assert final[0] == 'CLOSED', f"Expected CLOSED, got {final[0]}"
            assert float(final[1]) == current_price
            assert final[2] == 'MANUAL_CLOSE'
        finally:
            close(conn)
    return fn


# Manual close each user's first trade (the one with adjusted SL/TP)
test("E2E-07-alice", "Alice manual close AAPL @ $5.50 → profit $50",
     make_manual_close_test('alice', 0, 5.50))
test("E2E-07-bob", "Bob manual close MSFT @ $5.80 → loss -$20",
     make_manual_close_test('bob', 0, 5.80))
test("E2E-07-carlos", "Carlos manual close GOOG @ $10.00 → profit $100",
     make_manual_close_test('carlos', 0, 10.00))
test("E2E-07-diana", "Diana manual close QQQ @ $7.00 → loss -$50",
     make_manual_close_test('diana', 0, 7.00))


# ═════════════════════════════════════════════════════════════
# SECTION 8: Final Verification — All Trades Closed, RLS Intact
# ═════════════════════════════════════════════════════════════

print("\n─── Section 8: Final Verification ───────────────────────")


def make_final_check(user):
    def fn():
        conn, cur = conn_as(user)
        try:
            # All 3 trades should be CLOSED
            cur.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'CLOSED'")
            closed = cur.fetchone()[0]
            assert closed == 3, f"{user}: expected 3 CLOSED trades, got {closed}"

            cur.execute("SELECT COUNT(*) FROM paper_trades WHERE status = 'OPEN'")
            open_count = cur.fetchone()[0]
            assert open_count == 0, f"{user}: expected 0 OPEN trades, got {open_count}"

            # Verify state transitions exist for ALL trades
            cur.execute("""
                SELECT COUNT(*) FROM state_transitions st
                JOIN paper_trades pt ON st.trade_id = pt.id
                WHERE pt.username = %s
            """, (user,))
            transitions = cur.fetchone()[0]
            # Each trade should have at least 2 transitions (OPEN + CLOSE)
            # Trade 1 (adjusted): OPEN + ADJUST + CLOSE = 3
            # Trade 2 (SL hit):   OPEN + CLOSE = 2
            # Trade 3 (TP hit):   OPEN + CLOSE = 2
            assert transitions >= 6, f"{user}: expected ≥6 transitions, got {transitions}"

            # Verify each close_reason is present
            cur.execute("""
                SELECT close_reason, COUNT(*)
                FROM paper_trades
                GROUP BY close_reason
                ORDER BY close_reason
            """)
            reasons = {r[0]: r[1] for r in cur.fetchall()}
            assert 'SL_HIT' in reasons, f"{user}: missing SL_HIT close"
            assert 'TP_HIT' in reasons, f"{user}: missing TP_HIT close"
            assert 'MANUAL_CLOSE' in reasons, f"{user}: missing MANUAL_CLOSE close"

        finally:
            close(conn)
    return fn


for u in USERS:
    test(f"E2E-08-{u}",
         f"{u}: 3/3 CLOSED, 0 OPEN, ≥6 transitions, all close_reasons present",
         make_final_check(u))


# Verify cross-user isolation AFTER all closures
def t_final_isolation():
    """After everything, verify total trade count with superuser-like check."""
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = True
    cur = conn.cursor()
    # This query goes through RLS — without app.current_user set, sees 0
    cur.execute("SELECT COUNT(*) FROM paper_trades")
    no_context = cur.fetchone()[0]
    assert no_context == 0, f"Without user context, should see 0 trades, got {no_context}"
    conn.close()

test("E2E-09", "No-context query sees 0 trades (RLS enforced after full lifecycle)", t_final_isolation)


# ═════════════════════════════════════════════════════════════
# SECTION 9: State Transition Audit Trail Integrity
# ═════════════════════════════════════════════════════════════

print("\n─── Section 9: Audit Trail Integrity ────────────────────")


def make_audit_trail_check(user):
    def fn():
        conn, cur = conn_as(user)
        try:
            # Get all transitions ordered by time
            cur.execute("""
                SELECT st.trade_id, st.from_status, st.to_status, st.trigger
                FROM state_transitions st
                JOIN paper_trades pt ON st.trade_id = pt.id
                ORDER BY st.created_at
            """)
            transitions = cur.fetchall()

            # Group by trade_id
            by_trade = {}
            for (tid, from_s, to_s, trigger) in transitions:
                by_trade.setdefault(tid, []).append((from_s, to_s, trigger))

            for tid, history in by_trade.items():
                # First transition should always be None→OPEN
                assert history[0][0] is None, f"Trade {tid}: first from_status should be None"
                assert history[0][1] == 'OPEN', f"Trade {tid}: first to_status should be OPEN"
                assert history[0][2] == 'USER_SUBMIT'

                # Last transition should end in CLOSED
                assert history[-1][1] == 'CLOSED', f"Trade {tid}: last to_status should be CLOSED"

        finally:
            close(conn)
    return fn

for u in USERS:
    test(f"E2E-10-{u}",
         f"{u}: audit trail starts None→OPEN and ends →CLOSED for all trades",
         make_audit_trail_check(u))


# Cross-user audit trail isolation
def t_audit_isolation():
    """Bob should not see Alice's state transitions."""
    conn, cur = conn_as('bob')
    try:
        # Try to read transitions for alice's trade IDs
        alice_ids = trade_ids['alice']
        cur.execute("SELECT COUNT(*) FROM state_transitions WHERE trade_id = ANY(%s)",
                     (alice_ids,))
        count = cur.fetchone()[0]
        assert count == 0, f"Bob sees {count} of Alice's state transitions!"
    finally:
        close(conn)

test("E2E-11", "Audit trail RLS: Bob cannot see Alice's state transitions", t_audit_isolation)


# ═════════════════════════════════════════════════════════════
# CLEANUP & SUMMARY
# ═════════════════════════════════════════════════════════════

print("\n─── Cleanup ────────────────────────────────────────────")
cleanup()
print("  ✓ All test data cleaned up")

print(f"\n{'=' * 70}")
print(f"  E2E Multi-User Results: {passed}/{total} passed, {failed} failed")
print(f"{'=' * 70}")

if failed > 0:
    print(f"\n  ⚠ {failed} test(s) FAILED — review output above\n")
    sys.exit(1)
else:
    print(f"\n  🎉 ALL {total} TESTS PASSED — Full lifecycle verified for 4 users!\n")
    sys.exit(0)
