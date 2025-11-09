"""Lowe's retailer scraping interface."""

from __future__ import annotations

import os
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


def _resolve_user_agent() -> str | None:
    value = os.getenv("USER_AGENT")
    if not value:
        return None
    trimmed = value.strip()
    return trimmed or None

CLEARANCE_RE = re.compile(
    r"\b(clearance|closeout|last\s*chance|final\s*price|special\s*value|new\s*lower\s*price)\b",
    re.I,
)

_SKU_PATTERNS = (
    re.compile(
        rf"{re.escape(selectors.PRODUCT_PATH_FRAGMENT)}(?:[^/]*-)?(\d{{4,}})",
        re.I,
    ),
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
        or "..." in getattr(selectors, name, "")
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
async def set_store_context(
    page: Any,
    zip_code: str,
    *,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Set the Lowe's store context for *zip_code* and return (store_id, store_name)."""

    if user_agent is None:
        user_agent = _resolve_user_agent()

    if user_agent:
        try:
            await page.context.set_extra_http_headers({"User-Agent": user_agent})
        except Exception:  # pragma: no cover - defensive
            LOGGER.debug(
                "Unable to set USER_AGENT override; continuing with default",
                extra={"zip": zip_code},
            )

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

    LOGGER.info(
        "store=%s zip=%s",
        store_name.strip(),
        zip_code,
        extra={"zip": zip_code},
    )
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
    alt_locator = (
        page.locator(selectors.CARD_ALT)
        if getattr(selectors, "CARD_ALT", None)
        else None
    )
    active_locator = card_locator
    using_alt = False

    try:
        await active_locator.first.wait_for(state="visible", timeout=15000)
    except Exception as exc:
        if alt_locator is not None:
            try:
                await alt_locator.first.wait_for(state="visible", timeout=15000)
                active_locator = alt_locator
                using_alt = True
            except Exception as alt_exc:
                raise SelectorChangedError(
                    "Initial product cards failed to load.",
                    url=url,
                    zip_code=zip_code,
                    category=category_name,
                ) from alt_exc
        else:
            raise SelectorChangedError(
                "Initial product cards failed to load.",
                url=url,
                zip_code=zip_code,
                category=category_name,
            ) from exc

    products: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    pages = 0

    while True:
        try:
            card_count = await active_locator.count()
        except Exception:
            card_count = 0

        if card_count == 0 and not using_alt and alt_locator is not None:
            active_locator = alt_locator
            using_alt = True
            continue

        if card_count == 0:
            if pages == 0:
                raise SelectorChangedError(
                    "No product cards located on initial page.",
                    url=url,
                    zip_code=zip_code,
                    category=category_name,
                )
            break

        for index in range(card_count):
            card = active_locator.nth(index)
            record = await _extract_card(
                card,
                url=url,
                category_name=category_name,
                zip_code=zip_code,
                clearance_threshold=clearance_threshold,
            )
            if record is None:
                continue
            key = (
                record.get("sku") or record.get("product_url"),
                record.get("product_url"),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            products.append(record)

        pages += 1
        advanced = await paginate_or_scroll(page, selectors.NEXT_BTN)
        if not advanced:
            break

        await human_wait()

    if not products:
        raise SelectorChangedError(
            "No products extracted from category.",
            url=url,
            zip_code=zip_code,
            category=category_name,
        )

    LOGGER.info(
        "Scraped %d Lowe's rows for category=%s zip=%s",
        len(products),
        category_name,
        zip_code,
        extra={"zip": zip_code, "category": category_name, "url": url},
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
    if price is None and getattr(selectors, "PRICE_ALT", None):
        alt_price_text = await inner_text_safe(
            await _locator_or_none(card, selectors.PRICE_ALT)
        )
        price = schemas.parse_price(alt_price_text)
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
    browser: Any | None = None,
) -> list[dict[str, Any]]:
    """Execute the Lowe's workflow for a single ZIP."""

    user_agent = _resolve_user_agent()
    owns_browser = browser is None
    if owns_browser:
        browser = await playwright.chromium.launch(headless=True)

    context_kwargs: dict[str, Any] = {
        "viewport": {"width": 1440, "height": 900},
        "storage_state": None,
    }
    if user_agent:
        context_kwargs["user_agent"] = user_agent

    assert browser is not None
    context = await browser.new_context(**context_kwargs)
    page = await context.new_page()

    try:
        store_id, store_name = await set_store_context(
            page,
            zip_code,
            user_agent=user_agent,
        )
        results: list[dict[str, Any]] = []

        for category in categories:
            name = (category or {}).get("name")
            url = (category or {}).get("url")
            if not name or not url:
                continue

            LOGGER.info(
                "Starting category=%s zip=%s",
                name,
                zip_code,
                extra={"zip": zip_code, "category": name, "url": url},
            )

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
        except Exception as exc:
            LOGGER.warning(
                "Failed to close browser context: %s",
                exc,
                extra={"zip": zip_code},
            )
        if owns_browser:
            assert browser is not None  # for type checking
            try:
                await browser.close()
            except Exception as exc:
                LOGGER.warning(
                    "Failed to close browser: %s",
                    exc,
                    extra={"zip": zip_code},
                )
