"""
Tests for Point 6: Backtesting Context Service
================================================
Tests the ContextService which captures rich trading context
at entry/exit for backtesting and ML labeling.

Run: pytest tests/test_point_06_context.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from backend.services.context_service import ContextService


# ═══════════════════════════════════════════════════════════════
# Group A: Entry Context Capture (4 tests)
# ═══════════════════════════════════════════════════════════════

class TestEntryContextCapture:
    """Verify entry context collection with various input combinations."""

    def test_entry_context_basic_structure(self):
        """A1: Entry context has all required top-level keys."""
        svc = ContextService()
        ctx = svc.capture_entry_context(
            ticker='NVDA', option_type='CALL', strike=150.0,
            expiry='2026-03-27', entry_price=4.50
        )
        assert 'captured_at' in ctx
        assert ctx['capture_type'] == 'ENTRY'
        assert 'signals_snapshot' in ctx
        assert 'market_regime' in ctx
        assert 'order_book_state' in ctx

    def test_entry_context_with_scanner_result(self):
        """A2: Scanner result technicals flow into signals_snapshot."""
        svc = ContextService()
        scanner_result = {
            'technicals': {
                'rsi': 65.2,
                'macd_signal': 'bullish',
                'ma_signal': 'bullish',
                'score': 72,
                'volume_zscore': 1.5,
            },
            'sentiment': {
                'score': 68,
                'headline_count': 5,
            },
            'ai_analysis': {
                'score': 75,
                'verdict': 'PROCEED',
                'conviction': 'HIGH',
                'summary': 'Strong momentum with bullish technicals.',
                'factors': ['RSI above 60', 'MACD bullish crossover'],
            },
        }
        ctx = svc.capture_entry_context(
            ticker='NVDA', option_type='CALL', strike=150.0,
            expiry='2026-03-27', entry_price=4.50,
            scanner_result=scanner_result,
        )
        assert ctx['signals_snapshot']['daily']['rsi'] == 65.2
        assert ctx['signals_snapshot']['daily']['score'] == 72
        assert ctx['signals_snapshot']['sentiment']['score'] == 68
        assert ctx['ai_reasoning_log']['score'] == 75
        assert ctx['ai_reasoning_log']['verdict'] == 'PROCEED'

    def test_entry_context_with_orats(self):
        """A3: ORATS API provides market regime data."""
        mock_orats = MagicMock()
        mock_orats.get_quote.side_effect = lambda t: {
            'SPY': {'price': 502.5, 'pctChange': -0.45, 'volume': 50000000},
            'VIX': {'price': 18.2, 'pctChange': 2.1},
            'XLK': {'price': 220.0, 'pctChange': -1.2},
        }.get(t)
        mock_orats.get_option_chain.return_value = None

        svc = ContextService(orats_api=mock_orats)
        ctx = svc.capture_entry_context(
            ticker='NVDA', option_type='CALL', strike=150.0,
            expiry='2026-03-27', entry_price=4.50,
        )
        assert ctx['market_regime']['spy']['price'] == 502.5
        assert ctx['market_regime']['vix']['price'] == 18.2
        assert ctx['market_regime']['sector']['etf'] == 'XLK'

    def test_entry_context_without_orats(self):
        """A4: Graceful degradation when ORATS is unavailable."""
        svc = ContextService(orats_api=None)
        ctx = svc.capture_entry_context(
            ticker='NVDA', option_type='CALL', strike=150.0,
            expiry='2026-03-27', entry_price=4.50,
        )
        # Should still return valid context with empty market_regime
        assert ctx['market_regime'] == {}
        assert ctx['order_book_state']['entry_price'] == 4.50


# ═══════════════════════════════════════════════════════════════
# Group B: Exit Context Capture (2 tests)
# ═══════════════════════════════════════════════════════════════

class TestExitContextCapture:
    """Verify exit context collection and merging."""

    def _make_trade(self, **kwargs):
        """Helper to create a mock trade object."""
        trade = MagicMock()
        trade.ticker = kwargs.get('ticker', 'NVDA')
        trade.created_at = kwargs.get('created_at', datetime.utcnow() - timedelta(hours=5))
        trade.trade_context = kwargs.get('trade_context', {'capture_type': 'ENTRY'})
        return trade

    def test_exit_context_merges_with_entry(self):
        """B1: Exit context merges into existing entry context."""
        svc = ContextService()
        trade = self._make_trade(trade_context={
            'capture_type': 'ENTRY',
            'signals_snapshot': {'daily': {'rsi': 65}},
        })
        result = svc.capture_exit_context(trade, close_price=6.50, close_reason='TP_HIT')
        # Entry data preserved
        assert result['capture_type'] == 'ENTRY'
        assert result['signals_snapshot']['daily']['rsi'] == 65
        # Exit data added
        assert result['exit_context']['close_price'] == 6.50
        assert result['exit_context']['close_reason'] == 'TP_HIT'
        assert result['exit_context']['duration_hours'] is not None

    def test_exit_context_calculates_duration(self):
        """B2: Exit context correctly calculates trade duration."""
        svc = ContextService()
        trade = self._make_trade(
            created_at=datetime.utcnow() - timedelta(hours=3, minutes=30)
        )
        result = svc.capture_exit_context(trade, close_price=3.00, close_reason='SL_HIT')
        duration = result['exit_context']['duration_hours']
        assert 3.4 <= duration <= 3.6  # ~3.5 hours


# ═══════════════════════════════════════════════════════════════
# Group C: ML Target Calculation (3 tests)
# ═══════════════════════════════════════════════════════════════

class TestMLTargetCalculation:
    """Verify MFE/MAE/PnL target calculations for ML labeling."""

    def _make_trade(self, **kwargs):
        trade = MagicMock()
        trade.id = kwargs.get('id', 1)
        trade.entry_price = kwargs.get('entry_price', 4.00)
        trade.exit_price = kwargs.get('exit_price', 5.00)
        trade.direction = kwargs.get('direction', 'BUY')
        return trade

    def _make_snapshots(self, prices):
        """Create mock PriceSnapshot objects from a list of prices."""
        snaps = []
        for p in prices:
            s = MagicMock()
            s.mark_price = p
            snaps.append(s)
        return snaps

    def test_mfe_mae_buy_trade(self):
        """C1: MFE/MAE calculated correctly for a BUY trade."""
        svc = ContextService()
        trade = self._make_trade(entry_price=4.00, exit_price=5.00, direction='BUY')
        # Prices: dip to 3.60, then rally to 5.50, close at 5.00
        prices = [4.00, 3.80, 3.60, 4.20, 4.80, 5.20, 5.50, 5.30, 5.10, 5.00,
                  4.90, 4.95, 5.00]
        snaps = self._make_snapshots(prices)

        targets = svc.calculate_targets(trade, snaps)
        # MFE = (5.50 - 4.00) / 4.00 * 100 = 37.5%
        assert targets['target_mfe_pct'] == 37.5
        # MAE = (4.00 - 3.60) / 4.00 * 100 = 10.0%
        assert targets['target_mae_pct'] == 10.0
        # Realized = (5.00 - 4.00) / 4.00 * 100 = 25.0%
        assert targets['target_realized_pnl_pct'] == 25.0

    def test_pnl_time_intervals(self):
        """C2: P&L at 15m/30m/1h intervals captured (5min snapshots)."""
        svc = ContextService()
        trade = self._make_trade(entry_price=4.00, exit_price=5.00)
        # Index 3 = 15m, 6 = 30m, 12 = 1h (5-min intervals)
        prices = [4.00, 4.05, 4.10, 4.20, 4.15, 4.30, 4.50,
                  4.45, 4.60, 4.70, 4.80, 4.90, 5.00, 5.10]
        snaps = self._make_snapshots(prices)

        targets = svc.calculate_targets(trade, snaps)
        # 15m (index 3): (4.20 - 4.00) / 4.00 * 100 = 5.0%
        assert targets['target_pnl_15m'] == 5.0
        # 30m (index 6): (4.50 - 4.00) / 4.00 * 100 = 12.5%
        assert targets['target_pnl_30m'] == 12.5
        # 1h (index 12): (5.00 - 4.00) / 4.00 * 100 = 25.0%
        assert targets['target_pnl_1h'] == 25.0

    def test_empty_snapshots_returns_empty(self):
        """C3: No crash when price_snapshots is empty."""
        svc = ContextService()
        trade = self._make_trade()
        assert svc.calculate_targets(trade, []) == {}
        assert svc.calculate_targets(trade, None) == {}


# ═══════════════════════════════════════════════════════════════
# Group D: Sector ETF Mapping (2 tests)
# ═══════════════════════════════════════════════════════════════

class TestSectorMapping:
    """Verify ticker-to-sector-ETF mapping."""

    def test_known_tech_tickers(self):
        """D1: Tech tickers map to XLK."""
        svc = ContextService()
        assert svc._find_sector_etf('NVDA') == 'XLK'
        assert svc._find_sector_etf('AAPL') == 'XLK'
        assert svc._find_sector_etf('AMD') == 'XLK'

    def test_unknown_ticker_returns_none(self):
        """D2: Unknown tickers return None gracefully."""
        svc = ContextService()
        assert svc._find_sector_etf('ZZZZZ') is None
        assert svc._find_sector_etf('BITCOIN') is None


# ═══════════════════════════════════════════════════════════════
# Group E: Spread Calculation (1 test)
# ═══════════════════════════════════════════════════════════════

class TestSpreadCalculation:
    """Verify bid-ask spread percentage calculation."""

    def test_spread_pct_calculation(self):
        """E1: Spread percentage is correct."""
        # Bid=4.50, Ask=4.60 → Mid=4.55 → Spread=0.10/4.55*100 ≈ 2.20%
        result = ContextService._calc_spread_pct(4.50, 4.60)
        assert result == 2.20

        # Edge: zero bid
        assert ContextService._calc_spread_pct(0, 4.60) is None
        assert ContextService._calc_spread_pct(None, None) is None
"""
Total: 12 tests across 5 groups (A-E)
Run: pytest tests/test_point_06_context.py -v
"""
