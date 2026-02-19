"""
Fernet Encryption for Broker Tokens
====================================
Point 9: Symmetric encryption for Tradier API tokens stored in the database.

The ENCRYPTION_KEY env var must be set. Generate with:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_KEY = os.getenv('ENCRYPTION_KEY')
_cipher = None


def _get_cipher() -> Fernet:
    """Lazy-init the Fernet cipher from ENCRYPTION_KEY env var."""
    global _cipher, _KEY
    if _cipher is None:
        _KEY = os.getenv('ENCRYPTION_KEY')
        if not _KEY:
            raise RuntimeError(
                "ENCRYPTION_KEY environment variable is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _cipher = Fernet(_KEY.encode())
    return _cipher


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string (e.g. Tradier API token).

    Returns a base64-encoded ciphertext string suitable for database storage.
    """
    if not plaintext:
        return None
    cipher = _get_cipher()
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string back to plaintext.

    Raises RuntimeError if the ciphertext is invalid or the key has changed.
    """
    if not ciphertext:
        return None
    cipher = _get_cipher()
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt token — ENCRYPTION_KEY may have changed or data is corrupt")
        raise RuntimeError(
            "Failed to decrypt broker token. The encryption key may have been rotated. "
            "Re-enter your broker credentials."
        )
