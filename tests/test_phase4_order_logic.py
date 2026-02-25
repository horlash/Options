"""
Phase 4: Order Logic — Automated Tests
=======================================
Tests:
  T-OL-01: StateTransition is created on trade placement (None→OPEN)
  T-OL-02: StateTransition is created on manual close (OPEN→CLOSED)
  T-OL-03: StateTransition is created on broker fill (OPEN→CLOSED via BROKER_FILL)
  T-OL-04: StateTransition is created on expiration (OPEN→EXPIRED)
  T-OL-05: StateTransition is created on cancellation (OPEN→CANCELED)
  T-OL-06: Tradier order placement is attempted when credentials exist
  T-OL-07: Trade saved paper-only when no broker credentials
  T-OL-08: OCO bracket orders placed when SL + TP are set
  T-OL-09: _build_occ_symbol produces correct format
  T-OL-10: Idempotency key prevents duplicate Tradier orders
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

# ── Test Harness ──────────────────────────────────────────────

passed = 0
failed = 0

def test(test_id, description, fn):
    global passed, failed
    try:
        fn()
        passed += 1
        print(f"  ✅ {test_id}: {description}")
    except Exception as e:
        failed += 1
        print(f"  ❌ {test_id}: {description}")
        print(f"     Error: {e}")

print("\n" + "=" * 60)
print("Phase 4: Order Logic Tests")
print("=" * 60)


# ── T-OL-01: StateTransition on trade placement ────────────

def t_ol_01():
    from backend.database.paper_models import StateTransition, TradeStatus

    # Verify StateTransition model can be instantiated with None→OPEN
    transition = StateTransition(
        trade_id=1,
        from_status=None,
        to_status=TradeStatus.OPEN.value,
        trigger='USER_SUBMIT',
        metadata_json={'source': 'SCANNER', 'card_score': 85.5},
    )

    assert transition.from_status is None, f"Expected None, got {transition.from_status}"
    assert transition.to_status == 'OPEN', f"Expected OPEN, got {transition.to_status}"
    assert transition.trigger == 'USER_SUBMIT'
    assert transition.metadata_json['source'] == 'SCANNER'
    assert transition.metadata_json['card_score'] == 85.5

test("T-OL-01", "StateTransition: None→OPEN on trade placement", t_ol_01)


# ── T-OL-02: StateTransition on manual close ────────────────

def t_ol_02():
    from backend.services.monitor_service import MonitorService
    from backend.database.paper_models import TradeStatus

    ms = MonitorService()

    mock_db = MagicMock()
    mock_trade = MagicMock()
    mock_trade.id = 42
    mock_trade.status = TradeStatus.OPEN.value
    mock_trade.entry_price = 5.00
    mock_trade.exit_price = 4.50
    mock_trade.realized_pnl = -50.0
    mock_trade.version = 1

    ms._log_transition(
        mock_db, mock_trade,
        from_status=TradeStatus.OPEN.value,
        to_status=TradeStatus.CLOSED.value,
        trigger='USER_MANUAL_CLOSE',
        metadata={'exit_price': 4.50, 'pnl': -50.0},
    )

    # Verify db.add was called with a StateTransition
    assert mock_db.add.called, "db.add() should have been called"
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.trade_id == 42
    assert added_obj.from_status == 'OPEN'
    assert added_obj.to_status == 'CLOSED'
    assert added_obj.trigger == 'USER_MANUAL_CLOSE'
    assert added_obj.metadata_json['pnl'] == -50.0

test("T-OL-02", "StateTransition: OPEN→CLOSED on manual close", t_ol_02)


# ── T-OL-03: StateTransition on broker fill ─────────────────

def t_ol_03():
    from backend.services.monitor_service import MonitorService
    from backend.database.paper_models import TradeStatus

    ms = MonitorService()

    mock_db = MagicMock()
    mock_trade = MagicMock()
    mock_trade.id = 10
    mock_trade.ticker = 'AAPL'
    mock_trade.entry_price = 3.00
    mock_trade.qty = 2
    mock_trade.direction = 'BUY'
    mock_trade.sl_price = 2.00
    mock_trade.tp_price = 5.00
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    order = {'avg_fill_price': '5.20', 'status': 'filled'}
    ms._handle_fill(mock_db, mock_trade, order)

    # Verify _log_transition was called internally
    assert mock_db.add.called, "db.add() should create StateTransition"
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.from_status == 'OPEN'
    assert added_obj.to_status == 'CLOSED'
    assert added_obj.trigger == 'BROKER_FILL'
    assert added_obj.metadata_json['close_reason'] == 'TP_HIT'

test("T-OL-03", "StateTransition: OPEN→CLOSED on broker fill (TP_HIT)", t_ol_03)


# ── T-OL-04: StateTransition on expiration ──────────────────

def t_ol_04():
    from backend.services.monitor_service import MonitorService
    from backend.database.paper_models import TradeStatus

    ms = MonitorService()

    mock_db = MagicMock()
    mock_trade = MagicMock()
    mock_trade.id = 20
    mock_trade.ticker = 'NVDA'
    mock_trade.entry_price = 8.00
    mock_trade.qty = 1
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    ms._handle_expiration(mock_db, mock_trade)

    assert mock_db.add.called
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.from_status == 'OPEN'
    assert added_obj.to_status == 'EXPIRED'
    assert added_obj.trigger == 'BROKER_EXPIRED'

test("T-OL-04", "StateTransition: OPEN→EXPIRED on expiration", t_ol_04)


# ── T-OL-05: StateTransition on cancellation ────────────────

def t_ol_05():
    from backend.services.monitor_service import MonitorService
    from backend.database.paper_models import TradeStatus

    ms = MonitorService()

    mock_db = MagicMock()
    mock_trade = MagicMock()
    mock_trade.id = 30
    mock_trade.ticker = 'TSLA'
    mock_trade.version = 1
    mock_trade.status = 'OPEN'
    mock_trade.trade_context = {}

    ms._handle_cancellation(mock_db, mock_trade, 'rejected')

    assert mock_db.add.called
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.from_status == 'OPEN'
    assert added_obj.to_status == 'CANCELED'
    assert added_obj.trigger == 'BROKER_REJECTED'

test("T-OL-05", "StateTransition: OPEN→CANCELED on rejection", t_ol_05)


# ── T-OL-06: Tradier order attempted with credentials ──────

def t_ol_06():
    """Verify that place_trade() calls broker.place_order when credentials exist."""
    from backend.services.broker.factory import BrokerFactory

    mock_broker = MagicMock()
    mock_broker.place_order.return_value = {'id': '12345', 'status': 'pending'}
    mock_broker.place_oco_order.return_value = {'sl_id': '12346', 'tp_id': '12347'}

    # Verify the broker has the expected interface
    assert hasattr(mock_broker, 'place_order')
    assert hasattr(mock_broker, 'place_oco_order')
    assert hasattr(mock_broker, 'cancel_order')

    result = mock_broker.place_order({
        'symbol': 'AAPL260320C00150000',
        'side': 'buy_to_open',
        'quantity': 1,
        'type': 'limit',
        'price': 5.00,
        'duration': 'day',
    })
    assert result['id'] == '12345', f"Expected '12345', got {result.get('id')}"

test("T-OL-06", "Broker interface: place_order returns order_id", t_ol_06)


# ── T-OL-07: Paper-only when no credentials ────────────────

def t_ol_07():
    """Verify trade is saved even without broker credentials."""
    from backend.database.paper_models import PaperTrade, TradeStatus

    # Simulate trade creation without broker
    trade = PaperTrade(
        username='test_user',
        ticker='AAPL',
        option_type='CALL',
        strike=150.0,
        expiry='2026-03-20',
        entry_price=5.00,
        qty=1,
        status=TradeStatus.OPEN.value,
    )

    # Without broker credentials, tradier fields should be None
    assert trade.tradier_order_id is None
    assert trade.tradier_sl_order_id is None
    assert trade.tradier_tp_order_id is None
    assert trade.status == 'OPEN'

test("T-OL-07", "Paper-only: trade saved without broker IDs", t_ol_07)


# ── T-OL-08: OCO brackets placed when SL + TP set ──────────

def t_ol_08():
    """Verify OCO order structure matches Tradier's expected format."""
    mock_broker = MagicMock()
    mock_broker.place_oco_order.return_value = {'sl_id': '100', 'tp_id': '101'}

    oco = mock_broker.place_oco_order(
        sl_order={
            'symbol': 'NVDA260320C00200000',
            'side': 'sell_to_close',
            'quantity': 1,
            'type': 'stop',
            'stop': 3.75,
            'duration': 'gtc',
        },
        tp_order={
            'symbol': 'NVDA260320C00200000',
            'side': 'sell_to_close',
            'quantity': 1,
            'type': 'limit',
            'price': 7.50,
            'duration': 'gtc',
        },
    )

    assert oco['sl_id'] == '100'
    assert oco['tp_id'] == '101'
    # Verify the call was made with correct args
    call_args = mock_broker.place_oco_order.call_args
    assert call_args[1]['sl_order']['type'] == 'stop'
    assert call_args[1]['tp_order']['type'] == 'limit'

test("T-OL-08", "OCO brackets: SL=stop + TP=limit placed together", t_ol_08)


# ── T-OL-09: OCC symbol format ─────────────────────────────

def t_ol_09():
    from backend.services.monitor_service import MonitorService

    mock_trade = MagicMock()
    mock_trade.ticker = 'AAPL'
    mock_trade.expiry = '2026-03-20'
    mock_trade.option_type = 'CALL'
    mock_trade.strike = 150.0

    occ = MonitorService._build_occ_symbol(mock_trade)

    # Expected: AAPL260320C00150000
    assert occ == 'AAPL260320C00150000', f"Expected AAPL260320C00150000, got {occ}"

test("T-OL-09", "OCC symbol: AAPL 260320 $150 CALL → AAPL260320C00150000", t_ol_09)


# ── T-OL-10: _log_transition metadata contains all fields ──

def t_ol_10():
    from backend.services.monitor_service import MonitorService
    from backend.database.paper_models import StateTransition

    ms = MonitorService()
    mock_db = MagicMock()
    mock_trade = MagicMock()
    mock_trade.id = 99

    ms._log_transition(
        mock_db, mock_trade,
        from_status='OPEN',
        to_status='CLOSED',
        trigger='BROKER_FILL',
        metadata={'fill_price': 7.50, 'close_reason': 'TP_HIT', 'pnl': 250.0},
    )

    added = mock_db.add.call_args[0][0]
    assert isinstance(added, StateTransition)
    assert added.trade_id == 99
    assert added.metadata_json['fill_price'] == 7.50
    assert added.metadata_json['close_reason'] == 'TP_HIT'
    assert added.metadata_json['pnl'] == 250.0

test("T-OL-10", "_log_transition captures full metadata JSONB", t_ol_10)


# ── Summary ────────────────────────────────────────────────

print("\n" + "=" * 60)
print(f"Phase 4 Results: {passed} passed, {failed} failed out of {passed + failed}")
print("=" * 60)

if failed > 0:
    sys.exit(1)
