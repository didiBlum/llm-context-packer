from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, HttpUrl, Field


# ── Requests ──────────────────────────────────────────────────────────────

class PackRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=10)
    max_tokens: int | None = Field(None, gt=0, le=128_000)
    format: Literal["markdown", "json", "plain"] = "markdown"
    model: str = "gpt-4o"
    priority: Literal["quality", "compression", "speed"] = "quality"


class InspectRequest(BaseModel):
    urls: list[HttpUrl] = Field(..., min_length=1, max_length=10)
    model: str = "gpt-4o"


# ── Responses ─────────────────────────────────────────────────────────────

class PackResultItem(BaseModel):
    url: str
    title: str = ""
    content: str
    format: str
    token_count: int
    original_token_count: int
    tokens_saved: int
    compression_ratio: float
    fetch_method: str = "httpx"
    cached: bool = False
    warnings: list[str] = []


class PackResponse(BaseModel):
    results: list[PackResultItem]
    total_token_count: int
    total_tokens_saved: int
    budget_remaining: int | None = None
    processing_time_ms: int


class InspectResultItem(BaseModel):
    url: str
    title: str = ""
    raw_token_count: int
    estimated_packed_tokens: int
    estimated_compression_ratio: float
    content_type: str = ""


class InspectResponse(BaseModel):
    results: list[InspectResultItem]


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    cache_entries: int
    uptime_seconds: float


class ErrorResponse(BaseModel):
    type: str
    title: str
    status: int
    detail: str
