"""Lowe's retailer scraping interface."""

from __future__ import annotations

import re
from typing import Any

from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors.dom_utils import human_wait, inner_text_safe, paginate_or_scroll, price_to_float
from app.logging_config import get_logger
import app.selectors as selectors
from tenacity import retry, stop_after_attempt, wait_random_exponential

LOGGER = get_logger(__name__)


async def _safe_wait_for_load(page: Any, state: str) -> None:
    try:
        await page.wait_for_load_state(state)
    except Exception:
        return


async def _safe_click(locators: list[Any]) -> bool:
    for locator in locators:
        if locator is None:
            continue
        try:
            await locator.wait_for(state="visible", timeout=4000)
        except Exception:
            pass
        try:
            await locator.click()
            await human_wait(200, 500)
            return True
        except Exception:
            continue
    return False


async def _first_locator(locators: list[Any]) -> Any | None:
    for locator in locators:
        if locator is None:
            continue
        try:
            await locator.wait_for(state="visible", timeout=4000)
            return locator
        except Exception:
            continue
    return None


async def _safe_get_attribute(locator: Any, attribute: str) -> str | None:
    if locator is None:
        return None
    try:
        value = await locator.get_attribute(attribute)
    except Exception:
        return None
    if value is None:
        return None
    return value.strip() or None


async def _maybe_locator(root: Any, selector: str | None) -> Any | None:
    if not selector:
        return None
    try:
        return root.locator(selector)
    except Exception:
        return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.5, max=5),
    reraise=True,
)
async def set_store_context(page: Any, zip_code: str) -> tuple[str | None, str | None]:
    """Set the Lowe's store context for the given ZIP code."""

    await page.goto("https://www.lowes.com", wait_until="domcontentloaded")
    await _safe_wait_for_load(page, "networkidle")
    await human_wait(300, 700)

    entry_candidates: list[Any] = []
    if selectors.STORE_BADGE:
        entry_candidates.append(page.locator(selectors.STORE_BADGE))
    try:
        entry_candidates.append(page.get_by_role("button", name=re.compile("my store|change store|set store", re.I)))
    except Exception:
        pass
    try:
        entry_candidates.append(page.get_by_role("link", name=re.compile("my store|change store|set store", re.I)))
    except Exception:
        pass
    entry_candidates.append(page.locator("text=/Change Store/i"))
    entry_candidates.append(page.locator("text=/Set Store/i"))

    await _safe_click(entry_candidates)

    change_candidates: list[Any] = []
    try:
        change_candidates.append(page.get_by_role("button", name=re.compile("change store|update store", re.I)))
    except Exception:
        pass
    change_candidates.append(page.locator("text=/Change Store/i"))
    change_candidates.append(page.locator("text=/Update Store/i"))

    await _safe_click(change_candidates)

    zip_locators: list[Any] = []
    try:
        zip_locators.append(page.get_by_role("textbox", name=re.compile("zip", re.I)))
    except Exception:
        pass
    zip_locators.append(page.locator("input[name*='zip']"))
    zip_locators.append(page.locator("input[id*='zip']"))
    zip_locators.append(page.locator("input[placeholder*='zip']"))

    zip_input = await _first_locator(zip_locators)
    if zip_input is None:
        raise StoreContextError(zip_code=zip_code)

    try:
        await zip_input.click()
    except Exception:
        pass

    try:
        await zip_input.fill(zip_code)
    except Exception as exc:
        raise StoreContextError(zip_code=zip_code) from exc

    search_buttons: list[Any] = []
    try:
        search_buttons.append(page.get_by_role("button", name=re.compile("search|find store|go", re.I)))
    except Exception:
        pass
    search_buttons.append(page.locator("text=/Search/i"))
    search_buttons.append(page.locator("text=/Find Store/i"))

    if not await _safe_click(search_buttons):
        try:
            await zip_input.press("Enter")
        except Exception as exc:
            raise StoreContextError(zip_code=zip_code) from exc

    await human_wait(500, 900)

    result_buttons: list[Any] = []
    try:
        result_buttons.append(page.get_by_role("button", name=re.compile("set store|select store|make this my store", re.I)))
    except Exception:
        pass
    try:
        result_buttons.append(page.get_by_role("link", name=re.compile("set store|select store", re.I)))
    except Exception:
        pass
    result_buttons.append(page.locator("text=/Set Store/i"))
    result_buttons.append(page.locator("text=/Select Store/i"))

    if not await _safe_click(result_buttons):
        raise StoreContextError(zip_code=zip_code)

    await human_wait(400, 800)

    badge_locator = None
    if selectors.STORE_BADGE:
        try:
            badge_locator = page.locator(selectors.STORE_BADGE)
        except Exception:
            badge_locator = None
    badge_text = await inner_text_safe(badge_locator)

    if not badge_text:
        raise StoreContextError(zip_code=zip_code)

    cleaned = re.sub(r"(?i)my\s+store[:\-\s]*", "", badge_text).strip()
    store_name = cleaned or badge_text.strip()

    id_match = re.search(r"\b(\d{3,6})\b", badge_text)
    store_id = id_match.group(1) if id_match else None

    if store_id:
        LOGGER.info("Set Lowe's store %s (%s) for ZIP %s", store_name, store_id, zip_code)
    else:
        LOGGER.info("Set Lowe's store %s for ZIP %s", store_name, zip_code)

    return store_id, store_name


def _text_contains_clearance(text: str | None) -> bool:
    if not text:
        return False
    return "clearance" in text.lower()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.5, max=5),
    reraise=True,
)
async def scrape_category(page: Any, url: str, category_name: str, zip_code: str) -> list[dict]:
    """Scrape a Lowe's category page for the specified ZIP code."""

    LOGGER.info("Scraping Lowe's category '%s' for ZIP %s", category_name, zip_code)

    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
    except Exception as exc:
        raise PageLoadError(url=url, zip_code=zip_code, category=category_name) from exc

    await human_wait(300, 700)
    await paginate_or_scroll(page, selectors.NEXT_BTN, max_pages=25)

    products: list[dict] = []
    card_locator = _maybe_locator(page, selectors.CARD)
    card_count = 0
    if card_locator is not None:
        try:
            card_count = await card_locator.count()
        except Exception:
            card_count = 0

    for index in range(card_count):
        card = card_locator.nth(index)

        title = await inner_text_safe(_maybe_locator(card, selectors.TITLE))
        price_text = await inner_text_safe(_maybe_locator(card, selectors.PRICE))
        price = price_to_float(price_text)
        was_price_text = await inner_text_safe(_maybe_locator(card, selectors.WAS_PRICE))
        was_price = price_to_float(was_price_text)
        availability = await inner_text_safe(_maybe_locator(card, selectors.AVAIL))

        image_url = await _safe_get_attribute(_maybe_locator(card, selectors.IMG), "src")
        product_url = await _safe_get_attribute(_maybe_locator(card, selectors.LINK), "href")

        sku: str | None = None
        for attribute in [
            "data-product-id",
            "data-productid",
            "data-sku",
            "data-item-id",
            "data-id",
            "data-sku-id",
        ]:
            sku = await _safe_get_attribute(card, attribute)
            if sku:
                break

        if not sku and product_url:
            sku_match = re.search(r"/p-?(\d+)", product_url)
            if not sku_match:
                sku_match = re.search(r"/product/[^/]*?(\d{6,})", product_url)
            if not sku_match:
                sku_match = re.search(r"(\d{6,})(?:[/?]|$)", product_url)
            if sku_match:
                sku = sku_match.group(1)

        card_text = await inner_text_safe(card)
        clearance = _text_contains_clearance(card_text) or _text_contains_clearance(
            await inner_text_safe(card.locator("text=/clearance/i"))
        )

        if not title and price is None:
            continue

        product_record = {
            "retailer": "lowes",
            "title": title,
            "price": price,
            "price_was": was_price,
            "availability": availability,
            "image_url": image_url,
            "product_url": product_url,
            "sku": sku,
            "category": category_name,
            "zip": zip_code,
            "clearance": clearance,
        }

        products.append(product_record)

    if not products:
        raise SelectorChangedError(url=url, zip_code=zip_code, category=category_name)

    LOGGER.info(
        "Finished scraping Lowe's category '%s' for ZIP %s with %d items",
        category_name,
        zip_code,
        len(products),
    )

    return products


async def run_for_zip(playwright: Any, zip_code: str, categories: list[dict]) -> list[dict]:
    """Execute scraping workflow for a single ZIP code."""

    browser = await playwright.chromium.launch(headless=True)
    context = None
    page = None
    try:
        context = await browser.new_context()
        try:
            context.set_default_timeout(10000)
        except Exception:
            pass
        page = await context.new_page()

        store_id, store_name = await set_store_context(page, zip_code)
        store_id = store_id or f"zip:{zip_code}"
        store_name = store_name or f"Lowe's {zip_code}"

        rows: list[dict] = []
        for category in categories:
            name = category.get("name") if isinstance(category, dict) else None
            url = category.get("url") if isinstance(category, dict) else None
            if not name or not url:
                continue

            LOGGER.info("Starting category '%s' for ZIP %s", name, zip_code)
            results = await scrape_category(page, url, name, zip_code)
            for record in results:
                if not record.get("store_id"):
                    record["store_id"] = store_id
                if not record.get("store_name"):
                    record["store_name"] = store_name
            rows.extend(results)
            await human_wait(250, 900)

        return rows
    except (StoreContextError, SelectorChangedError, PageLoadError):
        raise
    except Exception as exc:
        LOGGER.error("Unexpected error while scraping Lowe's for ZIP %s: %s", zip_code, exc)
        raise
    finally:
        try:
            if context is not None:
                await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
