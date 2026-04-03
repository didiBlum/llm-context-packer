"""POST /v1/inspect — cheap token count without full compression."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.api.v1.schemas import InspectRequest, InspectResponse, InspectResultItem
from app.pipeline.fetcher import fetch_url
from app.pipeline.cleaner import clean_html
from app.pipeline.tokenizer import count_tokens

logger = logging.getLogger(__name__)
router = APIRouter()

# Average compression ratios from benchmarks (conservative estimates)
_AVG_CLEAN_RATIO = 0.70  # cleaning removes ~70% of tokens
_AVG_COMPRESS_RATIO = 0.15  # compression removes another ~15%
_TOTAL_ESTIMATED_RATIO = 1 - (1 - _AVG_CLEAN_RATIO) * (1 - _AVG_COMPRESS_RATIO)


@router.post("/inspect", response_model=InspectResponse)
async def inspect(req: InspectRequest):
    urls = [str(u) for u in req.urls]

    async def _inspect_one(url: str) -> InspectResultItem:
        try:
            fetch_result = await fetch_url(url)
            clean_result = clean_html(fetch_result.html)
            raw_tokens = count_tokens(fetch_result.html, req.model)
            clean_tokens = count_tokens(clean_result.markdown, req.model)

            # Estimate compressed tokens based on clean tokens
            estimated = int(clean_tokens * (1 - _AVG_COMPRESS_RATIO))
            estimated_ratio = round(1 - (estimated / raw_tokens), 4) if raw_tokens > 0 else 0

            return InspectResultItem(
                url=url,
                title=clean_result.title,
                raw_token_count=raw_tokens,
                estimated_packed_tokens=estimated,
                estimated_compression_ratio=estimated_ratio,
                content_type=fetch_result.content_type,
            )
        except Exception as e:
            return InspectResultItem(
                url=url,
                raw_token_count=0,
                estimated_packed_tokens=0,
                estimated_compression_ratio=0,
                content_type=f"error: {e}",
            )

    results = await asyncio.gather(*[_inspect_one(u) for u in urls])
    return InspectResponse(results=list(results))
