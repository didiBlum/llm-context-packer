"""In-memory TTL cache for packed results. No Redis needed."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from cachetools import TTLCache

from app.config import settings


class PackCache:
    def __init__(
        self,
        maxsize: int = settings.cache_max_size,
        ttl: int = settings.cache_ttl_seconds,
    ):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(url: str, fmt: str, model: str, priority: str) -> str:
        raw = f"{url}|{fmt}|{model}|{priority}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def get(
        self, url: str, fmt: str, model: str, priority: str
    ) -> Any | None:
        async with self._lock:
            return self._cache.get(self._key(url, fmt, model, priority))

    async def set(
        self, url: str, fmt: str, model: str, priority: str, result: Any
    ) -> None:
        async with self._lock:
            self._cache[self._key(url, fmt, model, priority)] = result

    @property
    def size(self) -> int:
        return len(self._cache)


# Singleton
cache = PackCache()
