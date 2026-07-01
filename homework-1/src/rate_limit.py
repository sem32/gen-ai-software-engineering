"""Simple in-memory, per-IP sliding-window rate limiter (Task 4 Option D).

Defaults to 100 requests per 60 seconds per client IP and returns HTTP 429 when
the limit is exceeded. Limits are configurable via the ``RATE_LIMIT_MAX`` and
``RATE_LIMIT_WINDOW`` environment variables (read at startup) so tests can dial
the limit down without waiting a real minute.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class RateLimiter:
    """Tracks request timestamps per client key within a rolling window."""

    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limiter: RateLimiter) -> None:
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not self.limiter.allow(client_ip):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": (
                        f"Rate limit exceeded: max {self.limiter.max_requests} "
                        f"requests per {int(self.limiter.window_seconds)}s."
                    ),
                },
            )
        return await call_next(request)
