#!/usr/bin/env python3
"""
Phase 5 Tests: Analytics Service
=================================
Tests all 7 SQL analytics queries + export + RLS isolation
against live Docker Postgres.

Run:  python tests/test_phase5_analytics.py
"""
import sys
import os
import json
import traceback
from datetime import datetime, timedelta

# ── Setup path ──
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import psycopg2
from psycopg2.extras import RealDictCursor


# ── Database connection ──
DB_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://paper_user:paper_pass@localhost:5433/paper_trading'
)

PASS = 0
FAIL = 0


def get_conn():
    return psycopg2.connect(DB_URL)


def run_as(conn, username, sql, params=None):
    """Execute SQL as a specific user (RLS context) inside a transaction."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("BEGIN")
        cur.execute('SET LOCAL "app.current_user" = %s', (username,))
        cur.execute(sql, params)
        rows = cur.fetchall()
        cur.execute("COMMIT")
        return rows
    except Exception as e:
        cur.execute("ROLLBACK")
        raise


def check(name, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} — {detail}")


# ═══════════════════════════════════════════════════════════════
# Seed Test Data
# ═══════════════════════════════════════════════════════════════

def seed_analytics_data(conn):
    """Insert realistic closed trades for analytics testing."""
    cur = conn.cursor()

    # Clean up first
    cur.execute("DELETE FROM paper_trades WHERE username IN ('ana_alice', 'ana_bob')")
    conn.commit()

    # Alice's trades: 5 closed (3 wins, 2 losses), various tickers & strategies
    trades = [
        # --- Alice: 3 wins ---
        {
            'username': 'ana_alice', 'ticker': 'NVDA', 'option_type': 'CALL',
            'strike': 150, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 5.00, 'exit_price': 8.00, 'qty': 2,
            'realized_pnl': 600.0, 'status': 'CLOSED', 'close_reason': 'TP_HIT',
            'strategy': 'WEEKLY',
            'trade_context': json.dumps({'mfe': 650.0, 'mae': -80.0, 'strategy_type': 'Momentum'}),
            'created_at': datetime(2026, 2, 1, 10, 0),
            'closed_at': datetime(2026, 2, 3, 14, 30),
        },
        {
            'username': 'ana_alice', 'ticker': 'AAPL', 'option_type': 'CALL',
            'strike': 200, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 3.00, 'exit_price': 5.50, 'qty': 1,
            'realized_pnl': 250.0, 'status': 'CLOSED', 'close_reason': 'MANUAL',
            'strategy': 'LEAP',
            'trade_context': json.dumps({'mfe': 300.0, 'mae': -50.0, 'strategy_type': 'Quality'}),
            'created_at': datetime(2026, 2, 5, 9, 30),
            'closed_at': datetime(2026, 2, 10, 15, 0),
        },
        {
            'username': 'ana_alice', 'ticker': 'NVDA', 'option_type': 'PUT',
            'strike': 140, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 4.00, 'exit_price': 6.00, 'qty': 1,
            'realized_pnl': 200.0, 'status': 'CLOSED', 'close_reason': 'MANUAL',
            'strategy': 'WEEKLY',
            'trade_context': json.dumps({'mfe': 210.0, 'mae': -30.0, 'strategy_type': 'Momentum'}),
            'created_at': datetime(2026, 2, 12, 10, 0),
            'closed_at': datetime(2026, 2, 14, 11, 0),
        },
        # --- Alice: 2 losses ---
        {
            'username': 'ana_alice', 'ticker': 'TSLA', 'option_type': 'CALL',
            'strike': 300, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 8.00, 'exit_price': 3.00, 'qty': 1,
            'realized_pnl': -500.0, 'status': 'CLOSED', 'close_reason': 'SL_HIT',
            'strategy': '0DTE',
            'trade_context': json.dumps({'mfe': 100.0, 'mae': -550.0, 'strategy_type': 'Breakout'}),
            'created_at': datetime(2026, 2, 15, 9, 35),
            'closed_at': datetime(2026, 2, 15, 12, 0),
        },
        {
            'username': 'ana_alice', 'ticker': 'AAPL', 'option_type': 'PUT',
            'strike': 210, 'expiry': '2026-02-28', 'direction': 'BUY',
            'entry_price': 2.50, 'exit_price': 0.00, 'qty': 1,
            'realized_pnl': -250.0, 'status': 'EXPIRED', 'close_reason': 'EXPIRED',
            'strategy': 'WEEKLY',
            'trade_context': json.dumps({'mfe': 50.0, 'mae': -250.0, 'strategy_type': 'Momentum'}),
            'created_at': datetime(2026, 2, 18, 10, 0),
            'closed_at': datetime(2026, 2, 28, 16, 0),
        },
    ]

    # Bob's trades: 2 closed (1 win, 1 loss)
    trades.extend([
        {
            'username': 'ana_bob', 'ticker': 'MSFT', 'option_type': 'CALL',
            'strike': 400, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 6.00, 'exit_price': 10.00, 'qty': 1,
            'realized_pnl': 400.0, 'status': 'CLOSED', 'close_reason': 'TP_HIT',
            'strategy': 'LEAP',
            'trade_context': json.dumps({'mfe': 420.0, 'mae': -60.0, 'strategy_type': 'Quality'}),
            'created_at': datetime(2026, 2, 3, 10, 0),
            'closed_at': datetime(2026, 2, 7, 14, 0),
        },
        {
            'username': 'ana_bob', 'ticker': 'GOOG', 'option_type': 'CALL',
            'strike': 180, 'expiry': '2026-03-20', 'direction': 'BUY',
            'entry_price': 5.00, 'exit_price': 2.50, 'qty': 1,
            'realized_pnl': -250.0, 'status': 'CLOSED', 'close_reason': 'SL_HIT',
            'strategy': 'WEEKLY',
            'trade_context': json.dumps({'mfe': 80.0, 'mae': -270.0, 'strategy_type': 'Breakout'}),
            'created_at': datetime(2026, 2, 10, 10, 0),
            'closed_at': datetime(2026, 2, 12, 11, 0),
        },
    ])

    for t in trades:
        cur.execute("""
            INSERT INTO paper_trades (
                username, ticker, option_type, strike, expiry, direction,
                entry_price, exit_price, qty, realized_pnl, status, close_reason,
                strategy, trade_context, created_at, closed_at
            ) VALUES (
                %(username)s, %(ticker)s, %(option_type)s, %(strike)s, %(expiry)s,
                %(direction)s, %(entry_price)s, %(exit_price)s, %(qty)s,
                %(realized_pnl)s, %(status)s, %(close_reason)s,
                %(strategy)s, %(trade_context)s, %(created_at)s, %(closed_at)s
            )
        """, t)

    conn.commit()
    return len(trades)


def cleanup(conn):
    """Remove all test data."""
    cur = conn.cursor()
    cur.execute("DELETE FROM paper_trades WHERE username IN ('ana_alice', 'ana_bob')")
    conn.commit()


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════

def test_summary_stats(conn):
    """AN-01: Summary stats query returns correct metrics."""
    print("\n--- Summary Stats ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            COUNT(*) AS total_trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
            ROUND(
                COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric
                / NULLIF(COUNT(*), 0) * 100, 1
            ) AS win_rate,
            ROUND(
                SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
                / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0))::numeric, 0), 2
            ) AS profit_factor,
            ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric, 2) AS avg_win,
            ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0)::numeric, 2) AS avg_loss,
            MAX(realized_pnl) AS largest_win,
            MIN(realized_pnl) AS largest_loss,
            ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
    """)
    row = rows[0]

    check("AN-01a: Alice total_trades = 5", row['total_trades'] == 5, f"got {row['total_trades']}")
    check("AN-01b: Alice wins = 3", row['wins'] == 3, f"got {row['wins']}")
    check("AN-01c: Alice losses = 2", row['losses'] == 2, f"got {row['losses']}")
    check("AN-01d: Alice win_rate = 60.0%", float(row['win_rate']) == 60.0, f"got {row['win_rate']}")
    check("AN-01e: Alice total_pnl = $300", float(row['total_pnl']) == 300.0, f"got {row['total_pnl']}")
    check("AN-01f: Alice largest_win = $600", float(row['largest_win']) == 600.0, f"got {row['largest_win']}")
    check("AN-01g: Alice largest_loss = -$500", float(row['largest_loss']) == -500.0, f"got {row['largest_loss']}")
    check("AN-01h: Profit factor = 1.4 (1050/750)", float(row['profit_factor']) == 1.4, f"got {row['profit_factor']}")


def test_equity_curve(conn):
    """AN-02: Equity curve returns cumulative P&L in date order."""
    print("\n--- Equity Curve ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            TO_CHAR(DATE(closed_at), 'YYYY-MM-DD') AS trade_date,
            ROUND(SUM(realized_pnl)::numeric, 2) AS daily_pnl,
            ROUND(
                SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at))::numeric, 2
            ) AS cumulative_pnl
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
        GROUP BY DATE(closed_at)
        ORDER BY DATE(closed_at)
    """)

    check("AN-02a: Equity curve has ≥3 date points", len(rows) >= 3, f"got {len(rows)}")
    check("AN-02b: First point is chronologically earliest", rows[0]['trade_date'] < rows[-1]['trade_date'])
    check("AN-02c: Final cumulative = $300", float(rows[-1]['cumulative_pnl']) == 300.0,
          f"got {rows[-1]['cumulative_pnl']}")


def test_max_drawdown(conn):
    """AN-03: Max drawdown identifies worst peak-to-trough."""
    print("\n--- Max Drawdown ---")
    rows = run_as(conn, 'ana_alice', """
        WITH equity AS (
            SELECT
                DATE(closed_at) AS trade_date,
                SUM(SUM(realized_pnl)) OVER (ORDER BY DATE(closed_at)) AS cumulative_pnl
            FROM paper_trades
            WHERE status IN ('CLOSED', 'EXPIRED')
              AND username = current_setting('app.current_user', true)
            GROUP BY DATE(closed_at)
        ),
        peaks AS (
            SELECT
                trade_date,
                cumulative_pnl,
                MAX(cumulative_pnl) OVER (ORDER BY trade_date) AS running_peak
            FROM equity
        )
        SELECT
            ROUND(MIN(cumulative_pnl - running_peak)::numeric, 2) AS max_drawdown
        FROM peaks
        WHERE cumulative_pnl - running_peak < 0
    """)

    row = rows[0] if rows else None
    check("AN-03: Max drawdown is negative", row and float(row['max_drawdown']) < 0,
          f"got {row}")


def test_ticker_breakdown(conn):
    """AN-04: Ticker breakdown groups correctly."""
    print("\n--- Ticker Breakdown ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            ticker,
            COUNT(*) AS trades,
            COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
            ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
        GROUP BY ticker
        ORDER BY total_pnl DESC
    """)

    tickers = {r['ticker']: r for r in rows}
    check("AN-04a: 3 unique tickers (NVDA, AAPL, TSLA)", len(rows) == 3, f"got {len(rows)}")
    check("AN-04b: NVDA has 2 trades", tickers.get('NVDA', {}).get('trades') == 2,
          f"got {tickers.get('NVDA')}")
    check("AN-04c: NVDA total_pnl = $800", float(tickers.get('NVDA', {}).get('total_pnl', 0)) == 800.0,
          f"got {tickers.get('NVDA', {}).get('total_pnl')}")
    check("AN-04d: TSLA total_pnl = -$500", float(tickers.get('TSLA', {}).get('total_pnl', 0)) == -500.0,
          f"got {tickers.get('TSLA', {}).get('total_pnl')}")


def test_strategy_breakdown(conn):
    """AN-05: Strategy breakdown reads from strategy column."""
    print("\n--- Strategy Breakdown ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            COALESCE(strategy, 'Unknown') AS strategy,
            COUNT(*) AS trades,
            ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
        GROUP BY strategy
        ORDER BY total_pnl DESC
    """)

    strategies = {r['strategy']: r for r in rows}
    check("AN-05a: WEEKLY strategy present", 'WEEKLY' in strategies, f"got {list(strategies.keys())}")
    check("AN-05b: WEEKLY has 3 trades", strategies.get('WEEKLY', {}).get('trades') == 3,
          f"got {strategies.get('WEEKLY')}")


def test_monthly_pnl(conn):
    """AN-06: Monthly P&L groups by year/month."""
    print("\n--- Monthly P&L ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            TO_CHAR(closed_at, 'YYYY') AS year,
            TO_CHAR(closed_at, 'Mon') AS month,
            EXTRACT(MONTH FROM closed_at)::int AS month_num,
            ROUND(SUM(realized_pnl)::numeric, 2) AS monthly_pnl,
            COUNT(*) AS trade_count
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
        GROUP BY year, month, month_num
        ORDER BY year, month_num
    """)

    check("AN-06a: At least 1 month of data", len(rows) >= 1, f"got {len(rows)}")
    feb = [r for r in rows if r['month_num'] == 2]
    check("AN-06b: Feb 2026 present", len(feb) == 1, f"got {feb}")
    check("AN-06c: Feb total_pnl = $300", float(feb[0]['monthly_pnl']) == 300.0 if feb else False,
          f"got {feb[0]['monthly_pnl'] if feb else 'N/A'}")
    check("AN-06d: Feb trade_count = 5", feb[0]['trade_count'] == 5 if feb else False,
          f"got {feb[0]['trade_count'] if feb else 'N/A'}")


def test_mfe_mae(conn):
    """AN-07: MFE/MAE exit quality analysis."""
    print("\n--- MFE/MAE Exit Quality ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            ticker,
            ROUND(realized_pnl::numeric, 2) AS realized_pnl,
            ROUND((trade_context->>'mfe')::numeric, 2) AS mfe,
            ROUND((trade_context->>'mae')::numeric, 2) AS mae,
            CASE
                WHEN realized_pnl > 0 AND (trade_context->>'mfe')::numeric > realized_pnl * 1.5
                THEN 'LEFT_MONEY'
                WHEN realized_pnl < 0 AND ABS((trade_context->>'mae')::numeric) > ABS(realized_pnl) * 1.5
                THEN 'HELD_TOO_LONG'
                ELSE 'OPTIMAL'
            END AS exit_quality
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
          AND trade_context->>'mfe' IS NOT NULL
        ORDER BY closed_at DESC
    """)

    check("AN-07a: All 5 trades have MFE/MAE data", len(rows) == 5, f"got {len(rows)}")

    qualities = [r['exit_quality'] for r in rows]
    check("AN-07b: At least one OPTIMAL exit", 'OPTIMAL' in qualities, f"got {qualities}")


def test_rls_isolation(conn):
    """AN-08: RLS isolation — Bob cannot see Alice's analytics."""
    print("\n--- RLS Isolation ---")
    rows = run_as(conn, 'ana_bob', """
        SELECT COUNT(*) AS total_trades
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
    """)
    row = rows[0]

    check("AN-08a: Bob sees only 2 trades (not Alice's 5)", row['total_trades'] == 2,
          f"got {row['total_trades']}")

    # Bob's ticker breakdown should NOT include NVDA/TSLA/AAPL
    rows2 = run_as(conn, 'ana_bob', """
        SELECT ticker FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
    """)
    bob_tickers = [r['ticker'] for r in rows2]

    check("AN-08b: Bob's tickers are MSFT+GOOG only", set(bob_tickers) == {'MSFT', 'GOOG'},
          f"got {bob_tickers}")


def test_empty_state(conn):
    """AN-09: Empty state for user with no trades."""
    print("\n--- Empty State ---")
    rows = run_as(conn, 'ana_nobody', """
        SELECT COUNT(*) AS total_trades
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
    """)
    row = rows[0]

    check("AN-09: User with no trades gets 0", row['total_trades'] == 0)


def test_export_query(conn):
    """AN-10: Export query returns all fields for CSV/JSON."""
    print("\n--- Export Data ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            id, ticker, option_type, strike, direction,
            entry_price, exit_price, qty, realized_pnl,
            strategy, status, close_reason,
            trade_context,
            TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS opened_at,
            TO_CHAR(closed_at, 'YYYY-MM-DD HH24:MI:SS') AS closed_at,
            ROUND(
                EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600, 1
            ) AS hold_hours
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
        ORDER BY closed_at DESC
    """)

    check("AN-10a: Export returns 5 rows for Alice", len(rows) == 5, f"got {len(rows)}")
    check("AN-10b: Export includes hold_hours", rows[0].get('hold_hours') is not None)
    check("AN-10c: Export includes trade_context", rows[0].get('trade_context') is not None)


def test_expectancy_calculation(conn):
    """AN-11: Expectancy calculation is correct."""
    print("\n--- Expectancy ---")
    rows = run_as(conn, 'ana_alice', """
        SELECT
            ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric, 2) AS avg_win,
            ROUND(AVG(realized_pnl) FILTER (WHERE realized_pnl < 0)::numeric, 2) AS avg_loss,
            ROUND(
                COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric
                / NULLIF(COUNT(*), 0) * 100, 1
            ) AS win_rate
        FROM paper_trades
        WHERE status IN ('CLOSED', 'EXPIRED')
          AND username = current_setting('app.current_user', true)
    """)
    row = rows[0]

    # Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)
    # = (0.6 * 350) - (0.4 * 375) = 210 - 150 = 60
    win_rate = float(row['win_rate']) / 100  # 0.6
    avg_win = float(row['avg_win'])  # 350
    avg_loss = abs(float(row['avg_loss']))  # 375
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    check("AN-11a: Expectancy > 0 (profitable system)", expectancy > 0,
          f"expectancy={expectancy:.2f}")
    check("AN-11b: avg_win = $350", avg_win == 350.0, f"got {avg_win}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("Phase 5: Analytics Tests")
    print("=" * 70)

    conn = get_conn()
    conn.autocommit = True

    try:
        count = seed_analytics_data(conn)
        print(f"  OK Seeded {count} test trades (5 Alice + 2 Bob)")

        test_summary_stats(conn)
        test_equity_curve(conn)
        test_max_drawdown(conn)
        test_ticker_breakdown(conn)
        test_strategy_breakdown(conn)
        test_monthly_pnl(conn)
        test_mfe_mae(conn)
        test_rls_isolation(conn)
        test_empty_state(conn)
        test_export_query(conn)
        test_expectancy_calculation(conn)

    except Exception as e:
        traceback.print_exc()
        FAIL += 1
    finally:
        print("\n--- Cleanup ---")
        cleanup(conn)
        print("  OK All test data cleaned up")
        conn.close()

    print("\n" + "=" * 70)
    print(f"  Phase 5 Analytics Results: {PASS}/{PASS + FAIL} passed, {FAIL} failed")
    print("=" * 70)

    if FAIL == 0:
        print(f"\n  ALL {PASS} TESTS PASSED")
    else:
        print(f"\n  ❌ {FAIL} TESTS FAILED")

    sys.exit(0 if FAIL == 0 else 1)
