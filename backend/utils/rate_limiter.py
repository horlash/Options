"""
Rate Limiter
============
Point 9: Sliding-window rate limiter for Tradier API calls.
Uses the lower sandbox limit (50/min) as ceiling to be safe across environments.
"""

import time
import threading
from collections import deque


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    Default: 50 calls per 60 seconds (Tradier sandbox limit is 60/min,
    we use 50 for headroom).

    Usage:
        limiter = RateLimiter(max_calls=50, period=60)
        limiter.wait()  # blocks if limit reached
        response = requests.get(...)
        limiter.update_from_headers(response.headers)
    """

    def __init__(self, max_calls: int = 50, period: int = 60):
        self.max_calls = max_calls
        self.period = period
        self.timestamps = deque()
        self._lock = threading.Lock()

    def wait(self) -> float:
        """Block until a call can be made. Returns time waited (seconds)."""
        waited = 0.0
        with self._lock:
            now = time.time()

            # Evict expired timestamps
            while self.timestamps and now - self.timestamps[0] > self.period:
                self.timestamps.popleft()

            # If at limit, sleep until the oldest timestamp expires
            if len(self.timestamps) >= self.max_calls:
                sleep_time = self.period - (now - self.timestamps[0]) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    waited = sleep_time
                    # Re-evict after sleeping
                    now = time.time()
                    while self.timestamps and now - self.timestamps[0] > self.period:
                        self.timestamps.popleft()

            self.timestamps.append(time.time())
        return waited

    def update_from_headers(self, headers: dict):
        """Optionally update limits from Tradier response headers.

        Tradier sends:
            X-Ratelimit-Allowed: 120
            X-Ratelimit-Used: 15
            X-Ratelimit-Available: 105
            X-Ratelimit-Expiry: 1709856000 (Unix timestamp)

        We use these as a safety net — if Tradier says we're closer to the
        limit than our local counter thinks, we trust Tradier.
        """
        available = headers.get('X-Ratelimit-Available')
        if available is not None:
            available = int(available)
            if available <= 5:
                # Tradier says we're almost at the limit — pad our queue
                with self._lock:
                    while len(self.timestamps) < self.max_calls - available:
                        self.timestamps.append(time.time())

    @property
    def remaining(self) -> int:
        """How many calls are available right now."""
        with self._lock:
            now = time.time()
            while self.timestamps and now - self.timestamps[0] > self.period:
                self.timestamps.popleft()
            return max(0, self.max_calls - len(self.timestamps))
