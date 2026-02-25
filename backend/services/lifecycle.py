"""
Position Lifecycle Manager
===========================
Point 11: State Machine for Trade Lifecycle Management

Enforces strict transition rules for the 7-state trade lifecycle:
  PENDING → OPEN → CLOSING → CLOSED
                 → EXPIRED
  PENDING → PARTIALLY_FILLED → OPEN
                              → CANCELED
  PENDING → CANCELED

Terminal states (CLOSED, EXPIRED, CANCELED) allow no further transitions.
"""

import logging
from datetime import datetime

from backend.database.paper_models import PaperTrade, StateTransition, TradeStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid Transition Whitelist
# ---------------------------------------------------------------------------
# Keys = current status, Values = list of allowed next statuses
VALID_TRANSITIONS = {
    TradeStatus.PENDING: [
        TradeStatus.OPEN,
        TradeStatus.PARTIALLY_FILLED,
        TradeStatus.CANCELED,
    ],
    TradeStatus.PARTIALLY_FILLED: [
        TradeStatus.OPEN,
        TradeStatus.CANCELED,
    ],
    TradeStatus.OPEN: [
        TradeStatus.CLOSING,
        TradeStatus.CLOSED,       # Direct close (manual or SL/TP hit)
        TradeStatus.EXPIRED,
        TradeStatus.CANCELED,     # Broker rejection/cancellation of open position
    ],
    TradeStatus.CLOSING: [
        TradeStatus.CLOSED,
        TradeStatus.OPEN,         # Close order rejected → revert
    ],
    # Terminal states — no transitions allowed
    TradeStatus.CLOSED: [],
    TradeStatus.EXPIRED: [],
    TradeStatus.CANCELED: [],
}


# ---------------------------------------------------------------------------
# Custom Exception
# ---------------------------------------------------------------------------
class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_status, to_status, trade_id=None):
        self.from_status = from_status
        self.to_status = to_status
        self.trade_id = trade_id

        allowed = VALID_TRANSITIONS.get(
            TradeStatus(from_status) if isinstance(from_status, str) else from_status,
            []
        )
        allowed_str = ', '.join(s.value for s in allowed) if allowed else 'NONE'

        msg = (
            f"Invalid transition: {from_status} → {to_status}"
            f"{f' (trade {trade_id})' if trade_id else ''}. "
            f"Allowed from {from_status}: [{allowed_str}]"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Lifecycle Manager
# ---------------------------------------------------------------------------
class LifecycleManager:
    """Enforces state machine rules and logs transitions.

    Usage:
        lm = LifecycleManager(db_session)
        lm.transition(trade, TradeStatus.CLOSED, trigger='BROKER_FILL',
                      metadata={'fill_price': 5.20})
    """

    def __init__(self, db_session):
        self.db = db_session

    # -- Public API ----------------------------------------------------------

    def transition(self, trade, new_status, trigger, metadata=None):
        """Validate and apply a state transition.

        Args:
            trade:       PaperTrade instance to transition.
            new_status:  Target TradeStatus (enum or string).
            trigger:     What caused this transition (e.g. 'BROKER_FILL').
            metadata:    Optional dict of extra context for the audit log.

        Returns:
            The updated PaperTrade instance.

        Raises:
            InvalidTransitionError: If the transition is not allowed.
        """
        # Normalize to enum
        if isinstance(new_status, str):
            new_status = TradeStatus(new_status)

        old_status_str = trade.status
        old_status = TradeStatus(old_status_str) if old_status_str else None

        # Validate
        self._validate_transition(old_status, new_status, trade.id)

        # Apply the status change
        trade.status = new_status.value
        trade.version += 1
        trade.updated_at = datetime.utcnow()

        # Terminal state side effects
        if new_status in (TradeStatus.CLOSED, TradeStatus.EXPIRED, TradeStatus.CANCELED):
            trade.closed_at = datetime.utcnow()

        # Audit trail
        self._log_transition(
            trade,
            from_status=old_status_str,
            to_status=new_status.value,
            trigger=trigger,
            metadata=metadata,
        )

        logger.info(
            f"Trade {trade.id} transitioned: "
            f"{old_status_str} → {new_status.value} via {trigger}"
        )

        return trade

    def can_transition(self, from_status, to_status):
        """Check whether a transition is valid without applying it.

        Args:
            from_status: Current status (string or TradeStatus enum).
            to_status:   Target status (string or TradeStatus enum).

        Returns:
            True if the transition is allowed, False otherwise.
        """
        if isinstance(from_status, str):
            try:
                from_status = TradeStatus(from_status)
            except ValueError:
                return False
        if isinstance(to_status, str):
            try:
                to_status = TradeStatus(to_status)
            except ValueError:
                return False

        allowed = VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    def get_allowed_transitions(self, from_status):
        """Return list of allowed next statuses from the given status.

        Args:
            from_status: Current status (string or TradeStatus enum).

        Returns:
            List of TradeStatus values that are valid next states.
        """
        if isinstance(from_status, str):
            from_status = TradeStatus(from_status)
        return list(VALID_TRANSITIONS.get(from_status, []))

    # -- Private helpers -----------------------------------------------------

    def _validate_transition(self, old_status, new_status, trade_id=None):
        """Raise InvalidTransitionError if the transition is forbidden."""
        if old_status is None:
            # Initial creation — only PENDING or OPEN are allowed as first state
            if new_status not in (TradeStatus.PENDING, TradeStatus.OPEN):
                raise InvalidTransitionError(
                    'NULL', new_status.value, trade_id
                )
            return

        allowed = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            raise InvalidTransitionError(
                old_status.value, new_status.value, trade_id
            )

    def _log_transition(self, trade, from_status, to_status, trigger, metadata=None):
        """Write a StateTransition audit record."""
        transition = StateTransition(
            trade_id=trade.id,
            from_status=from_status,
            to_status=to_status,
            trigger=trigger,
            metadata_json=metadata or {},
        )
        self.db.add(transition)
        logger.debug(
            f"StateTransition: trade {trade.id} "
            f"{from_status} → {to_status} via {trigger}"
        )
