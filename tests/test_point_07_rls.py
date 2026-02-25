"""
Regression Tests for Point 7: Multi-User Data Isolation (RLS)
=============================================================
Tests T-07-01 through T-07-10 from regression_testing_plan.md

Uses raw DBAPI connections to ensure SET LOCAL stays within
the same transaction and connection — required for Postgres RLS.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psycopg2

DB_PARAMS = dict(
    host='localhost', port=5433,
    dbname='paper_trading', user='app_user', password='app_pass'
)

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


def conn_as(username=None):
    """Create a raw psycopg2 connection with RLS user context."""
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()
    if username:
        cur.execute(f'SET LOCAL "app.current_user" = %s', (username,))
    return conn, cur


def close(conn):
    """Rollback and close a connection."""
    try:
        conn.rollback()
    except Exception:
        pass
    conn.close()


# =========================================================================
# SETUP: Seed alice (5 trades) + bob (5 trades)
# =========================================================================
def seed():
    """Seed test data using per-user connections."""
    # Alice's trades
    conn, cur = conn_as('alice')
    for i in range(5):
        cur.execute(
            "INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, status) "
            "VALUES (%s, %s, 'CALL', %s, '2026-06-20', %s, 'OPEN')",
            ('alice', f'ALICE{i}', 100 + i, 5.0 + i)
        )
    conn.commit()
    conn.close()

    # Bob's trades
    conn, cur = conn_as('bob')
    for i in range(5):
        cur.execute(
            "INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price, status) "
            "VALUES (%s, %s, 'CALL', %s, '2026-06-20', %s, 'OPEN')",
            ('bob', f'BOB{i}', 200 + i, 8.0 + i)
        )
    conn.commit()
    conn.close()


def teardown():
    """Clean up all test data."""
    conn, cur = conn_as('alice')
    cur.execute("DELETE FROM paper_trades WHERE username = 'alice'")
    conn.commit()
    conn.close()

    conn, cur = conn_as('bob')
    cur.execute("DELETE FROM paper_trades WHERE username = 'bob'")
    conn.commit()
    conn.close()


print("Setting up test data (alice: 5 trades, bob: 5 trades)...")
seed()


# =========================================================================
# T-07-01: Alice can only see Alice's 5 trades
# =========================================================================
def t_07_01():
    conn, cur = conn_as('alice')
    try:
        cur.execute("SELECT COUNT(*) FROM paper_trades")
        count = cur.fetchone()[0]
        assert count == 5, f"Alice should see 5 trades, got {count}"

        cur.execute("SELECT DISTINCT username FROM paper_trades")
        users = [r[0] for r in cur.fetchall()]
        assert users == ['alice'], f"Alice should only see 'alice', got {users}"
    finally:
        close(conn)

test("T-07-01", "Alice can only see Alice's 5 trades", t_07_01)


# =========================================================================
# T-07-02: Bob cannot see Alice's trades
# =========================================================================
def t_07_02():
    conn, cur = conn_as('bob')
    try:
        cur.execute("SELECT COUNT(*) FROM paper_trades")
        count = cur.fetchone()[0]
        assert count == 5, f"Bob should see 5 trades, got {count}"

        cur.execute("SELECT COUNT(*) FROM paper_trades WHERE ticker LIKE 'ALICE%'")
        alice_count = cur.fetchone()[0]
        assert alice_count == 0, f"Bob can see {alice_count} of Alice's trades!"
    finally:
        close(conn)

test("T-07-02", "Bob cannot see Alice's trades", t_07_02)


# =========================================================================
# T-07-03: RLS enforced on INSERT (Bob can't insert as Alice)
# =========================================================================
def t_07_03():
    conn, cur = conn_as('bob')
    try:
        raised = False
        try:
            cur.execute(
                "INSERT INTO paper_trades (username, ticker, option_type, strike, expiry, entry_price) "
                "VALUES ('alice', 'HACK1', 'CALL', 999.0, '2026-06-20', 1.00)"
            )
            conn.commit()
        except psycopg2.errors.InsufficientPrivilege:
            raised = True
            conn.rollback()
        except psycopg2.Error as e:
            if 'policy' in str(e).lower() or 'row-level' in str(e).lower():
                raised = True
                conn.rollback()
            else:
                raise
        assert raised, "INSERT as alice by bob should have been rejected by RLS WITH CHECK"
    finally:
        close(conn)

test("T-07-03", "RLS enforced on INSERT: Bob can't insert as Alice", t_07_03)


# =========================================================================
# T-07-04: RLS enforced on UPDATE (Bob can't update Alice's trade)
# =========================================================================
def t_07_04():
    conn, cur = conn_as('bob')
    try:
        cur.execute("UPDATE paper_trades SET entry_price = 999.99 WHERE username = 'alice'")
        assert cur.rowcount == 0, f"Bob updated {cur.rowcount} of Alice's trades!"
    finally:
        close(conn)

test("T-07-04", "RLS enforced on UPDATE: Bob can't update Alice's trade", t_07_04)


# =========================================================================
# T-07-05: RLS enforced on DELETE (Bob can't delete Alice's trade)
# =========================================================================
def t_07_05():
    conn, cur = conn_as('bob')
    try:
        cur.execute("DELETE FROM paper_trades WHERE username = 'alice'")
        assert cur.rowcount == 0, f"Bob deleted {cur.rowcount} of Alice's trades!"
    finally:
        close(conn)

test("T-07-05", "RLS enforced on DELETE: Bob can't delete Alice's trade", t_07_05)


# =========================================================================
# T-07-06: Verify alice's data survived bob's attack
# =========================================================================
def t_07_06():
    conn, cur = conn_as('alice')
    try:
        cur.execute("SELECT COUNT(*) FROM paper_trades")
        count = cur.fetchone()[0]
        assert count == 5, f"Alice should still have 5 trades after Bob's attacks, got {count}"
    finally:
        close(conn)

test("T-07-06", "Alice's data survived Bob's UPDATE/DELETE attempts", t_07_06)


# =========================================================================
# T-07-07: No app.current_user set = no access
# =========================================================================
def t_07_07():
    conn, cur = conn_as(None)  # No user context
    try:
        cur.execute("SELECT COUNT(*) FROM paper_trades")
        count = cur.fetchone()[0]
        assert count == 0, f"Without session user, should see 0 trades, got {count}"
    finally:
        close(conn)

test("T-07-07", "No app.current_user set = 0 trades visible", t_07_07)


# =========================================================================
# T-07-08: RLS on state_transitions (cross-table isolation)
# =========================================================================
def t_07_08():
    # Insert a transition for one of alice's trades
    conn, cur = conn_as('alice')
    cur.execute("SELECT id FROM paper_trades LIMIT 1")
    trade_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO state_transitions (trade_id, from_status, to_status, trigger) "
        "VALUES (%s, NULL, 'PENDING', 'user_submit')", (trade_id,)
    )
    conn.commit()
    conn.close()

    # Bob should NOT see alice's transitions
    conn, cur = conn_as('bob')
    try:
        cur.execute("SELECT COUNT(*) FROM state_transitions")
        count = cur.fetchone()[0]
        assert count == 0, f"Bob should see 0 of Alice's transitions, got {count}"
    finally:
        close(conn)

    # Clean up as alice
    conn, cur = conn_as('alice')
    cur.execute("DELETE FROM state_transitions")
    conn.commit()
    conn.close()

test("T-07-08", "RLS on state_transitions: Bob can't see Alice's transitions", t_07_08)


# =========================================================================
# T-07-09: FORCE ROW LEVEL SECURITY is enabled on all 4 tables
# =========================================================================
def t_07_09():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute("""
        SELECT relname, relrowsecurity, relforcerowsecurity
        FROM pg_class
        WHERE relname IN ('paper_trades', 'state_transitions', 'price_snapshots', 'user_settings')
        ORDER BY relname
    """)
    rows = cur.fetchall()
    conn.close()

    assert len(rows) == 4, f"Expected 4 tables, got {len(rows)}"
    for name, rls, force_rls in rows:
        assert rls is True, f"{name}: relrowsecurity should be True"
        assert force_rls is True, f"{name}: relforcerowsecurity should be True"

test("T-07-09", "FORCE ROW LEVEL SECURITY enabled on all 4 tables", t_07_09)


# =========================================================================
# T-07-10: RLS policies exist on all 4 tables
# =========================================================================
def t_07_10():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM pg_policies
        WHERE tablename IN ('paper_trades', 'state_transitions', 'price_snapshots', 'user_settings')
    """)
    count = cur.fetchone()[0]
    conn.close()
    assert count == 4, f"Expected 4 RLS policies, got {count}"

test("T-07-10", "RLS policies exist on all 4 tables", t_07_10)


# =========================================================================
# TEARDOWN
# =========================================================================
print("\nCleaning up test data...")
teardown()


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*50}")
print(f"Point 7 Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)
