"""Minimal CDP scraper to pull Back Aisle items from an already-open Chrome tab.

Usage (PowerShell):
    & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\\Temp\\ChromeProfile"
    # Open your Back Aisle URL in that Chrome window (store already set)
    $env:CHEAPSKATER_CDP_URL="http://127.0.0.1:9222"
    python scripts/cdp_back_aisle.py --url "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&inStock=1&storeNumber=1089"

Outputs JSON lines to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
from typing import Any
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright


async def _text_or_none(elem, selector: str) -> str | None:
    try:
        target = await elem.query_selector(selector)
        if not target:
            return None
        content = (await target.inner_text()).strip()
        return content or None
    except Exception:
        return None


async def _attr_or_none(elem, selector: str, attr: str) -> str | None:
    try:
        target = await elem.query_selector(selector)
        if not target:
            return None
        value = await target.get_attribute(attr)
        if value is None:
            return None
        value = value.strip()
        return value or None
    except Exception:
        return None


def _parse_price(raw: str | None) -> float | None:
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw if (ch.isdigit() or ch in {".", ","}))
    if not cleaned:
        return None
    try:
        return float(cleaned.replace(",", ""))
    except Exception:
        return None


def _store_from_url(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        store = qs.get("storeNumber")
        if store:
            return store[0]
    except Exception:
        return None
    return None


async def _human_pause(min_s: float = 2.0, max_s: float = 6.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def scrape_page(page, store_id: str | None, url: str) -> list[dict[str, Any]]:
    # Wait for product grid/cards.
    try:
        await page.wait_for_selector("div[data-itemid]", timeout=20000)
    except Exception:
        pass

    cards = await page.query_selector_all("div[data-itemid]")
    items: list[dict[str, Any]] = []
    for card in cards:
        sku = await card.get_attribute("data-itemid")
        title = await _text_or_none(card, '[data-testid="item-description"]') or await _text_or_none(
            card, 'a[data-testid="item-description-link"]'
        )
        price_text = await _text_or_none(card, '[data-testid="regular-price"]') or await _text_or_none(
            card, '[data-testid="current-price"]'
        )
        was_text = await _text_or_none(card, '[data-testid="was-price"]')
        price = _parse_price(price_text)
        price_was = _parse_price(was_text)
        link = await _attr_or_none(card, 'a[href][data-testid="item-description-link"]', "href") or await _attr_or_none(
            card, "a[href]", "href"
        )
        img = await _attr_or_none(card, "img", "src")
        avail = await _text_or_none(card, '[data-testid="fulfillment-availability"]')

        items.append(
            {
                "store_id": store_id,
                "url": url,
                "sku": sku,
                "title": title,
                "price": price,
                "price_was": price_was,
                "item_url": link,
                "image_url": img,
                "availability": avail,
            }
        )

    return items


async def scrape_all_pages(page, url: str, max_pages: int = 80) -> list[dict[str, Any]]:
    store_id = _store_from_url(url)
    results: list[dict[str, Any]] = []
    seen_skus: set[str] = set()
    stagnant = 0
    for _ in range(max_pages):
        page_items = await scrape_page(page, store_id, url)
        new_found = False
        for item in page_items:
            sku = (item.get("sku") or "").strip()
            if sku and sku in seen_skus:
                continue
            if sku:
                seen_skus.add(sku)
            results.append(item)
            new_found = True
        if not new_found:
            stagnant += 1
        else:
            stagnant = 0
        if stagnant >= 3:
            break
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        try:
            await page.wait_for_load_state("networkidle")
        except Exception:
            pass
        await _human_pause()

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Back Aisle page via CDP attach with pagination.")
    parser.add_argument("--url", required=True, help="Back Aisle URL with storeNumber and filters applied.")
    parser.add_argument("--max-pages", type=int, default=80, help="Max pages to paginate (default 80).")
    args = parser.parse_args()

    cdp = os.getenv("CHEAPSKATER_CDP_URL") or "http://127.0.0.1:9222"

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp)
        if browser.contexts and browser.contexts[0].pages:
            page = browser.contexts[0].pages[0]
        elif browser.contexts:
            page = await browser.contexts[0].new_page()
        else:
            page = await browser.new_page()

        await page.goto(args.url, wait_until="networkidle", timeout=60000)
        await _human_pause()
        items = await scrape_all_pages(page, args.url, max_pages=args.max_pages)
        for item in items:
            print(json.dumps(item, ensure_ascii=False))

        # Do not close the user's browser.


if __name__ == "__main__":
    asyncio.run(main())
