"""Central orchestrator: fetch → clean → compress → tokenize → budget."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.pipeline.fetcher import fetch_url, FetchResult
from app.pipeline.cleaner import clean_html, CleanResult
from app.pipeline.compressor import compress
from app.pipeline.tokenizer import count_tokens
from app.pipeline.format_negotiator import fit_to_budget, allocate_budgets, BudgetResult
from app.pipeline.pdf_extractor import extract_pdf_to_markdown

logger = logging.getLogger(__name__)


@dataclass
class PackedResult:
    url: str
    title: str
    content: str
    format: str
    token_count: int
    original_token_count: int
    tokens_saved: int
    compression_ratio: float
    fetch_method: str
    cached: bool
    warnings: list[str]


async def pack_single(
    url: str,
    fmt: str = "markdown",
    model: str = "gpt-4o",
    priority: str = "quality",
    max_tokens: int | None = None,
    use_playwright: bool = False,
) -> PackedResult:
    """Full pipeline for a single URL."""
    warnings: list[str] = []

    # 1. Fetch
    try:
        fetch_result = await fetch_url(url, use_playwright=use_playwright)
    except Exception as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

    if fetch_result.status_code >= 400:
        warnings.append(f"HTTP {fetch_result.status_code} — content may be incomplete")

    # 2. Clean: PDF vs HTML
    is_pdf = "pdf" in fetch_result.content_type or url.lower().endswith(".pdf")
    if is_pdf and fetch_result.raw_bytes:
        markdown = extract_pdf_to_markdown(fetch_result.raw_bytes)
        clean_result = CleanResult(markdown=markdown, title="", description="")
        warnings.append("Extracted from PDF")
    else:
        clean_result = clean_html(fetch_result.html)

    # Count original tokens (after cleaning, before compression)
    original_tokens = count_tokens(clean_result.markdown, model)

    # 3. Compress
    compressed = compress(clean_result.markdown, priority)

    # 4. Format output
    if fmt == "json":
        import json
        content = json.dumps({
            "title": clean_result.title,
            "content": compressed,
            "url": url,
        }, ensure_ascii=False)
    elif fmt == "plain":
        # Strip markdown formatting
        content = _markdown_to_plain(compressed)
    else:
        content = compressed

    # 5. Fit to budget if needed
    budget_result = fit_to_budget(content, max_tokens, model, priority)
    if budget_result.was_truncated:
        warnings.append("Content was truncated to fit token budget")

    # Calculate savings
    final_tokens = budget_result.token_count
    raw_html_tokens = count_tokens(fetch_result.html, model)
    tokens_saved = raw_html_tokens - final_tokens
    compression_ratio = round(1 - (final_tokens / raw_html_tokens), 4) if raw_html_tokens > 0 else 0

    return PackedResult(
        url=url,
        title=clean_result.title,
        content=budget_result.content,
        format=fmt,
        token_count=final_tokens,
        original_token_count=raw_html_tokens,
        tokens_saved=tokens_saved,
        compression_ratio=compression_ratio,
        fetch_method=fetch_result.method,
        cached=False,
        warnings=warnings,
    )


async def pack_multi(
    urls: list[str],
    fmt: str = "markdown",
    model: str = "gpt-4o",
    priority: str = "quality",
    max_tokens: int | None = None,
    use_playwright: bool = False,
) -> list[PackedResult]:
    """Pack multiple URLs, optionally within a shared token budget."""
    if max_tokens is None:
        # No budget — pack each independently in parallel
        tasks = [
            pack_single(url, fmt, model, priority, None, use_playwright)
            for url in urls
        ]
        return await asyncio.gather(*tasks)

    # With budget: first pack without budget to get sizes, then allocate
    tasks = [
        pack_single(url, fmt, model, priority, None, use_playwright)
        for url in urls
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separate successes from errors
    packed: list[tuple[int, PackedResult]] = []
    errors: list[tuple[int, Exception]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            errors.append((i, r))
        else:
            packed.append((i, r))

    # Allocate budget
    token_counts = [r.token_count for _, r in packed]
    budgets = allocate_budgets(token_counts, max_tokens)

    # Re-fit each to its allocated budget
    final_results: list[PackedResult] = [None] * len(urls)  # type: ignore

    for j, (orig_idx, result) in enumerate(packed):
        budget = budgets[j]
        if budget is not None:
            budget_result = fit_to_budget(result.content, budget, model, priority)
            result.content = budget_result.content
            result.token_count = budget_result.token_count
            result.tokens_saved = result.original_token_count - result.token_count
            if result.original_token_count > 0:
                result.compression_ratio = round(
                    1 - (result.token_count / result.original_token_count), 4
                )
            if budget_result.was_truncated:
                result.warnings.append("Truncated to fit shared budget")

        final_results[orig_idx] = result

    # Handle errors
    for orig_idx, exc in errors:
        final_results[orig_idx] = PackedResult(
            url=urls[orig_idx],
            title="",
            content="",
            format=fmt,
            token_count=0,
            original_token_count=0,
            tokens_saved=0,
            compression_ratio=0,
            fetch_method="error",
            cached=False,
            warnings=[f"Fetch failed: {exc}"],
        )

    return final_results


def _markdown_to_plain(md: str) -> str:
    """Simple markdown stripping for plain text output."""
    import re
    text = md
    # Remove headings markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Remove inline code backticks (keep content)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Remove link syntax, keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text
