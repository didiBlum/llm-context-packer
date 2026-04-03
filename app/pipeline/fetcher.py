"""Fetch web content: httpx primary, Playwright fallback for JS-heavy pages."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_JS_MARKERS = [
    b'<div id="root"></div>',
    b'<div id="__next"></div>',
    b'<div id="app"></div>',
    b"__NEXT_DATA__",
    b"window.__remixContext",
]

_USER_AGENT = "LLMContextPacker/1.0 (semantic-indexer; +https://context-packer.dev)"

# Playwright: one page at a time, reuse browser across requests
_pw_semaphore = asyncio.Semaphore(1)
_pw_instance = None  # playwright context manager
_pw_browser = None    # reusable browser

_RSS_LIMIT_MB = 400


@dataclass
class FetchResult:
    html: str
    content_type: str
    url: str
    method: str
    status_code: int
    raw_bytes: bytes | None = None  # set for binary content (PDF)


async def fetch_url(url: str, use_playwright: bool = False) -> FetchResult:
    """Fetch a URL. Tries httpx first, falls back to Playwright if needed."""
    if use_playwright:
        return await _fetch_playwright(url)

    result = await _fetch_httpx(url)

    # Auto-detect JS shells that need rendering
    if result.html and len(result.html.strip()) < 2000:
        body_bytes = result.html.encode("utf-8", errors="ignore")
        if any(marker in body_bytes for marker in _JS_MARKERS):
            logger.info("JS shell detected for %s, falling back to Playwright", url)
            return await _fetch_playwright(url)

    return result


async def _fetch_httpx(url: str) -> FetchResult:
    """Fast path: plain HTTP fetch."""
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.fetch_timeout_seconds),
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        response = await client.get(url)
        content_type = response.headers.get("content-type", "")

        if not _is_text_content(content_type) and "pdf" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")

        if len(response.content) > settings.max_response_bytes:
            raise ValueError(
                f"Response too large: {len(response.content)} bytes "
                f"(max {settings.max_response_bytes})"
            )

        is_pdf = "pdf" in content_type or url.lower().endswith(".pdf")
        return FetchResult(
            html="" if is_pdf else response.text,
            content_type=content_type,
            url=str(response.url),
            method="httpx",
            status_code=response.status_code,
            raw_bytes=response.content if is_pdf else None,
        )


async def _get_browser():
    """Get or create a reusable Playwright browser instance."""
    global _pw_instance, _pw_browser

    # Memory guard: if RSS is too high, kill and recreate
    if _pw_browser and _get_rss_mb() > _RSS_LIMIT_MB:
        logger.warning("RSS %.0fMB exceeds limit, recycling browser", _get_rss_mb())
        await _shutdown_playwright()

    if _pw_browser is None:
        from playwright.async_api import async_playwright
        _pw_instance = await async_playwright().start()
        _pw_browser = await _pw_instance.chromium.launch(
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
        )
        logger.info("Playwright browser started")

    return _pw_browser


async def _shutdown_playwright():
    """Cleanly shut down browser and playwright."""
    global _pw_instance, _pw_browser
    try:
        if _pw_browser:
            await _pw_browser.close()
        if _pw_instance:
            await _pw_instance.stop()
    except Exception:
        pass
    _pw_browser = None
    _pw_instance = None


async def _fetch_playwright(url: str) -> FetchResult:
    """Slow path: headless browser for JS-rendered pages."""
    async with _pw_semaphore:
        browser = await _get_browser()
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            java_script_enabled=True,
        )
        try:
            page = await context.new_page()

            # Block heavy resources to save CPU/RAM
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2,ttf,eot,css}",
                lambda route: route.abort(),
            )

            response = await page.goto(url, wait_until="networkidle", timeout=15000)
            html = await page.content()
            final_url = page.url
            status = response.status if response else 200

            return FetchResult(
                html=html,
                content_type="text/html",
                url=final_url,
                method="playwright",
                status_code=status,
            )
        finally:
            await context.close()


def _get_rss_mb() -> float:
    """Get current process RSS in MB (macOS/Linux)."""
    try:
        import resource
        # resource.getrusage returns RSS in bytes on Linux, KB on macOS
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        rss_kb = rusage.ru_maxrss
        # macOS returns bytes, Linux returns KB
        if os.uname().sysname == "Darwin":
            return rss_kb / (1024 * 1024)
        return rss_kb / 1024
    except Exception:
        return 0


def _is_text_content(content_type: str) -> bool:
    text_types = ["text/", "application/json", "application/xml", "application/xhtml"]
    return any(t in content_type for t in text_types)
