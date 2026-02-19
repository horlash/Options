"""
BrokerProvider — Abstract Base Class
=====================================
Point 9: Defines the contract for any broker integration.
Any new broker (Schwab, IBKR, etc.) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BrokerProvider(ABC):
    """Abstract base class for broker integrations.

    All methods return normalized data structures regardless of the
    underlying broker API. This allows the trade service layer to be
    broker-agnostic.
    """

    # ─── Market Data ────────────────────────────────────────────────

    @abstractmethod
    def get_quotes(self, symbols: List[str]) -> List[dict]:
        """Get current quotes for one or more symbols.

        Args:
            symbols: List of ticker symbols (e.g. ['AAPL', 'MSFT'])

        Returns:
            List of quote dicts, each containing at minimum:
                symbol, last, bid, ask, volume, change, change_percentage
        """
        pass

    @abstractmethod
    def get_option_chain(self, symbol: str, expiry: str, option_type: str = None) -> List[dict]:
        """Get option chain for a symbol and expiration date.

        Args:
            symbol: Underlying ticker (e.g. 'AAPL')
            expiry: Expiration date as 'YYYY-MM-DD'
            option_type: Optional filter — 'call', 'put', or None (both)

        Returns:
            List of option dicts, each containing at minimum:
                symbol (OCC), strike, option_type, bid, ask, last,
                volume, open_interest, greeks (dict with delta, gamma, theta, vega, iv)
        """
        pass

    @abstractmethod
    def get_option_expirations(self, symbol: str) -> List[str]:
        """Get available option expiration dates for a symbol.

        Args:
            symbol: Underlying ticker (e.g. 'AAPL')

        Returns:
            List of expiration date strings ['YYYY-MM-DD', ...]
        """
        pass

    # ─── Order Management ───────────────────────────────────────────

    @abstractmethod
    def place_order(self, order_request: dict) -> str:
        """Place a single-leg order. Returns order_id.

        Args:
            order_request: Dict with keys:
                symbol (OCC symbol for options), side, quantity, type,
                duration, price (for limit), stop (for stop orders)

        Returns:
            order_id as string

        Raises:
            BrokerOrderRejectedException: If order was accepted (200 OK)
                but rejected downstream by risk/margin checks.
            BrokerException: For HTTP-level errors
        """
        pass

    @abstractmethod
    def place_oco_order(self, sl_order: dict, tp_order: dict) -> dict:
        """Place a One-Cancels-Other order (SL + TP brackets).

        Args:
            sl_order: Stop loss leg — dict with symbol, qty, stop_price
            tp_order: Take profit leg — dict with symbol, qty, limit_price

        Returns:
            Dict with 'id' (parent order), 'leg' (list of child order dicts)
        """
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Returns:
            True if cancellation succeeded, False if order was already
            filled or not cancellable.
        """
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> dict:
        """Get the current status of an order.

        Returns:
            Dict with at minimum: id, status, symbol, side, quantity,
            type, price, avg_fill_price, filled_quantity, create_date
        """
        pass

    @abstractmethod
    def get_orders(self) -> List[dict]:
        """Get all orders for the account.

        Returns:
            List of order dicts (same format as get_order)
        """
        pass

    # ─── Account ────────────────────────────────────────────────────

    @abstractmethod
    def get_account_balance(self) -> dict:
        """Get account balance and buying power.

        Returns:
            Dict with at minimum: total_equity, cash, buying_power,
            market_value, open_pnl, close_pnl
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[dict]:
        """Get all open positions.

        Returns:
            List of position dicts with: symbol, quantity, cost_basis,
            current_value, pnl, pnl_pct
        """
        pass

    # ─── Connection Test ────────────────────────────────────────────

    @abstractmethod
    def test_connection(self) -> dict:
        """Test the broker connection (validates credentials).

        Returns:
            Dict with: connected (bool), account_id, name, environment
        """
        pass
