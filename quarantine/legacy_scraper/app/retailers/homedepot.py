"""Home Depot retailer scraping interface mirroring the Lowe's workflow."""

from __future__ import annotations

from typing import Any


async def set_store_context(page: Any, zip_code: str) -> tuple[str | None, str | None]:
    """Set the Lowe's store context for the given ZIP code."""

    # The Lowe's implementation opens the store context modal and submits the ZIP
    # using shared selectors; Home Depot will follow the same pattern once built.
    raise NotImplementedError("Home Depot store context flow not implemented yet.")


async def scrape_category(page: Any, url: str, category_name: str, zip_code: str) -> list[dict]:
    """Scrape a Lowe's category page for the specified ZIP code."""

    # This will eventually reuse app.selectors, paginate_or_scroll, and extract the
    # same product fields that Lowe's currently gathers from each result card.
    raise NotImplementedError("Home Depot category scraping is not implemented yet.")


async def run_for_zip(playwright: Any, zip_code: str, categories: list[dict]) -> list[dict]:
    """Execute scraping workflow for a single ZIP code."""

    # The orchestrator will replicate the Lowe's flow: set store context, iterate
    # categories, and consolidate identical observation payloads for downstream use.
    raise NotImplementedError("Home Depot ZIP workflow is not implemented yet.")
