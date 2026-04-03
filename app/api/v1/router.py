from fastapi import APIRouter

from app.api.v1.endpoints import pack, inspect, health

router = APIRouter()
router.include_router(pack.router, tags=["pack"])
router.include_router(inspect.router, tags=["inspect"])
router.include_router(health.router, tags=["health"])
