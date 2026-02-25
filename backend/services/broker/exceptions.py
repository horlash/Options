"""
Broker Exception Hierarchy
==========================
Point 9: Normalized error types for all broker operations.
Every Tradier HTTP error maps to one of these.
"""


class BrokerException(Exception):
    """Base exception for all broker operations."""

    def __init__(self, message: str, status_code: int = None, raw_response: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response


class BrokerAuthException(BrokerException):
    """401 — Invalid or expired token. User must re-authenticate."""
    pass


class BrokerRateLimitException(BrokerException):
    """429 — Rate limited. Caller should wait and retry."""
    pass


class BrokerInsufficientFundsException(BrokerException):
    """Order rejected due to insufficient buying power or margin violation."""
    pass


class BrokerOrderRejectedException(BrokerException):
    """
    The '200 OK but actually failed' gotcha.
    Order was accepted by Tradier but rejected downstream
    (risk management, margin check, invalid symbol, etc.).
    """

    def __init__(self, message: str, order_id: str = None, reject_reason: str = None):
        super().__init__(message)
        self.order_id = order_id
        self.reject_reason = reject_reason


class BrokerUnavailableException(BrokerException):
    """503 — Broker is down or in maintenance."""
    pass


class BrokerTimeoutException(BrokerException):
    """Request to broker timed out."""
    pass
