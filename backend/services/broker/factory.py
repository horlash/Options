"""
Broker Factory — The "Switch"
==============================
Point 9: Creates the appropriate BrokerProvider instance based on
the user's settings. Handles token decryption and environment selection.
"""

import logging
from backend.services.broker.base import BrokerProvider
from backend.services.broker.tradier import TradierBroker
from backend.services.broker.exceptions import BrokerException
from backend.security.crypto import decrypt

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Factory that creates the correct broker instance for a user.

    Usage:
        user_settings = db.query(UserSettings).filter_by(username='alice').first()
        broker = BrokerFactory.get_broker(user_settings)
        quotes = broker.get_quotes(['AAPL'])
    """

    @staticmethod
    def get_broker(user_settings) -> BrokerProvider:
        """Create a TradierBroker from the user's stored settings.

        Args:
            user_settings: A UserSettings model instance with
                broker_mode, tradier_sandbox_token, tradier_live_token,
                tradier_account_id

        Returns:
            A configured TradierBroker instance

        Raises:
            BrokerException: If credentials are missing or invalid
        """
        mode = (user_settings.broker_mode or 'TRADIER_SANDBOX').upper()

        if mode in ('LIVE', 'TRADIER_LIVE'):
            encrypted_token = user_settings.tradier_live_token
            is_live = True
            if not encrypted_token:
                raise BrokerException(
                    "Live trading token not configured. "
                    "Go to Settings → Broker → enter your Live API token."
                )
        else:
            encrypted_token = user_settings.tradier_sandbox_token
            is_live = False
            if not encrypted_token:
                raise BrokerException(
                    "Sandbox token not configured. "
                    "Go to Settings → Broker → enter your Sandbox API token."
                )

        if not user_settings.tradier_account_id:
            raise BrokerException(
                "Tradier account ID not configured. "
                "Go to Settings → Broker → enter your Account Number."
            )

        # Decrypt the stored token
        try:
            token = decrypt(encrypted_token)
        except RuntimeError as e:
            raise BrokerException(
                f"Failed to decrypt broker token: {e}. "
                f"Re-enter your credentials in Settings."
            )

        logger.info(
            f"BrokerFactory: creating TradierBroker "
            f"(mode={mode}, account={user_settings.tradier_account_id})"
        )

        return TradierBroker(
            access_token=token,
            account_id=user_settings.tradier_account_id,
            is_live=is_live,
        )

    @staticmethod
    def get_broker_direct(token: str, account_id: str, is_live: bool = False) -> BrokerProvider:
        """Create a TradierBroker directly from plaintext credentials.

        Used for testing and initial setup — bypasses encryption.
        """
        return TradierBroker(
            access_token=token,
            account_id=account_id,
            is_live=is_live,
        )
