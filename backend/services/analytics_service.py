"""
Analytics Service
=================
Phase 5: Intelligence — Business logic for portfolio analytics.

Executes raw SQL queries from backend.queries.analytics and returns
JSON-serializable results. All queries are RLS-scoped by the session
user set via get_paper_db_with_user().
"""
import logging
from datetime import datetime
from sqlalchemy import text

from backend.queries.analytics import (
    SUMMARY_STATS_QUERY,
    EQUITY_CURVE_QUERY,
    MAX_DRAWDOWN_QUERY,
    TICKER_BREAKDOWN_QUERY,
    STRATEGY_BREAKDOWN_QUERY,
    MONTHLY_PNL_QUERY,
    MFE_MAE_QUERY,
)

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Portfolio analytics powered by raw Postgres SQL."""

    def __init__(self, db_session):
        self.db = db_session

    @staticmethod
    def _apply_date_filter(query, start_date=None, end_date=None):
        """Append optional date range filter to an analytics query.

        Args:
            query: SQL query string (must already have WHERE clause)
            start_date: Optional YYYY-MM-DD string for lower bound
            end_date: Optional YYYY-MM-DD string for upper bound

        Returns:
            (query_string, params_dict) tuple for use with text().
        """
        params = {}
        if start_date:
            query += "\n  AND closed_at >= :start_date"
            params['start_date'] = start_date
        if end_date:
            query += "\n  AND closed_at <= :end_date"
            params['end_date'] = end_date
        return query, params

    def get_summary(self, start_date=None, end_date=None) -> dict:
        """Get all summary stats + computed expectancy.

        Returns 12 metrics: total_trades, wins, losses, breakeven,
        win_rate, profit_factor, avg_win, avg_loss, largest_win,
        largest_loss, total_pnl, avg_hold_hours, expectancy.
        """
        try:
            query, params = self._apply_date_filter(
                SUMMARY_STATS_QUERY, start_date, end_date
            )
            result = self.db.execute(text(query), params).mappings().first()

            if not result or result['total_trades'] == 0:
                return self._empty_summary()

            row = dict(result)

            # Compute Expectancy: (win_rate% * avg_win) - (loss_rate% * avg_loss)
            win_rate = float(row.get('win_rate') or 0) / 100
            avg_win = float(row.get('avg_win') or 0)
            avg_loss = abs(float(row.get('avg_loss') or 0))
            expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

            # Convert Decimal types to float for JSON serialization
            for key in row:
                if row[key] is not None and hasattr(row[key], '__float__'):
                    row[key] = float(row[key])

            row['expectancy'] = round(expectancy, 2)
            return row

        except Exception as e:
            logger.exception(f"get_summary failed: {e}")
            return self._empty_summary()

    def get_equity_curve(self, start_date=None, end_date=None) -> list:
        """Get cumulative P&L data points for Chart.js line chart.

        Returns: [{trade_date, daily_pnl, cumulative_pnl}, ...]
        """
        try:
            query, params = self._apply_date_filter(
                EQUITY_CURVE_QUERY, start_date, end_date
            )
            rows = self.db.execute(text(query), params).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_equity_curve failed: {e}")
            return []

    def get_max_drawdown(self, start_date=None, end_date=None) -> dict:
        """Get worst peak-to-trough decline.

        Returns: {max_drawdown: float, drawdown_date: str}
        """
        try:
            query, params = self._apply_date_filter(
                MAX_DRAWDOWN_QUERY, start_date, end_date
            )
            result = self.db.execute(text(query), params).mappings().first()
            if result and result['max_drawdown'] is not None:
                return {
                    'max_drawdown': float(result['max_drawdown']),
                    'drawdown_date': str(result['drawdown_date']) if result['drawdown_date'] else None,
                }
            return {'max_drawdown': 0, 'drawdown_date': None}
        except Exception as e:
            logger.exception(f"get_max_drawdown failed: {e}")
            return {'max_drawdown': 0, 'drawdown_date': None}

    def get_ticker_breakdown(self, start_date=None, end_date=None) -> list:
        """Get per-ticker performance breakdown.

        Returns: [{ticker, trades, wins, win_rate, total_pnl, avg_pnl}, ...]
        """
        try:
            query, params = self._apply_date_filter(
                TICKER_BREAKDOWN_QUERY, start_date, end_date
            )
            rows = self.db.execute(text(query), params).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_ticker_breakdown failed: {e}")
            return []

    def get_strategy_breakdown(self, start_date=None, end_date=None) -> list:
        """Get per-strategy performance breakdown.

        Returns: [{strategy, trades, win_rate, total_pnl, profit_factor}, ...]
        """
        try:
            query, params = self._apply_date_filter(
                STRATEGY_BREAKDOWN_QUERY, start_date, end_date
            )
            rows = self.db.execute(text(query), params).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_strategy_breakdown failed: {e}")
            return []

    def get_monthly_pnl(self, start_date=None, end_date=None) -> list:
        """Get monthly P&L aggregation for bar chart.

        Returns: [{year, month, month_num, monthly_pnl, trade_count}, ...]
        """
        try:
            query, params = self._apply_date_filter(
                MONTHLY_PNL_QUERY, start_date, end_date
            )
            rows = self.db.execute(text(query), params).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_monthly_pnl failed: {e}")
            return []

    def get_mfe_mae_analysis(self, start_date=None, end_date=None) -> list:
        """Get exit quality analysis using MFE/MAE from trade_context JSONB.

        Returns: [{ticker, realized_pnl, max_favorable_excursion,
                   max_adverse_excursion, exit_quality}, ...]
        Exit quality labels: OPTIMAL | LEFT_MONEY | HELD_TOO_LONG
        """
        try:
            query, params = self._apply_date_filter(
                MFE_MAE_QUERY, start_date, end_date
            )
            rows = self.db.execute(text(query), params).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_mfe_mae_analysis failed: {e}")
            return []

    # --- CSV/JSON Export Helpers ---

    def get_export_data(self) -> list:
        """Get all closed trades for CSV/JSON export.

        Returns list of dicts with trade details + context.
        """
        try:
            query = text("""
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
            rows = self.db.execute(query).mappings().all()
            return [self._row_to_dict(r) for r in rows]
        except Exception as e:
            logger.exception(f"get_export_data failed: {e}")
            return []

    # --- Private Helpers ---

    @staticmethod
    def _row_to_dict(row) -> dict:
        """Convert a SQLAlchemy RowMapping to a JSON-safe dict."""
        d = dict(row)
        for key, val in d.items():
            if val is not None and hasattr(val, '__float__') and not isinstance(val, (int, float, str, bool)):
                d[key] = float(val)
            elif isinstance(val, datetime):
                d[key] = val.isoformat()
        return d

    @staticmethod
    def _empty_summary() -> dict:
        """Return zeroed-out summary for users with no closed trades."""
        return {
            'total_trades': 0, 'wins': 0, 'losses': 0, 'breakeven': 0,
            'win_rate': 0.0, 'profit_factor': 0.0, 'expectancy': 0.0,
            'avg_win': 0.0, 'avg_loss': 0.0,
            'largest_win': 0.0, 'largest_loss': 0.0,
            'total_pnl': 0.0, 'avg_hold_hours': 0.0,
        }
