"""
Portfolio Risk Manager — G17/G18 Remediation
Enforces position limits and sector concentration rules.

G17: Max positions per ticker, total positions, portfolio exposure
G18: Sector concentration limits, single-ticker exposure cap
"""

import logging
from backend.config import Config

logger = logging.getLogger(__name__)


class PortfolioRiskManager:
    """
    Pre-trade risk checks for portfolio-level constraints.

    F17 NOTE: Checks are currently advisory only — not enforced in the
    trade execution path. Future: integrate as a hard gate in
    paper_routes.py before order submission.

    Usage:
        prm = PortfolioRiskManager()
        check = prm.check_trade(
            ticker='AAPL',
            sector='Technology',
            trade_cost=500,
            account_size=50000,
            current_positions=[...],  # list of dicts with ticker, sector, cost
        )
        # check = {
        #   'allowed': True/False,
        #   'violations': [...],
        #   'warnings': [...],
        #   'limits': {...},
        # }
    """

    def __init__(self):
        self.max_per_ticker = Config.MAX_POSITIONS_PER_TICKER
        self.max_total = Config.MAX_TOTAL_POSITIONS
        self.max_exposure_pct = Config.MAX_PORTFOLIO_EXPOSURE_PCT
        self.max_sector_pct = Config.MAX_SECTOR_CONCENTRATION_PCT
        self.max_single_ticker_pct = Config.MAX_SINGLE_TICKER_PCT

    def check_trade(self, ticker, sector, trade_cost, account_size,
                    current_positions=None):
        """
        Run pre-trade risk checks.

        Args:
            ticker: Symbol to trade
            sector: Sector of the ticker
            trade_cost: Cost of the new trade in dollars
            account_size: Total account value
            current_positions: List of dicts [{'ticker': str, 'sector': str, 'cost': float}]

        Returns:
            dict with 'allowed', 'violations', 'warnings', 'limits'
        """
        current_positions = current_positions or []
        violations = []
        warnings = []

        # G17: Position count per ticker
        ticker_count = sum(1 for p in current_positions if p.get('ticker') == ticker)
        if ticker_count >= self.max_per_ticker:
            violations.append(
                f"G17: Max {self.max_per_ticker} positions per ticker ({ticker} has {ticker_count})")

        # G17: Total position count
        total_count = len(current_positions)
        if total_count >= self.max_total:
            violations.append(
                f"G17: Max {self.max_total} total positions (currently {total_count})")

        # G17: Total portfolio exposure
        total_exposure = sum(p.get('cost', 0) for p in current_positions) + trade_cost
        exposure_pct = (total_exposure / account_size) * 100 if account_size > 0 else 0
        if exposure_pct > self.max_exposure_pct:
            violations.append(
                f"G17: Total exposure {exposure_pct:.1f}% exceeds {self.max_exposure_pct}% limit")

        # G18: Sector concentration
        if sector:
            sector_exposure = sum(
                p.get('cost', 0) for p in current_positions if p.get('sector') == sector
            ) + trade_cost
            sector_pct = (sector_exposure / account_size) * 100 if account_size > 0 else 0
            if sector_pct > self.max_sector_pct:
                violations.append(
                    f"G18: {sector} sector at {sector_pct:.1f}% exceeds {self.max_sector_pct}% limit")
            elif sector_pct > self.max_sector_pct * 0.8:
                warnings.append(
                    f"G18: {sector} sector at {sector_pct:.1f}% — approaching {self.max_sector_pct}% limit")

        # G18: Single ticker concentration
        ticker_exposure = sum(
            p.get('cost', 0) for p in current_positions if p.get('ticker') == ticker
        ) + trade_cost
        ticker_pct = (ticker_exposure / account_size) * 100 if account_size > 0 else 0
        if ticker_pct > self.max_single_ticker_pct:
            violations.append(
                f"G18: {ticker} at {ticker_pct:.1f}% exceeds {self.max_single_ticker_pct}% limit")

        return {
            'allowed': len(violations) == 0,
            'violations': violations,
            'warnings': warnings,
            'limits': {
                'max_per_ticker': self.max_per_ticker,
                'max_total_positions': self.max_total,
                'max_exposure_pct': self.max_exposure_pct,
                'max_sector_pct': self.max_sector_pct,
                'max_single_ticker_pct': self.max_single_ticker_pct,
            },
            'current_state': {
                'ticker_positions': ticker_count,
                'total_positions': total_count,
                'total_exposure_pct': round(exposure_pct, 2),
                'ticker_exposure_pct': round(ticker_pct, 2),
            }
        }

    # GAP-1 FIX: Portfolio-level max drawdown circuit breaker
    def check_drawdown(self, current_portfolio_value, peak_portfolio_value,
                       block_threshold_pct=15.0, close_threshold_pct=25.0):
        """
        Check if portfolio drawdown has breached circuit breaker levels.

        Args:
            current_portfolio_value: Current total portfolio value
            peak_portfolio_value: Highest portfolio value recorded (high-water mark)
            block_threshold_pct: Drawdown % that blocks new trades (default 15%)
            close_threshold_pct: Drawdown % that triggers auto-close all (default 25%)

        Returns:
            dict with 'status', 'drawdown_pct', 'action', 'message'
            status: 'ok' | 'block_new_trades' | 'close_all_positions'
        """
        if peak_portfolio_value <= 0:
            return {
                'status': 'ok',
                'drawdown_pct': 0,
                'action': 'none',
                'message': 'No peak value recorded yet',
            }

        drawdown_pct = ((peak_portfolio_value - current_portfolio_value) / peak_portfolio_value) * 100
        drawdown_pct = max(0, drawdown_pct)  # Can't have negative drawdown

        if drawdown_pct >= close_threshold_pct:
            logger.critical(
                f"CIRCUIT BREAKER: Drawdown {drawdown_pct:.1f}% >= {close_threshold_pct}% "
                f"(peak=${peak_portfolio_value:.2f}, current=${current_portfolio_value:.2f}). "
                f"ACTION: CLOSE ALL POSITIONS"
            )
            return {
                'status': 'close_all_positions',
                'drawdown_pct': round(drawdown_pct, 2),
                'action': 'close_all',
                'message': f'Drawdown {drawdown_pct:.1f}% exceeds {close_threshold_pct}% limit. All positions should be closed.',
            }
        elif drawdown_pct >= block_threshold_pct:
            logger.warning(
                f"CIRCUIT BREAKER: Drawdown {drawdown_pct:.1f}% >= {block_threshold_pct}% "
                f"(peak=${peak_portfolio_value:.2f}, current=${current_portfolio_value:.2f}). "
                f"ACTION: BLOCK NEW TRADES"
            )
            return {
                'status': 'block_new_trades',
                'drawdown_pct': round(drawdown_pct, 2),
                'action': 'block',
                'message': f'Drawdown {drawdown_pct:.1f}% exceeds {block_threshold_pct}% limit. New trades blocked.',
            }
        else:
            return {
                'status': 'ok',
                'drawdown_pct': round(drawdown_pct, 2),
                'action': 'none',
                'message': f'Drawdown {drawdown_pct:.1f}% within limits.',
            }
