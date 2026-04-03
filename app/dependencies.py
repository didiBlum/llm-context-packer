"""FastAPI dependencies: tier enforcement, request validation."""

from __future__ import annotations

from fastapi import Request, HTTPException

from app.config import settings


def get_tier(request: Request) -> dict:
    """Extract and return the tier config from RapidAPI subscription header."""
    subscription = request.headers.get("X-RapidAPI-Subscription", "").upper()
    tier = settings.tiers.get(subscription, settings.tiers["default"])

    # In dev mode, use the most permissive tier
    if settings.env == "development":
        return settings.tiers["ULTRA"]

    return tier


def enforce_tier_limits(
    tier: dict,
    num_urls: int,
    max_tokens: int | None,
    needs_playwright: bool = False,
):
    """Raise HTTPException if the request exceeds tier limits."""
    if num_urls > tier["max_urls"]:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "https://context-packer.dev/errors/tier-limit",
                "title": "Tier Limit Exceeded",
                "status": 403,
                "detail": (
                    f"Your plan allows {tier['max_urls']} URLs per request. "
                    f"You sent {num_urls}. Upgrade for more."
                ),
            },
        )

    if max_tokens and max_tokens > tier["max_tokens"]:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "https://context-packer.dev/errors/tier-limit",
                "title": "Tier Limit Exceeded",
                "status": 403,
                "detail": (
                    f"Your plan allows max_tokens up to {tier['max_tokens']:,}. "
                    f"You requested {max_tokens:,}. Upgrade for more."
                ),
            },
        )

    if needs_playwright and not tier["playwright"]:
        raise HTTPException(
            status_code=403,
            detail={
                "type": "https://context-packer.dev/errors/tier-limit",
                "title": "Playwright Not Available",
                "status": 403,
                "detail": "JS rendering requires a paid plan. Upgrade to Basic or higher.",
            },
        )
