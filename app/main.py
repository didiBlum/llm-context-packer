import time
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.api.v1.router import router as v1_router
from app.middleware.rapidapi_auth import RapidAPIAuthMiddleware

logging.basicConfig(level=getattr(logging, settings.log_level.upper()))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LLM Context Packer",
    version="1.0.0",
    description="Compress web content into token-optimized markdown for LLMs",
    docs_url="/docs" if settings.env == "development" else None,
    redoc_url=None,
)

# Auth middleware (skip in dev for easier testing)
if settings.env != "development":
    app.add_middleware(RapidAPIAuthMiddleware)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    response.headers["X-Processing-Time-Ms"] = str(elapsed_ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://context-packer.dev/errors/internal",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred.",
        },
    )


app.include_router(v1_router, prefix="/v1")
