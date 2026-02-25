"""
Phase 3 Regression Tests: Monitor Service
==========================================
Tests T-MS-01 through T-MS-10

Mock-based tests — no database required.
Tests verify internal logic of MonitorService handlers.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
from unittest.mock import patch, MagicMock

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


print("\n" + "=" * 60)
print("Phase 3 Tests: Monitor Service")
print("=" * 60 + "\n")


# =========================================================================
# T-MS-01: MonitorService imports and initializes
# =========================================================================
def t_ms_01():
    from backend.services.monitor_service import MonitorService
    ms = MonitorService()
    assert ms.orats is not None, "orats should be initialized"

test("T-MS-01", "MonitorService imports and initializes", t_ms_01)


# =========================================================================
# T-MS-02: sync_tradier_orders (no open trades = no-op)
# =========================================================================
def t_ms_02():
    from backend.services.monitor_service import MonitorService
    ms = MonitorService()

    # Mock is_market_open to True, but with no trades in DB
    with patch('backend.services.monitor_service.is_market_open', return_value=True):
        with patch.object(ms, '_sync_user_orders') as mock_sync:
            # The method should complete without error
            ms.sync_tradier_orders()

test("T-MS-02", "sync_tradier_orders completes with no open trades", t_ms_02)


# =========================================================================
# T-MS-03: sync_tradier_orders skips when market is closed
# =========================================================================
def t_ms_03():
    from backend.services.monitor_service import MonitorService
    ms = MonitorService()

    with patch('backend.services.monitor_service.is_market_open', return_value=False):
        with patch('backend.services.monitor_service.get_paper_db') as mock_db:
            ms.sync_tradier_orders()
            mock_db.assert_not_called()

test("T-MS-03", "sync_tradier_orders skips when market is closed", t_ms_03)


# =========================================================================
# T-MS-04: update_price_snapshots skips when market is closed
# =========================================================================
def t_ms_04():
    from backend.services.monitor_service import MonitorService
    ms = MonitorService()

    with patch('backend.services.monitor_service.is_market_open', return_value=False):
        with patch('backend.services.monitor_service.get_paper_db') as mock_db:
            ms.update_price_snapshots()
            mock_db.assert_not_called()

test("T-MS-04", "update_price_snapshots skips when market is closed", t_ms_04)


# =========================================================================
# T-MS-05: _handle_fill sets CLOSED status and calculates P&L
# =========================================================================
def t_ms_05():
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    mock_trade = MagicMock()
    mock_trade.entry_price = 5.00
    mock_trade.qty = 1
    mock_trade.direction = 'BUY'
    mock_trade.sl_price = 4.00
    mock_trade.tp_price = 7.00
    mock_trade.id = 1
    mock_trade.ticker = 'NVDA'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    order = {'avg_fill_price': '7.50', 'status': 'filled'}

    ms._handle_fill(MagicMock(), mock_trade, order)

    assert mock_trade.status == 'CLOSED', f"Expected CLOSED, got {mock_trade.status}"
    assert mock_trade.exit_price == 7.50
    assert mock_trade.realized_pnl == 250.0, f"Expected $250 P&L, got {mock_trade.realized_pnl}"
    assert mock_trade.close_reason == 'TP_HIT'
    assert mock_trade.version == 2

test("T-MS-05", "_handle_fill sets CLOSED, calculates P&L, tags TP_HIT", t_ms_05)


# =========================================================================
# T-MS-06: _handle_fill detects SL_HIT close reason
# =========================================================================
def t_ms_06():
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    mock_trade = MagicMock()
    mock_trade.entry_price = 5.00
    mock_trade.qty = 1
    mock_trade.direction = 'BUY'
    mock_trade.sl_price = 3.50
    mock_trade.tp_price = 7.50
    mock_trade.id = 2
    mock_trade.ticker = 'AAPL'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    order = {'avg_fill_price': '3.45', 'status': 'filled'}

    ms._handle_fill(MagicMock(), mock_trade, order)

    assert mock_trade.close_reason == 'SL_HIT', f"Expected SL_HIT, got {mock_trade.close_reason}"
    assert mock_trade.realized_pnl == -155.0, f"Expected -155.0, got {mock_trade.realized_pnl}"

test("T-MS-06", "_handle_fill detects SL_HIT when fill_price <= sl_price*1.02", t_ms_06)


# =========================================================================
# T-MS-07: _handle_expiration sets EXPIRED with full loss
# =========================================================================
def t_ms_07():
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    mock_trade = MagicMock()
    mock_trade.entry_price = 4.00
    mock_trade.qty = 2
    mock_trade.id = 3
    mock_trade.ticker = 'GOOG'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    ms._handle_expiration(MagicMock(), mock_trade)

    assert mock_trade.status == 'EXPIRED', f"Expected EXPIRED, got {mock_trade.status}"
    assert mock_trade.exit_price == 0.0
    assert mock_trade.realized_pnl == -800.0, f"Expected -800, got {mock_trade.realized_pnl}"
    assert mock_trade.close_reason == 'EXPIRED'

test("T-MS-07", "_handle_expiration sets EXPIRED, exit=0, full loss P&L", t_ms_07)


# =========================================================================
# T-MS-08: _handle_cancellation sets CANCELED status
# =========================================================================
def t_ms_08():
    from backend.services.monitor_service import MonitorService

    ms = MonitorService()

    mock_trade = MagicMock()
    mock_trade.id = 4
    mock_trade.ticker = 'TSLA'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    ms._handle_cancellation(MagicMock(), mock_trade, 'rejected')

    assert mock_trade.status == 'CANCELED', f"Expected CANCELED, got {mock_trade.status}"
    assert mock_trade.close_reason == 'REJECTED'

test("T-MS-08", "_handle_cancellation sets CANCELED with uppercased reason", t_ms_08)


# =========================================================================
# T-MS-09: _build_occ_symbol generates correct format
# =========================================================================
def t_ms_09():
    from backend.services.monitor_service import MonitorService

    mock_trade = MagicMock()
    mock_trade.ticker = 'AAPL'
    mock_trade.expiry = '2026-03-20'
    mock_trade.option_type = 'CALL'
    mock_trade.strike = 150.0

    result = MonitorService._build_occ_symbol(mock_trade)

    # AAPL260320C00150000
    assert result == 'AAPL260320C00150000', f"Expected AAPL260320C00150000, got {result}"

test("T-MS-09", "_build_occ_symbol: AAPL 150C 03/20/26 → AAPL260320C00150000", t_ms_09)


# =========================================================================
# T-MS-10: _build_occ_symbol handles PUT and fractional strikes
# =========================================================================
def t_ms_10():
    from backend.services.monitor_service import MonitorService

    mock_trade = MagicMock()
    mock_trade.ticker = 'SPY'
    mock_trade.expiry = '2026-12-18'
    mock_trade.option_type = 'PUT'
    mock_trade.strike = 450.5

    result = MonitorService._build_occ_symbol(mock_trade)

    # SPY261218P00450500
    assert result == 'SPY261218P00450500', f"Expected SPY261218P00450500, got {result}"

test("T-MS-10", "_build_occ_symbol: SPY 450.5P 12/18/26 → SPY261218P00450500", t_ms_10)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*60}")
print(f"Monitor Service Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*60}")

sys.exit(0 if failed == 0 else 1)
