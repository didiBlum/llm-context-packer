"""RapidAPI proxy secret validation middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings


class RapidAPIAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip auth for health check
        if request.url.path.endswith("/health"):
            return await call_next(request)

        secret = request.headers.get("X-RapidAPI-Proxy-Secret", "")
        if not settings.rapidapi_proxy_secret:
            # No secret configured — allow all (dev mode)
            return await call_next(request)

        if secret != settings.rapidapi_proxy_secret:
            return JSONResponse(
                status_code=403,
                content={
                    "type": "https://context-packer.dev/errors/unauthorized",
                    "title": "Unauthorized",
                    "status": 403,
                    "detail": "Invalid or missing X-RapidAPI-Proxy-Secret header.",
                },
            )

        return await call_next(request)
