"""Lowe's retailer scraping interface."""

from __future__ import annotations

from typing import Any


async def set_store_context(page: Any, zip_code: str) -> tuple[str | None, str | None]:
    """Set the Lowe's store context for the given ZIP code."""
    ...


async def scrape_category(page: Any, url: str, category_name: str, zip_code: str) -> list[dict]:
    """Scrape a Lowe's category page for the specified ZIP code."""
    ...


async def run_for_zip(playwright: Any, zip_code: str, categories: list[dict]) -> list[dict]:
    """Execute scraping workflow for a single ZIP code."""
    ...
