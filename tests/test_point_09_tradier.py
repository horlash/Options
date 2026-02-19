"""
Regression Tests for Point 9: Tradier Integration
==================================================
Tests T-09-01 through T-09-10

These tests hit the LIVE Tradier Sandbox API.
Sandbox credentials are loaded from environment or hardcoded for dev.

Usage:
    $env:PYTHONPATH = "."; python tests/test_point_09_tradier.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.services.broker.tradier import TradierBroker
from backend.services.broker.factory import BrokerFactory
from backend.services.broker.exceptions import (
    BrokerException,
    BrokerAuthException,
    BrokerOrderRejectedException,
)
from backend.utils.rate_limiter import RateLimiter
from backend.security.crypto import encrypt, decrypt

# ─── Sandbox Credentials ───────────────────────────────────────────
SANDBOX_TOKEN = os.getenv('TRADIER_SANDBOX_TOKEN', '8A09vGkjXxbJspeGkT0iNI8VEapW')
SANDBOX_ACCOUNT = os.getenv('TRADIER_SANDBOX_ACCOUNT', 'VA81170223')

# Generate an encryption key for tests if not set
TEST_ENCRYPTION_KEY = 'hNk-Qz1vHmDxJyGGqX3sdRGXsUqx6T1MnZq1bGzXJpE='
os.environ.setdefault('ENCRYPTION_KEY', TEST_ENCRYPTION_KEY)

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
        print(f"     Error: {type(e).__name__}: {e}")
        failed += 1


# Create broker instance for all tests
broker = BrokerFactory.get_broker_direct(
    token=SANDBOX_TOKEN,
    account_id=SANDBOX_ACCOUNT,
    is_live=False,
)


# =========================================================================
# T-09-01: Connection test — validate sandbox credentials
# =========================================================================
def t_09_01():
    result = broker.test_connection()
    assert result["connected"] is True, f"Connection failed: {result}"
    assert result["environment"] == "SANDBOX"
    assert result["account_id"] == SANDBOX_ACCOUNT
    print(f"     → Name: {result.get('name')}, Type: {result.get('account_type')}, "
          f"Status: {result.get('status')}")

test("T-09-01", "Sandbox connection test succeeds with valid credentials", t_09_01)


# =========================================================================
# T-09-02: Get stock quotes
# =========================================================================
def t_09_02():
    quotes = broker.get_quotes(['AAPL', 'MSFT', 'SPY'])
    assert len(quotes) == 3, f"Expected 3 quotes, got {len(quotes)}"
    for q in quotes:
        assert q["symbol"] in ('AAPL', 'MSFT', 'SPY'), f"Unexpected symbol: {q['symbol']}"
        assert q["last"] is not None, f"{q['symbol']} has no last price"
        assert q["bid"] is not None, f"{q['symbol']} has no bid"
        assert q["ask"] is not None, f"{q['symbol']} has no ask"
    aapl = next(q for q in quotes if q["symbol"] == "AAPL")
    print(f"     → AAPL: last=${aapl['last']}, bid=${aapl['bid']}, ask=${aapl['ask']}, "
          f"vol={aapl['volume']}")

test("T-09-02", "Get stock quotes (AAPL, MSFT, SPY) with all fields", t_09_02)


# =========================================================================
# T-09-03: Get account balance
# =========================================================================
def t_09_03():
    balance = broker.get_account_balance()
    assert balance["total_equity"] is not None, "Missing total_equity"
    assert balance["account_type"] is not None, "Missing account_type"
    print(f"     → Equity: ${balance['total_equity']}, "
          f"Type: {balance['account_type']}, "
          f"Option BP: {balance.get('option_buying_power')}")

test("T-09-03", "Get account balance with equity and buying power", t_09_03)


# =========================================================================
# T-09-04: Get option expirations for AAPL
# =========================================================================
def t_09_04():
    exps = broker.get_option_expirations('AAPL')
    assert len(exps) > 0, "No expirations returned for AAPL"
    # Expirations should be date strings
    for exp in exps[:3]:
        assert len(exp) == 10, f"Expiration format wrong: {exp}"
        assert exp[4] == '-', f"Expiration format wrong: {exp}"
    print(f"     → {len(exps)} expirations, nearest: {exps[0]}, farthest: {exps[-1]}")

test("T-09-04", "Get option expirations for AAPL", t_09_04)


# =========================================================================
# T-09-05: Get option chain with greeks
# =========================================================================
def t_09_05():
    # Get nearest expiry first
    exps = broker.get_option_expirations('AAPL')
    assert len(exps) > 0, "No expirations for chain test"
    nearest_exp = exps[0]

    chain = broker.get_option_chain('AAPL', nearest_exp, option_type='call')
    assert len(chain) > 0, f"No options in chain for AAPL {nearest_exp}"

    # Find a call option in the chain
    # Note: Sandbox may return mixed types despite filter param
    calls = [o for o in chain if o.get("option_type") == "call"]
    if not calls:
        # Sandbox quirk: may not filter — just use first option
        opt = chain[0]
        print(f"     ⚠ Sandbox ignored option_type filter (got {opt['option_type']})")
    else:
        opt = calls[0]

    # Check the option has all required fields
    assert opt["symbol"] is not None, "Missing OCC symbol"
    assert opt["strike"] is not None, "Missing strike"
    assert "greeks" in opt, "Missing greeks"

    # Check greeks structure exists
    greeks = opt["greeks"]
    has_greeks = greeks.get("delta") is not None
    print(f"     → Chain: {len(chain)} options for {nearest_exp}, "
          f"strike: ${opt['strike']}, type: {opt['option_type']}, "
          f"delta: {greeks.get('delta')}, greeks: {has_greeks}")

test("T-09-05", "Get option chain with greeks for AAPL", t_09_05)


# =========================================================================
# T-09-06: Place a sandbox market order (buy 1 AAPL share)
# =========================================================================
placed_order_id = None

def t_09_06():
    global placed_order_id
    order_id = broker.place_order({
        "class": "equity",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 1,
        "type": "market",
        "duration": "day",
    })
    assert order_id is not None, "No order_id returned"
    assert str(order_id).isdigit(), f"Order ID not numeric: {order_id}"
    placed_order_id = order_id
    print(f"     → Order ID: {order_id}")

test("T-09-06", "Place sandbox market order (buy 1 AAPL)", t_09_06)


# =========================================================================
# T-09-07: Get order status for the placed order
# =========================================================================
def t_09_07():
    assert placed_order_id is not None, "No order was placed in T-09-06"
    time.sleep(1)  # Let it settle
    order = broker.get_order(placed_order_id)
    assert order is not None, "Order not found"
    status = order.get("status", "unknown")
    print(f"     → Order {placed_order_id}: status={status}, "
          f"side={order.get('side')}, symbol={order.get('symbol')}")

test("T-09-07", "Get order status returns valid data", t_09_07)


# =========================================================================
# T-09-08: Get positions after trade
# =========================================================================
def t_09_08():
    positions = broker.get_positions()
    # May or may not have positions depending on sandbox state
    print(f"     → {len(positions)} open positions")
    for p in positions[:3]:
        print(f"       {p['symbol']}: qty={p['quantity']}, cost={p.get('cost_basis')}")

test("T-09-08", "Get positions returns list (may be empty in sandbox)", t_09_08)


# =========================================================================
# T-09-09: Auth failure with wrong token
# =========================================================================
def t_09_09():
    bad_broker = BrokerFactory.get_broker_direct(
        token="INVALID_TOKEN_12345",
        account_id=SANDBOX_ACCOUNT,
        is_live=False,
    )
    result = bad_broker.test_connection()
    assert result["connected"] is False, "Should fail with invalid token"
    assert "error" in result, "Should have error message"
    print(f"     → Correctly rejected: {result['error'][:60]}")

test("T-09-09", "Authentication fails gracefully with wrong token", t_09_09)


# =========================================================================
# T-09-10: Fernet encryption round-trip for tokens
# =========================================================================
def t_09_10():
    original = SANDBOX_TOKEN
    encrypted = encrypt(original)
    assert encrypted != original, "Encrypted should differ from original"
    assert len(encrypted) > len(original), "Encrypted should be longer"

    decrypted = decrypt(encrypted)
    assert decrypted == original, f"Round-trip failed: got {decrypted[:10]}..."

    # Verify encrypted token can't be easily read
    assert SANDBOX_TOKEN not in encrypted, "Token visible in ciphertext!"
    print(f"     → Original: {original[:8]}..., Encrypted: {encrypted[:20]}..., "
          f"Round-trip: ✓")

test("T-09-10", "Fernet encryption round-trip preserves token", t_09_10)


# =========================================================================
# T-09-11: Rate limiter enforces sliding window
# =========================================================================
def t_09_11():
    limiter = RateLimiter(max_calls=5, period=2)
    start = time.time()

    # Make 5 calls instantly (should all pass)
    for _ in range(5):
        limiter.wait()

    # 6th call should block until window slides
    limiter.wait()
    elapsed = time.time() - start
    assert elapsed >= 1.5, f"Rate limiter didn't block (elapsed={elapsed:.2f}s)"
    print(f"     → 6 calls took {elapsed:.2f}s (expected ≥1.5s): rate limiting works")

test("T-09-11", "Rate limiter blocks when limit reached", t_09_11)


# =========================================================================
# T-09-12: Get all orders
# =========================================================================
def t_09_12():
    orders = broker.get_orders()
    assert isinstance(orders, list), f"Expected list, got {type(orders)}"
    print(f"     → {len(orders)} total orders in account")
    if orders:
        latest = orders[-1] if isinstance(orders[-1], dict) else orders[-1]
        print(f"       Latest: {latest.get('symbol')} {latest.get('side')} "
              f"status={latest.get('status')}")

test("T-09-12", "Get all orders returns list", t_09_12)


# =========================================================================
# T-09-13: Factory creates broker from encrypted settings (mock)
# =========================================================================
def t_09_13():
    """Simulate the full factory flow with encrypted token."""
    class MockUserSettings:
        broker_mode = 'TRADIER_SANDBOX'
        tradier_sandbox_token = encrypt(SANDBOX_TOKEN)
        tradier_live_token = None
        tradier_account_id = SANDBOX_ACCOUNT

    settings = MockUserSettings()
    factory_broker = BrokerFactory.get_broker(settings)
    result = factory_broker.test_connection()
    assert result["connected"] is True, f"Factory broker failed: {result}"
    print(f"     → Factory → encrypt → decrypt → connect: ✓")

test("T-09-13", "BrokerFactory creates working broker from encrypted settings", t_09_13)


# =========================================================================
# Summary
# =========================================================================
print(f"\n{'='*50}")
print(f"Point 9 Regression Results: {passed}/{total} passed, {failed} failed")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)
