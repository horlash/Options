"""
Analytics SQL Queries
=====================
Phase 5: Intelligence — Raw Postgres queries for performance analytics.

All queries are RLS-aware via current_setting('app.current_user').
Uses Postgres FILTER clauses for efficient aggregation.
"""

# ---------------------------------------------------------------------------
# 1. Summary Stats (Single Query — 10 Metrics)
# ---------------------------------------------------------------------------
SUMMARY_STATS_QUERY = """
SELECT
    COUNT(*) AS total_trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    COUNT(*) FILTER (WHERE realized_pnl < 0) AS losses,
    COUNT(*) FILTER (WHERE realized_pnl = 0) AS breakeven,

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

    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,

    ROUND(
        AVG(EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600)::numeric, 1
    ) AS avg_hold_hours
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
"""

# ---------------------------------------------------------------------------
# 2. Equity Curve (Cumulative P&L Over Time)
# ---------------------------------------------------------------------------
EQUITY_CURVE_QUERY = """
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
"""

# ---------------------------------------------------------------------------
# 3. Max Drawdown Calculation (Peak-to-Trough via Window Functions)
# ---------------------------------------------------------------------------
MAX_DRAWDOWN_QUERY = """
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
    ROUND(MIN(cumulative_pnl - running_peak)::numeric, 2) AS max_drawdown,
    (ARRAY_AGG(trade_date ORDER BY (cumulative_pnl - running_peak) ASC))[1] AS drawdown_date
FROM peaks
WHERE cumulative_pnl - running_peak < 0
"""

# ---------------------------------------------------------------------------
# 4. Per-Ticker Breakdown
# ---------------------------------------------------------------------------
TICKER_BREAKDOWN_QUERY = """
SELECT
    ticker,
    COUNT(*) AS trades,
    COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
GROUP BY ticker
ORDER BY total_pnl DESC
"""

# ---------------------------------------------------------------------------
# 5. Per-Strategy Breakdown (via trade_context JSONB)
# ---------------------------------------------------------------------------
STRATEGY_BREAKDOWN_QUERY = """
SELECT
    COALESCE(strategy, 'Unknown') AS strategy,
    COUNT(*) AS trades,
    ROUND(
        COUNT(*) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1
    ) AS win_rate,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(
        SUM(realized_pnl) FILTER (WHERE realized_pnl > 0)::numeric
        / NULLIF(ABS(SUM(realized_pnl) FILTER (WHERE realized_pnl < 0))::numeric, 0), 2
    ) AS profit_factor
FROM paper_trades
WHERE status IN ('CLOSED', 'EXPIRED')
  AND username = current_setting('app.current_user', true)
GROUP BY strategy
ORDER BY total_pnl DESC
"""

# ---------------------------------------------------------------------------
# 6. Monthly P&L Aggregation
# ---------------------------------------------------------------------------
MONTHLY_PNL_QUERY = """
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
"""

# ---------------------------------------------------------------------------
# 7. MFE/MAE Exit Quality Analysis (via trade_context JSONB)
# ---------------------------------------------------------------------------
MFE_MAE_QUERY = """
SELECT
    ticker,
    ROUND(realized_pnl::numeric, 2) AS realized_pnl,
    ROUND((trade_context->>'mfe')::numeric, 2) AS max_favorable_excursion,
    ROUND((trade_context->>'mae')::numeric, 2) AS max_adverse_excursion,
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
  AND trade_context->>'mae' IS NOT NULL
ORDER BY closed_at DESC
"""
