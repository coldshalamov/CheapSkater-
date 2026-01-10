"""Utility helpers for normalising scraped text values."""

from __future__ import annotations


def extract_category_name(category_url: str | None) -> str:
    """
    Convert a Lowe's /pl/ category URL into a user-friendly category name.

    Rules:
    - Strip query params and trailing slashes.
    - Split on "/pl/" then "/" to get segments.
    - Drop purely-numeric segments (including hyphenated numeric IDs).
    - Use the last remaining text segment as the most-specific category slug.
    - Convert kebab-case to Title Case.
    """

    if not category_url:
        return "Uncategorized"

    try:
        path = category_url.split("?", 1)[0].rstrip("/")
        if "/pl/" not in path:
            return "Uncategorized"

        tail = path.split("/pl/", 1)[-1]
        segments = [seg for seg in tail.split("/") if seg]
        text_segments = [seg for seg in segments if not seg.replace("-", "").isdigit()]
        if not text_segments:
            return "Uncategorized"

        slug = text_segments[-1]
        name = slug.replace("-", " ").strip()
        return name.title() if name else "Uncategorized"
    except Exception:
        return "Uncategorized"


def normalize_availability(value: str | None) -> str | None:
    """Convert schema.org availability URIs into human-readable labels."""

    if not value:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    lowered = trimmed.lower()
    if lowered.startswith("http://schema.org/"):
        trimmed = trimmed[len("http://schema.org/") :]
        lowered = trimmed.lower()
    elif lowered.startswith("https://schema.org/"):
        trimmed = trimmed[len("https://schema.org/") :]
        lowered = trimmed.lower()

    mapped = {
        "instock": "In Stock",
        "outofstock": "Out of Stock",
        "preorder": "Preorder",
        "soldout": "Sold Out",
        "limitedavailability": "Limited",
        "onlineonly": "Online Only",
    }

    if lowered in mapped:
        return mapped[lowered]

    if lowered in {"limited", "limited availability"}:
        return "Limited"

    return trimmed


__all__ = ["extract_category_name", "normalize_availability"]
