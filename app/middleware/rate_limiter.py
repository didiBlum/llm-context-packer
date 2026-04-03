"""Simple in-memory sliding window rate limiter per RapidAPI user."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Max requests per user per minute
MAX_REQUESTS_PER_MINUTE = 100


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_rpm: int = MAX_REQUESTS_PER_MINUTE):
        super().__init__(app)
        self.max_rpm = max_rpm
        # user_key -> list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/health"):
            return await call_next(request)

        user_key = request.headers.get("X-RapidAPI-User", request.client.host if request.client else "unknown")
        now = time.time()
        window_start = now - 60

        # Clean old entries
        timestamps = self._requests[user_key]
        self._requests[user_key] = [t for t in timestamps if t > window_start]

        if len(self._requests[user_key]) >= self.max_rpm:
            return JSONResponse(
                status_code=429,
                content={
                    "type": "https://context-packer.dev/errors/rate-limited",
                    "title": "Rate Limited",
                    "status": 429,
                    "detail": f"Max {self.max_rpm} requests per minute. Try again shortly.",
                },
                headers={"Retry-After": "60"},
            )

        self._requests[user_key].append(now)
        return await call_next(request)
