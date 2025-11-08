"""Lowe's retailer scraping interface."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from tenacity import retry, stop_after_attempt, wait_random_exponential

import app.selectors as selectors
from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors import schemas
from app.extractors.dom_utils import human_wait, inner_text_safe, paginate_or_scroll
from app.logging_config import get_logger

LOGGER = get_logger(__name__)

CLEARANCE_RE = re.compile(
    r"\b(clearance|closeout|last\s*chance|final\s*price|special\s*value|new\s*lower\s*price)\b",
    re.I,
)

_SKU_PATTERNS = (
    re.compile(r"/pd/(?:[^/]*-)?(\d{4,})", re.I),
    re.compile(r"/product/[^/]+-(\d{4,})", re.I),
    re.compile(r"(\d{6,})(?:[/?]|$)"),
)

_STORE_BUTTON_TEXT = re.compile("(set|select|choose|make).{0,10}store", re.I)
_STORE_BADGE_FALLBACK = re.compile("store|my store|change store", re.I)


def _ensure_selectors_configured() -> None:
    required = (
        "CARD",
        "TITLE",
        "PRICE",
        "LINK",
        "STORE_BADGE",
    )
    missing = [
        name
        for name in required
        if not getattr(selectors, name, "").strip()
        or "TODO" in getattr(selectors, name, "").upper()
    ]
    if missing:
        raise SelectorChangedError(
            "SELECTORS_NOT_CONFIGURED: " + ", ".join(missing)
        )


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
            await locator.wait_for(state="visible", timeout=5000)
            await locator.click()
            await human_wait(400, 900)
            return True
        except Exception:
            continue
    return False


async def _first_locator(locators: list[Any]) -> Any | None:
    for locator in locators:
        if locator is None:
            continue
        try:
            await locator.wait_for(state="visible", timeout=5000)
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
    trimmed = value.strip()
    return trimmed or None


async def _locator_or_none(root: Any, selector: str | None) -> Any | None:
    if not selector:
        return None
    try:
        return root.locator(selector).first
    except Exception:
        return None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.5, max=5),
    reraise=True,
)
async def set_store_context(page: Any, zip_code: str) -> tuple[str, str]:
    """Set the Lowe's store context for *zip_code* and return (store_id, store_name)."""

    try:
        await page.goto("https://www.lowes.com/", wait_until="domcontentloaded")
    except Exception as exc:  # pragma: no cover - network failure
        raise StoreContextError(zip_code=zip_code) from exc

    await _safe_wait_for_load(page, "networkidle")
    await human_wait()

    triggers: list[Any] = []
    if selectors.STORE_BADGE:
        try:
            triggers.append(page.locator(selectors.STORE_BADGE).first)
        except Exception:
            pass
    try:
        triggers.append(page.get_by_role("button", name=_STORE_BADGE_FALLBACK))
    except Exception:
        pass
    try:
        triggers.append(page.get_by_role("link", name=_STORE_BADGE_FALLBACK))
    except Exception:
        pass
    triggers.append(page.locator("text=/Find a Store/i"))

    await _safe_click(triggers)

    search_locators: list[Any] = []
    try:
        search_locators.append(page.get_by_role("textbox", name=re.compile("zip", re.I)))
    except Exception:
        pass
    for selector in ("input[name*='zip']", "input[id*='zip']", "input[placeholder*='ZIP']"):
        search_locators.append(page.locator(selector))

    zip_input = await _first_locator(search_locators)
    if zip_input is None:
        raise StoreContextError(zip_code=zip_code)

    try:
        await zip_input.fill(zip_code)
    except Exception as exc:
        raise StoreContextError(zip_code=zip_code) from exc

    await human_wait()

    try:
        await zip_input.press("Enter")
    except Exception:
        try:
            await zip_input.evaluate("(el) => el.form && el.form.submit && el.form.submit()")
        except Exception:
            pass

    await human_wait(800, 1400)

    option_locators: list[Any] = []
    option_locators.append(page.locator("button:has-text('Set Store')"))
    option_locators.append(page.locator("button:has-text('Make This My Store')"))
    option_locators.append(page.locator("button:has-text('Select Store')"))
    try:
        option_locators.append(page.get_by_role("button", name=_STORE_BUTTON_TEXT))
    except Exception:
        pass

    store_button = await _first_locator(option_locators)
    if store_button is None:
        raise StoreContextError(zip_code=zip_code)

    store_id = await _safe_get_attribute(store_button, "data-storeid")
    if store_id is None:
        store_id = await _safe_get_attribute(store_button, "data-store-id")

    try:
        await store_button.click()
    except Exception as exc:
        raise StoreContextError(zip_code=zip_code) from exc

    await human_wait(900, 1500)

    badge_locator = await _locator_or_none(page, selectors.STORE_BADGE)
    if badge_locator is None:
        raise StoreContextError(zip_code=zip_code)
    try:
        await badge_locator.wait_for(state="visible", timeout=10000)
    except Exception as exc:
        raise StoreContextError(zip_code=zip_code) from exc

    store_name = await inner_text_safe(badge_locator)
    if not store_name:
        raise StoreContextError(zip_code=zip_code)

    if store_id is None:
        store_id = await _safe_get_attribute(badge_locator, "data-storeid")
    if store_id is None:
        store_id = f"{zip_code}:{store_name.strip()}"

    LOGGER.info("store=%s zip=%s", store_name.strip(), zip_code)
    return store_id.strip(), store_name.strip()


async def scrape_category(
    page: Any,
    url: str,
    category_name: str,
    zip_code: str,
    *,
    clearance_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    """Scrape a single Lowe's category page."""

    _ensure_selectors_configured()

    try:
        await page.goto(url, wait_until="domcontentloaded")
    except Exception as exc:  # pragma: no cover - navigation failure
        raise PageLoadError(url=url, zip_code=zip_code, category=category_name) from exc

    await _safe_wait_for_load(page, "networkidle")
    await human_wait()

    card_locator = page.locator(selectors.CARD)
    try:
        await card_locator.first.wait_for(state="visible", timeout=15000)
    except Exception as exc:
        raise PageLoadError(url=url, zip_code=zip_code, category=category_name) from exc

    products: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    paginated = bool(selectors.NEXT_BTN and selectors.NEXT_BTN.strip())
    processed = 0

    while True:
        try:
            card_count = await card_locator.count()
        except Exception:
            card_count = 0

        if card_count == 0:
            break

        start_index = 0 if paginated else processed
        for index in range(start_index, card_count):
            card = card_locator.nth(index)
            record = await _extract_card(
                card,
                url=url,
                category_name=category_name,
                zip_code=zip_code,
                clearance_threshold=clearance_threshold,
            )
            if record is None:
                continue
            key = (record.get("sku"), record.get("product_url"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            products.append(record)

        if not paginated:
            processed = card_count

        advanced = await paginate_or_scroll(page, selectors.NEXT_BTN)
        if not advanced:
            break

        await human_wait()

        if not paginated:
            try:
                new_count = await card_locator.count()
            except Exception:
                new_count = 0
            if new_count <= processed:
                break

    if not products:
        raise SelectorChangedError(
            "SELECTORS_NOT_CONFIGURED or zero cards rendered.",
            url=url,
            zip_code=zip_code,
            category=category_name,
        )

    LOGGER.info(
        "Scraped %d Lowe's rows for category=%s zip=%s",
        len(products),
        category_name,
        zip_code,
    )
    return products


async def _extract_card(
    card: Any,
    *,
    url: str,
    category_name: str,
    zip_code: str,
    clearance_threshold: float,
) -> dict[str, Any] | None:
    title = await inner_text_safe(await _locator_or_none(card, selectors.TITLE))
    price_text = await inner_text_safe(await _locator_or_none(card, selectors.PRICE))
    price = schemas.parse_price(price_text)
    if price is None:
        price = schemas.parse_price(await inner_text_safe(card))
    was_text = await inner_text_safe(await _locator_or_none(card, selectors.WAS_PRICE))
    price_was = schemas.parse_price(was_text)
    availability = await inner_text_safe(await _locator_or_none(card, selectors.AVAIL))

    link_locator = await _locator_or_none(card, selectors.LINK)
    href = await _safe_get_attribute(link_locator, "href")
    product_url = urljoin(url, href) if href else None

    img_locator = await _locator_or_none(card, selectors.IMG)
    image_url = await _safe_get_attribute(img_locator, "src")
    if image_url:
        image_url = urljoin(url, image_url)

    sku = await _extract_sku(card, product_url)

    card_text = await inner_text_safe(card) or ""
    clearance = bool(CLEARANCE_RE.search(card_text))
    pct_off = schemas.compute_pct_off(price, price_was)
    if pct_off is not None and pct_off >= clearance_threshold:
        clearance = True

    if not any([title, product_url, price]):
        return None

    return {
        "retailer": "lowes",
        "title": title or "",
        "price": price,
        "price_was": price_was,
        "availability": availability,
        "image_url": image_url,
        "product_url": product_url,
        "sku": sku,
        "category": category_name,
        "zip": zip_code,
        "clearance": clearance,
        "pct_off": pct_off,
    }


async def _extract_sku(card: Any, product_url: str | None) -> str | None:
    for attribute in (
        "data-product-id",
        "data-productid",
        "data-item-id",
        "data-sku",
        "data-sku-id",
        "data-id",
    ):
        sku = await _safe_get_attribute(card, attribute)
        if sku:
            return sku

    if not product_url:
        return None

    for pattern in _SKU_PATTERNS:
        match = pattern.search(product_url)
        if match:
            return match.group(1)
    return None


async def run_for_zip(
    playwright: Any,
    zip_code: str,
    categories: list[dict[str, Any]],
    *,
    clearance_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    """Execute the Lowe's workflow for a single ZIP."""

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent="lowes-orwa-tracker/1.0 (contact: you@example.com)",
        storage_state=None,
    )
    page = await context.new_page()

    try:
        store_id, store_name = await set_store_context(page, zip_code)
        results: list[dict[str, Any]] = []

        for category in categories:
            name = (category or {}).get("name")
            url = (category or {}).get("url")
            if not name or not url:
                continue

            LOGGER.info("Starting category=%s zip=%s", name, zip_code)

            @retry(
                stop=stop_after_attempt(3),
                wait=wait_random_exponential(multiplier=0.5, max=5),
                reraise=True,
            )
            async def _scrape() -> list[dict[str, Any]]:
                await human_wait()
                return await scrape_category(
                    page,
                    url,
                    name,
                    zip_code,
                    clearance_threshold=clearance_threshold,
                )

            category_rows = await _scrape()
            for row in category_rows:
                row.setdefault("store_id", store_id)
                row.setdefault("store_name", store_name)
            results.extend(category_rows)
            await human_wait()

        return results
    finally:
        try:
            await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass
