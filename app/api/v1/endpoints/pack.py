"""POST /v1/pack — core endpoint."""

import time
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.v1.schemas import PackRequest, PackResponse, PackResultItem
from app.pipeline.orchestrator import pack_single, pack_multi, PackedResult
from app.cache.store import cache
from app.dependencies import get_tier, enforce_tier_limits

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/pack", response_model=PackResponse)
async def pack(req: PackRequest, request: Request):
    start = time.perf_counter()
    urls = [str(u) for u in req.urls]

    # Tier enforcement
    tier = get_tier(request)
    enforce_tier_limits(tier, len(urls), req.max_tokens)

    try:
        if len(urls) == 1:
            results = [await _pack_with_cache(
                urls[0], req.format, req.model, req.priority, req.max_tokens
            )]
        else:
            results = await _pack_multi_with_cache(
                urls, req.format, req.model, req.priority, req.max_tokens
            )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    elapsed_ms = round((time.perf_counter() - start) * 1000)

    total_tokens = sum(r.token_count for r in results)
    total_saved = sum(r.tokens_saved for r in results)
    budget_remaining = (req.max_tokens - total_tokens) if req.max_tokens else None

    response = PackResponse(
        results=[_to_item(r) for r in results],
        total_token_count=total_tokens,
        total_tokens_saved=total_saved,
        budget_remaining=budget_remaining,
        processing_time_ms=elapsed_ms,
    )

    json_response = JSONResponse(content=response.model_dump())
    json_response.headers["X-Tokens-Used"] = str(total_tokens)
    json_response.headers["X-Tokens-Saved"] = str(total_saved)
    if total_saved + total_tokens > 0:
        ratio = round(total_saved / (total_saved + total_tokens), 2)
        json_response.headers["X-Compression-Ratio"] = str(ratio)

    return json_response


async def _pack_with_cache(
    url: str, fmt: str, model: str, priority: str, max_tokens: int | None
) -> PackedResult:
    """Pack a single URL with cache lookup."""
    # Cache key doesn't include max_tokens — we cache the full result
    # and apply budget later
    cached = await cache.get(url, fmt, model, priority)
    if cached is not None:
        cached.cached = True
        return cached

    result = await pack_single(url, fmt, model, priority, max_tokens)
    await cache.set(url, fmt, model, priority, result)
    return result


async def _pack_multi_with_cache(
    urls: list[str], fmt: str, model: str, priority: str, max_tokens: int | None
) -> list[PackedResult]:
    """Pack multiple URLs, checking cache for each."""
    results: list[PackedResult] = []
    uncached_urls: list[str] = []
    uncached_indices: list[int] = []

    # Check cache for each URL
    for i, url in enumerate(urls):
        cached = await cache.get(url, fmt, model, priority)
        if cached is not None:
            cached.cached = True
            results.append(cached)
        else:
            results.append(None)  # type: ignore
            uncached_urls.append(url)
            uncached_indices.append(i)

    # Fetch uncached URLs
    if uncached_urls:
        packed = await pack_multi(uncached_urls, fmt, model, priority, max_tokens)
        for idx, result in zip(uncached_indices, packed):
            results[idx] = result
            await cache.set(urls[idx], fmt, model, priority, result)

    return results


def _to_item(r: PackedResult) -> PackResultItem:
    return PackResultItem(
        url=r.url,
        title=r.title,
        content=r.content,
        format=r.format,
        token_count=r.token_count,
        original_token_count=r.original_token_count,
        tokens_saved=r.tokens_saved,
        compression_ratio=r.compression_ratio,
        fetch_method=r.fetch_method,
        cached=r.cached,
        warnings=r.warnings,
    )
