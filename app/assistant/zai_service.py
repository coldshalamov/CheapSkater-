"""z.ai (Grok) API integration for AI-powered deal summaries."""

from __future__ import annotations

import os
import json
import time
import hashlib
from datetime import datetime, timezone
from typing import Any

import httpx

from app.logging_config import get_logger

LOGGER = get_logger(__name__)

# Configuration
ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
ZAI_API_BASE = os.getenv("ZAI_API_BASE", "https://api.x.ai/v1")
ZAI_MODEL = os.getenv("ZAI_MODEL", "grok-3-mini")

# Simple in-memory cache
_summary_cache: dict[str, tuple[str, float]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def is_zai_configured() -> bool:
    """Check if z.ai API is configured."""
    return bool(ZAI_API_KEY)


def _cache_key(deals: list[dict[str, Any]]) -> str:
    """Generate a cache key from deals data."""
    # Use date + deal count + first few SKUs for cache key
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    skus = sorted([d.get("sku", "") for d in deals[:20]])
    key_data = f"{today}:{len(deals)}:{':'.join(skus[:5])}"
    return hashlib.md5(key_data.encode()).hexdigest()


def _get_cached_summary(cache_key: str) -> str | None:
    """Get cached summary if still valid."""
    if cache_key in _summary_cache:
        summary, cached_at = _summary_cache[cache_key]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            LOGGER.debug("Cache hit for summary key=%s", cache_key[:8])
            return summary
        # Expired - remove from cache
        del _summary_cache[cache_key]
    return None


def _cache_summary(cache_key: str, summary: str) -> None:
    """Cache a summary."""
    _summary_cache[cache_key] = (summary, time.time())
    # Simple cache cleanup - keep max 10 entries
    if len(_summary_cache) > 10:
        oldest_key = min(_summary_cache, key=lambda k: _summary_cache[k][1])
        del _summary_cache[oldest_key]


def _format_deals_for_prompt(deals: list[dict[str, Any]], max_deals: int = 30) -> str:
    """Format deals into a compact string for the AI prompt."""
    lines = []
    for deal in deals[:max_deals]:
        title = deal.get("title", "Unknown")[:60]
        price = deal.get("price", 0)
        was_price = deal.get("price_was", 0)
        pct_off = deal.get("pct_off", 0)
        if pct_off < 1:
            pct_off = pct_off * 100
        category = deal.get("category", "Other")[:30]
        store = deal.get("store_name", deal.get("store_label", ""))[:30]
        state = deal.get("store_state", "")

        lines.append(
            f"- {title} | ${price:.2f} (was ${was_price:.2f}, {pct_off:.0f}% off) | {category} | {store} {state}"
        )

    return "\n".join(lines)


def _build_summary_prompt(deals: list[dict[str, Any]], region: str = "all") -> str:
    """Build the prompt for deal summarization."""
    deals_text = _format_deals_for_prompt(deals)
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    region_context = ""
    if region == "WA_OR":
        region_context = " in the Pacific Northwest (Washington and Oregon)"
    elif region == "FL":
        region_context = " in Florida"

    prompt = f"""You are a helpful deal-hunting assistant for GloorBot, a Lowe's clearance deal tracker.
Summarize today's best clearance deals{region_context} for {today}.

Here are the top deals found today:
{deals_text}

Write a brief, engaging summary (2-3 short paragraphs) highlighting:
1. The best overall deals (highest discounts or most valuable items)
2. Notable categories with good finds
3. Any standout items worth mentioning

Be conversational and helpful. Focus on the deals that offer the best value. Don't list every item - highlight the gems.
Keep it concise - this will be shown at the top of a deals page."""

    return prompt


class ZAIService:
    """Service for interacting with the z.ai (Grok) API."""

    def __init__(self):
        if not is_zai_configured():
            raise ValueError("z.ai API key not configured. Set ZAI_API_KEY environment variable.")
        self.client = httpx.Client(
            base_url=ZAI_API_BASE,
            headers={
                "Authorization": f"Bearer {ZAI_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def generate_completion(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate a completion using the z.ai API."""
        try:
            response = self.client.post(
                "/chat/completions",
                json={
                    "model": ZAI_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract the completion text
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
            return ""

        except httpx.HTTPStatusError as e:
            LOGGER.error("z.ai API error: status=%s body=%s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            LOGGER.error("z.ai API error: %s", e)
            raise

    def close(self):
        """Close the HTTP client."""
        self.client.close()


def generate_deal_summary(
    deals: list[dict[str, Any]],
    region: str = "all",
    use_cache: bool = True,
) -> str:
    """
    Generate an AI summary of today's deals.

    Args:
        deals: List of deal dictionaries
        region: Region context (all, WA_OR, FL)
        use_cache: Whether to use caching

    Returns:
        AI-generated summary string, or fallback message if API fails
    """
    if not deals:
        return "No new deals found today. Check back later!"

    if not is_zai_configured():
        return _generate_fallback_summary(deals, region)

    # Check cache
    cache_key = _cache_key(deals)
    if use_cache:
        cached = _get_cached_summary(cache_key)
        if cached:
            return cached

    try:
        service = ZAIService()
        prompt = _build_summary_prompt(deals, region)
        summary = service.generate_completion(prompt)
        service.close()

        if summary:
            if use_cache:
                _cache_summary(cache_key, summary)
            return summary

        return _generate_fallback_summary(deals, region)

    except Exception as e:
        LOGGER.warning("Failed to generate AI summary: %s", e)
        return _generate_fallback_summary(deals, region)


def _generate_fallback_summary(deals: list[dict[str, Any]], region: str = "all") -> str:
    """Generate a simple fallback summary when AI is unavailable."""
    if not deals:
        return "No deals available at this time."

    # Calculate some basic stats
    total_deals = len(deals)

    # Find best discount
    best_deal = max(deals, key=lambda d: d.get("pct_off", 0) or 0, default=None)

    # Count categories
    categories = {}
    for deal in deals:
        cat = deal.get("category", "Other")
        categories[cat] = categories.get(cat, 0) + 1
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]

    region_text = ""
    if region == "WA_OR":
        region_text = " in the Pacific Northwest"
    elif region == "FL":
        region_text = " in Florida"

    summary = f"Found **{total_deals} clearance deals**{region_text} today!\n\n"

    if best_deal:
        pct = best_deal.get("pct_off", 0)
        if pct < 1:
            pct = pct * 100
        title = best_deal.get("title", "Unknown")[:50]
        price = best_deal.get("price", 0)
        summary += f"**Top Deal:** {title} at **${price:.2f}** ({pct:.0f}% off)\n\n"

    if top_categories:
        cat_text = ", ".join([f"{cat} ({count})" for cat, count in top_categories])
        summary += f"**Popular Categories:** {cat_text}"

    return summary
