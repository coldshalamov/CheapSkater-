"""Utility helpers for normalising scraped text values."""

from __future__ import annotations


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


__all__ = ["normalize_availability"]
