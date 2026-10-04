"""
In-memory per-IP rate limiter for BlindSpot AI.

Uses a simple sliding window algorithm. State is stored in a module-level
dict, which is appropriate for a single-process deployment on Cloud Run.
For multi-instance deployments, a shared store (e.g., Redis) would be needed.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock


class RateLimiter:
    """
    Per-IP sliding-window rate limiter.

    Attributes:
        max_requests: Maximum allowed requests per window.
        window_seconds: Duration of the sliding window in seconds.
    """

    def __init__(self, max_requests: int = 20, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()

    def is_allowed(self, ip: str) -> bool:
        """
        Check whether the given IP is within its rate limit.

        Removes timestamps outside the current window, then checks the count.

        Args:
            ip: Client IP address string.

        Returns:
            True if the request should be allowed, False if rate-limited.
        """
        now = time.monotonic()
        with self._lock:
            if ip not in self._requests:
                self._requests[ip] = deque()
            window = self._requests[ip]

            # Remove expired timestamps
            cutoff = now - self.window_seconds
            while window and window[0] <= cutoff:
                window.popleft()

            if len(window) >= self.max_requests:
                return False

            window.append(now)
            return True

    def reset(self, ip: str) -> None:
        """
        Clear all recorded requests for an IP (useful in tests).

        Args:
            ip: Client IP address to reset.
        """
        with self._lock:
            self._requests.pop(ip, None)


# Singleton limiter used by the FastAPI app
_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    """Return the application-wide rate limiter, initialising it if needed."""
    global _limiter
    if _limiter is None:
        from backend.app.config import get_settings

        settings = get_settings()
        _limiter = RateLimiter(max_requests=settings.rate_limit_rpm)
    return _limiter
