"""
Tradier Broker — Concrete Implementation
==========================================
Point 9: Full Tradier API client implementing BrokerProvider.

Supports:
  - Sandbox (https://sandbox.tradier.com/v1)
  - Live    (https://api.tradier.com/v1)

Key behaviors:
  - Rate limiting (50/min sliding window)
  - Automatic retry on 429 (rate limit) and 503 (unavailable)
  - Post-placement order confirmation (the "200 OK but rejected" gotcha)
  - Tradier response header monitoring
"""

import time
import logging
from typing import List, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.services.broker.base import BrokerProvider
from backend.services.broker.exceptions import (
    BrokerException,
    BrokerAuthException,
    BrokerRateLimitException,
    BrokerOrderRejectedException,
    BrokerUnavailableException,
    BrokerTimeoutException,
    BrokerInsufficientFundsException,
)
from backend.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class TradierBroker(BrokerProvider):
    """Tradier API broker implementation.

    Supports both Sandbox and Live environments.
    Factory creates instances via BrokerFactory.get_broker().
    """

    SANDBOX_URL = "https://sandbox.tradier.com/v1"
    LIVE_URL = "https://api.tradier.com/v1"

    # Order confirmation polling
    ORDER_CONFIRM_DELAY = 1.0         # seconds to wait before checking status
    ORDER_CONFIRM_MAX_RETRIES = 3     # max retries for confirmation poll
    ORDER_CONFIRM_RETRY_DELAY = 1.0   # seconds between confirmation retries

    # Request timeout (sandbox chains endpoint can be slow)
    REQUEST_TIMEOUT = 30  # seconds

    def __init__(self, access_token: str, account_id: str, is_live: bool = False):
        """
        Args:
            access_token: Tradier bearer token (sandbox or live)
            account_id: Tradier account number (e.g. 'VA81170223')
            is_live: True for live trading, False for sandbox
        """
        self.token = access_token
        self.account_id = account_id
        self.is_live = is_live
        self.base_url = self.LIVE_URL if is_live else self.SANDBOX_URL
        self.environment = "LIVE" if is_live else "SANDBOX"

        # Rate limiter: 50/min for safety (sandbox=60, live=120)
        self.limiter = RateLimiter(max_calls=50, period=60)

        # Persistent session with retry logic for transient failures
        self.session = self._build_session()

        logger.info(
            f"TradierBroker initialized: env={self.environment}, "
            f"account={self.account_id}, base_url={self.base_url}"
        )

    def _build_session(self) -> requests.Session:
        """Build a requests session with retry strategy and auth headers."""
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        })

        # Retry strategy: 2 retries on 429/500/502/503 with exponential backoff
        retry_strategy = Retry(
            total=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503],
            allowed_methods=["GET", "DELETE"],   # Only retry idempotent methods
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        s.mount("https://", adapter)
        return s

    # ─── Internal request method ────────────────────────────────────

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        """Execute an API request with rate limiting, timeout, and error handling.

        Args:
            method: HTTP method ('GET', 'POST', 'DELETE')
            path: API path (appended to base_url)
            **kwargs: Passed to requests (params, data, json, etc.)

        Returns:
            requests.Response object

        Raises:
            BrokerAuthException, BrokerRateLimitException,
            BrokerUnavailableException, BrokerTimeoutException,
            BrokerException (generic)
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        kwargs.setdefault('timeout', self.REQUEST_TIMEOUT)

        # Rate limit
        waited = self.limiter.wait()
        if waited > 0:
            logger.warning(f"Rate limiter: waited {waited:.1f}s before {method} {path}")

        # Execute request
        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.exceptions.Timeout:
            raise BrokerTimeoutException(
                f"Request timed out: {method} {path}",
                status_code=408
            )
        except requests.exceptions.ConnectionError as e:
            raise BrokerUnavailableException(
                f"Connection failed: {method} {path} — {e}",
                status_code=503
            )

        # Update rate limiter from response headers
        self.limiter.update_from_headers(resp.headers)

        # Log the call
        logger.debug(
            f"Tradier {method} {path} → {resp.status_code} "
            f"(rate: {self.limiter.remaining} remaining)"
        )

        # Error mapping
        self._check_response(resp, method, path)

        return resp

    def _check_response(self, resp: requests.Response, method: str, path: str):
        """Map HTTP status codes to our exception hierarchy."""
        if resp.status_code < 400:
            return  # Success

        raw = resp.text[:500]  # Truncate for logging

        if resp.status_code == 401:
            raise BrokerAuthException(
                f"Authentication failed ({self.environment}). "
                f"Token may be invalid or expired. "
                f"Sandbox and Live tokens are NOT interchangeable.",
                status_code=401,
                raw_response=raw,
            )

        if resp.status_code == 429:
            raise BrokerRateLimitException(
                f"Rate limited by Tradier. Waited but still hit limit.",
                status_code=429,
                raw_response=raw,
            )

        if resp.status_code == 403:
            raise BrokerException(
                f"Insufficient permissions: {method} {path}",
                status_code=403,
                raw_response=raw,
            )

        if resp.status_code in (500, 502):
            raise BrokerException(
                f"Tradier server error ({resp.status_code}): {method} {path}",
                status_code=resp.status_code,
                raw_response=raw,
            )

        if resp.status_code == 503:
            raise BrokerUnavailableException(
                "Tradier is unavailable (maintenance or outage).",
                status_code=503,
                raw_response=raw,
            )

        raise BrokerException(
            f"Tradier error {resp.status_code}: {raw}",
            status_code=resp.status_code,
            raw_response=raw,
        )

    # ─── Market Data ────────────────────────────────────────────────

    def get_quotes(self, symbols: List[str]) -> List[dict]:
        """Get current quotes for one or more symbols.

        Note: Sandbox quotes are 15-minute delayed.
        """
        if not symbols:
            return []

        resp = self._request(
            'GET', '/markets/quotes',
            params={"symbols": ",".join(symbols), "greeks": "false"}
        )
        data = resp.json()

        quotes = data.get("quotes", {}).get("quote", [])
        # Tradier returns a dict for single symbol, list for multiple
        if isinstance(quotes, dict):
            quotes = [quotes]

        # Normalize to our format
        return [self._normalize_quote(q) for q in quotes]

    def _normalize_quote(self, q: dict) -> dict:
        """Normalize a Tradier quote dict to our standard format."""
        return {
            "symbol": q.get("symbol"),
            "description": q.get("description"),
            "last": q.get("last"),
            "bid": q.get("bid"),
            "ask": q.get("ask"),
            "high": q.get("high"),
            "low": q.get("low"),
            "open": q.get("open"),
            "close": q.get("close"),  # previous close
            "volume": q.get("volume"),
            "change": q.get("change"),
            "change_percentage": q.get("change_percentage"),
            "average_volume": q.get("average_volume"),
            "last_volume": q.get("last_volume"),
            "trade_date": q.get("trade_date"),
            "type": q.get("type"),  # 'stock', 'option', 'etf', etc.
        }

    def get_option_chain(self, symbol: str, expiry: str, option_type: str = None) -> List[dict]:
        """Get option chain for a symbol and expiration date.

        Args:
            symbol: Underlying ticker (e.g. 'AAPL')
            expiry: Expiration date as 'YYYY-MM-DD'
            option_type: 'call', 'put', or None (both)
        """
        params = {
            "symbol": symbol,
            "expiration": expiry,
            "greeks": "true",
        }
        if option_type:
            params["option_type"] = option_type.lower()

        resp = self._request('GET', '/markets/options/chains', params=params)
        data = resp.json()

        options = data.get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]

        return [self._normalize_option(o) for o in options]

    def _normalize_option(self, o: dict) -> dict:
        """Normalize a Tradier option dict to our standard format."""
        greeks = o.get("greeks") or {}
        return {
            "symbol": o.get("symbol"),           # OCC symbol (e.g. AAPL260620C00150000)
            "underlying": o.get("underlying"),
            "strike": o.get("strike"),
            "option_type": o.get("option_type"),  # 'call' or 'put'
            "expiration_date": o.get("expiration_date"),
            "last": o.get("last"),
            "bid": o.get("bid"),
            "ask": o.get("ask"),
            "volume": o.get("volume"),
            "open_interest": o.get("open_interest"),
            "greeks": {
                "delta": greeks.get("delta"),
                "gamma": greeks.get("gamma"),
                "theta": greeks.get("theta"),
                "vega": greeks.get("vega"),
                "rho": greeks.get("rho"),
                "iv": greeks.get("mid_iv") or greeks.get("smv_vol"),
            },
        }

    def get_option_expirations(self, symbol: str) -> List[str]:
        """Get available option expiration dates."""
        resp = self._request(
            'GET', '/markets/options/expirations',
            params={"symbol": symbol, "includeAllRoots": "true", "strikes": "false"}
        )
        data = resp.json()

        expirations = data.get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            expirations = [expirations]
        return expirations

    # ─── Order Management ───────────────────────────────────────────

    def place_order(self, order_request: dict) -> str:
        """Place a single-leg order with post-placement confirmation.

        CRITICAL: Tradier returns 200 OK immediately but the order can
        be rejected downstream. We poll order status to confirm.
        """
        # Build the form data payload
        payload = {
            "class": order_request.get("class", "option"),
            "symbol": order_request["symbol"],
            "side": order_request["side"],
            "quantity": str(order_request["quantity"]),
            "type": order_request.get("type", "market"),
            "duration": order_request.get("duration", "day"),
        }

        # Add price fields if present
        if "price" in order_request:
            payload["price"] = str(order_request["price"])
        if "stop" in order_request:
            payload["stop"] = str(order_request["stop"])

        # Place the order
        resp = self._request(
            'POST',
            f'/accounts/{self.account_id}/orders',
            data=payload
        )
        result = resp.json()
        order_data = result.get("order", {})
        order_id = str(order_data.get("id"))

        logger.info(f"Order placed: id={order_id}, status={order_data.get('status')}")

        # ── THE GOTCHA FIX: Confirm the order wasn't silently rejected ──
        time.sleep(self.ORDER_CONFIRM_DELAY)
        confirmation = self._confirm_order(order_id)

        if confirmation.get("status") == "rejected":
            reason = confirmation.get("reason_description", "Unknown reason")
            logger.error(f"Order {order_id} rejected downstream: {reason}")
            raise BrokerOrderRejectedException(
                f"Order was accepted but rejected downstream: {reason}",
                order_id=order_id,
                reject_reason=reason,
            )

        return order_id

    def _confirm_order(self, order_id: str) -> dict:
        """Poll order status to confirm it wasn't silently rejected."""
        for attempt in range(self.ORDER_CONFIRM_MAX_RETRIES):
            try:
                order = self.get_order(order_id)
                status = order.get("status", "").lower()

                # Terminal states — we know the result
                if status in ("filled", "partially_filled", "rejected", "canceled", "expired"):
                    return order

                # Non-terminal — still processing, wait and retry
                if status in ("pending", "open"):
                    return order  # Accepted, not yet filled — this is fine

                # Unknown status
                logger.warning(f"Order {order_id}: unknown status '{status}', retry {attempt + 1}")

            except BrokerException as e:
                logger.warning(f"Confirmation poll failed (attempt {attempt + 1}): {e}")

            if attempt < self.ORDER_CONFIRM_MAX_RETRIES - 1:
                time.sleep(self.ORDER_CONFIRM_RETRY_DELAY)

        # If all retries exhausted, return what we have
        logger.warning(f"Order {order_id}: confirmation polling exhausted, assuming OK")
        return {"status": "unknown", "id": order_id}

    def place_oco_order(self, sl_order: dict, tp_order: dict) -> dict:
        """Place a One-Cancels-Other order for SL/TP brackets (Point 4).

        Tradier OCO format uses indexed brackets for each leg.
        """
        payload = {
            "class": "oco",
            "duration": "gtc",
            # Leg 1: Stop Loss
            "side[0]": "sell_to_close",
            "symbol[0]": sl_order["symbol"],
            "quantity[0]": str(sl_order["qty"]),
            "type[0]": "stop",
            "stop[0]": str(sl_order["stop_price"]),
            # Leg 2: Take Profit
            "side[1]": "sell_to_close",
            "symbol[1]": tp_order["symbol"],
            "quantity[1]": str(tp_order["qty"]),
            "type[1]": "limit",
            "price[1]": str(tp_order["limit_price"]),
        }

        resp = self._request(
            'POST',
            f'/accounts/{self.account_id}/orders',
            data=payload
        )

        result = resp.json().get("order", {})
        logger.info(f"OCO order placed: {result}")
        return result

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order. Returns True if successful."""
        try:
            resp = self._request(
                'DELETE',
                f'/accounts/{self.account_id}/orders/{order_id}'
            )
            return resp.status_code == 200
        except BrokerException as e:
            logger.warning(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_order(self, order_id: str) -> dict:
        """Get the current status of an order."""
        resp = self._request(
            'GET',
            f'/accounts/{self.account_id}/orders/{order_id}'
        )
        data = resp.json()
        return data.get("order", data)

    def get_orders(self) -> List[dict]:
        """Get all orders for the account."""
        resp = self._request(
            'GET',
            f'/accounts/{self.account_id}/orders'
        )
        data = resp.json()
        orders = data.get("orders", {})

        if orders == "null" or orders is None:
            return []

        order_list = orders.get("order", [])
        if isinstance(order_list, dict):
            order_list = [order_list]
        return order_list

    # ─── Account ────────────────────────────────────────────────────

    def get_account_balance(self) -> dict:
        """Get account balance and buying power."""
        resp = self._request(
            'GET',
            f'/accounts/{self.account_id}/balances'
        )
        data = resp.json()
        balances = data.get("balances", {})
        return self._normalize_balance(balances)

    def _normalize_balance(self, b: dict) -> dict:
        """Normalize Tradier balance response."""
        # Tradier nests marginally differently for margin vs cash accounts
        margin = b.get("margin", {})
        cash = b.get("cash", {})
        pdt = b.get("pdt", {})

        return {
            "total_equity": b.get("total_equity"),
            "total_cash": b.get("total_cash"),
            "market_value": b.get("market_value"),
            "open_pnl": b.get("open_pl"),
            "close_pnl": b.get("close_pl"),
            "option_buying_power": margin.get("option_buying_power") or cash.get("option_buying_power"),
            "stock_buying_power": margin.get("stock_buying_power") or cash.get("stock_buying_power"),
            "account_type": b.get("account_type"),
            "pending_cash": b.get("pending_cash"),
            "uncleared_funds": b.get("uncleared_funds"),
            "pending_orders_count": b.get("pending_orders_count"),
            # Raw for debugging
            "_raw": b,
        }

    def get_positions(self) -> List[dict]:
        """Get all open positions."""
        resp = self._request(
            'GET',
            f'/accounts/{self.account_id}/positions'
        )
        data = resp.json()
        positions = data.get("positions", {})

        if positions == "null" or positions is None:
            return []

        pos_list = positions.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]

        return [self._normalize_position(p) for p in pos_list]

    def _normalize_position(self, p: dict) -> dict:
        """Normalize a Tradier position dict."""
        return {
            "symbol": p.get("symbol"),
            "quantity": p.get("quantity"),
            "cost_basis": p.get("cost_basis"),
            "current_value": p.get("market_value"),
            "pnl": (p.get("market_value", 0) or 0) - (p.get("cost_basis", 0) or 0),
            "date_acquired": p.get("date_acquired"),
            "id": p.get("id"),
        }

    # ─── Connection Test ────────────────────────────────────────────

    def test_connection(self) -> dict:
        """Test the broker connection by fetching the user profile."""
        try:
            resp = self._request('GET', '/user/profile')
            data = resp.json()
            profile = data.get("profile", {})
            account_info = profile.get("account", {})

            # Tradier may return a list of accounts
            if isinstance(account_info, list):
                # Find the matching account
                matched = next(
                    (a for a in account_info if a.get("account_number") == self.account_id),
                    account_info[0] if account_info else {}
                )
            else:
                matched = account_info

            return {
                "connected": True,
                "account_id": matched.get("account_number", self.account_id),
                "name": profile.get("name"),
                "environment": self.environment,
                "account_type": matched.get("type"),
                "classification": matched.get("classification"),
                "status": matched.get("status"),
                "day_trader": matched.get("day_trader"),
            }
        except BrokerAuthException:
            return {
                "connected": False,
                "error": "Authentication failed — check your API token",
                "environment": self.environment,
            }
        except BrokerException as e:
            return {
                "connected": False,
                "error": str(e),
                "environment": self.environment,
            }

    # ─── Utility ────────────────────────────────────────────────────

    @property
    def rate_limit_remaining(self) -> int:
        """How many API calls are available before rate limiting kicks in."""
        return self.limiter.remaining

    def __repr__(self):
        return f"TradierBroker(env={self.environment}, account={self.account_id})"
