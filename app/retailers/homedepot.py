"""Home Depot retailer scraping interface (not yet implemented)."""

from __future__ import annotations

from typing import Any


async def set_store_context(page: Any, zip_code: str) -> tuple[str | None, str | None]:
    """Set the Home Depot store context for the given ZIP code."""
    raise NotImplementedError("Home Depot store context is not implemented yet.")


async def scrape_category(page: Any, url: str, category_name: str, zip_code: str) -> list[dict]:
    """Scrape a Home Depot category page for the specified ZIP code."""
    raise NotImplementedError("Home Depot category scraping is not implemented yet.")


async def run_for_zip(playwright: Any, zip_code: str, categories: list[dict]) -> list[dict]:
    """Execute scraping workflow for a single ZIP code."""
    raise NotImplementedError("Home Depot scraping workflow is not implemented yet.")
