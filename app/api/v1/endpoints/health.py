import time

from fastapi import APIRouter

from app.api.v1.schemas import HealthResponse
from app.cache.store import cache

router = APIRouter()

_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        cache_entries=cache.size,
        uptime_seconds=round(time.time() - _start_time, 1),
    )
