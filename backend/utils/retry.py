"""
P1-A7: Retry decorator for transient API failures.

Wraps external API calls (ORATS, Tradier, Finnhub) with exponential back-off
so a single network hiccup doesn't crash the scanner mid-run.

Usage:
    from backend.utils.retry import retry_api

    @retry_api(max_retries=3, base_delay=1.0)
    def get_quote(self, ticker):
        ...
"""

import time
import logging
import functools
import requests

logger = logging.getLogger(__name__)

# Exceptions that are safe to retry (transient / network)
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    ConnectionResetError,
    TimeoutError,
    OSError,  # Covers "Network is unreachable", etc.
)


def retry_api(max_retries=3, base_delay=1.0, backoff_factor=2.0):
    """Decorator: retry a function on transient network/API errors.

    Args:
        max_retries:    Number of retry attempts after the first failure.
        base_delay:     Initial delay in seconds before the first retry.
        backoff_factor: Multiplier applied to the delay after each retry
                        (exponential back-off).

    Retries on:
        - requests connection/timeout/chunked-encoding errors
        - ConnectionResetError, TimeoutError, OSError
        - HTTP 5xx responses (server errors) — detected via
          requests.Response.raise_for_status()

    Does NOT retry on:
        - HTTP 4xx (client errors like 401, 403, 404, 429)
        - ValueError, KeyError, or other programming bugs
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay

            for attempt in range(1 + max_retries):  # attempt 0 = first try
                try:
                    return func(*args, **kwargs)
                except RETRYABLE_EXCEPTIONS as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        logger.warning(
                            "%s attempt %d/%d failed (%s: %s) — retrying in %.1fs",
                            func.__qualname__,
                            attempt + 1,
                            1 + max_retries,
                            type(exc).__name__,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__qualname__,
                            1 + max_retries,
                            exc,
                        )
                except requests.exceptions.HTTPError as exc:
                    # Only retry 5xx server errors
                    if exc.response is not None and 500 <= exc.response.status_code < 600:
                        last_exception = exc
                        if attempt < max_retries:
                            logger.warning(
                                "%s attempt %d/%d got HTTP %d — retrying in %.1fs",
                                func.__qualname__,
                                attempt + 1,
                                1 + max_retries,
                                exc.response.status_code,
                                delay,
                            )
                            time.sleep(delay)
                            delay *= backoff_factor
                        else:
                            logger.error(
                                "%s failed after %d attempts: HTTP %d",
                                func.__qualname__,
                                1 + max_retries,
                                exc.response.status_code,
                            )
                    else:
                        # 4xx errors — don't retry, just re-raise
                        raise

            # All retries exhausted
            raise last_exception  # type: ignore[misc]

        return wrapper
    return decorator
