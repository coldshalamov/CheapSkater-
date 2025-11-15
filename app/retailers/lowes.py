"""Lowe's retailer scraping interface."""

from __future__ import annotations
import json
import os
import random
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from tenacity import retry, stop_after_attempt, wait_random_exponential

from playwright.async_api import async_playwright

import app.selectors as selectors
from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors import schemas
from app.extractors.dom_utils import human_wait, inner_text_safe, paginate_or_scroll
from app.logging_config import get_logger
from app.playwright_env import (
    apply_stealth,
    category_delay_bounds,
    headless_enabled,
    mouse_jitter_enabled,
)
from app.playwright_env import headless_enabled

LOGGER = get_logger(__name__)
BASE_URL = "https://www.lowes.com"


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
_ZIP_PATTERN = re.compile(r"\b(\d{5})\b")
_STORE_ID_PATTERN = re.compile(r"Store:#\s*([0-9]+)", re.I)

_STORE_SELECTION_CACHE: dict[str, dict[str, str]] = {}
_STORE_MODAL_CACHE: dict[str, dict[str, str]] = {}


@dataclass
class _StoreChoice:
    button: Any | None
    store_id: str | None
    store_name: str | None
    zip_code: str | None


def _cache_store_candidate(
    zip_code: str,
    *,
    store_id: str | None,
    store_name: str | None,
    modal_zip: str | None,
    raw_text: str | None,
) -> None:
    if not zip_code:
        return
    _STORE_MODAL_CACHE[zip_code] = {
        "store_id": (store_id or "").strip(),
        "store_name": (store_name or "").strip(),
        "modal_zip": (modal_zip or "").strip(),
        "text": (raw_text or "").strip(),
    }


def _cache_store_selection(zip_code: str, store_id: str | None, store_name: str | None) -> None:
    if not zip_code:
        return
    _STORE_SELECTION_CACHE[zip_code] = {
        "store_id": (store_id or "").strip(),
        "store_name": (store_name or "").strip(),
    }


def _get_cached_store(zip_code: str) -> dict[str, str] | None:
    entry = _STORE_SELECTION_CACHE.get(zip_code)
    if not entry:
        return None
    if not entry.get("store_id") and not entry.get("store_name"):
        return None
    return entry


def _store_badge_matches_cached(
    cached: dict[str, str] | None,
    *,
    badge_store_id: str | None,
    badge_text: str | None,
) -> bool:
    if not cached:
        return False
    cached_id = (cached.get("store_id") or "").strip()
    cached_name = (cached.get("store_name") or "").strip().lower()
    if cached_id and badge_store_id and cached_id == badge_store_id.strip():
        return True
    if cached_name and badge_text:
        stripped_badge = badge_text.strip().lower()
        if cached_name and cached_name in stripped_badge:
            return True
    return False


async def _category_pause() -> None:
    """Introduce a realistic break between category fetches."""

    min_ms, max_ms = category_delay_bounds()
    if max_ms <= 0:
        return
    await human_wait(min_ms, max_ms, obey_policy=False)


async def _jitter_mouse(page: Any) -> None:
    """Randomise cursor movement to mimic human browsing."""

    if not mouse_jitter_enabled():
        return

    try:
        width = await page.evaluate("() => window.innerWidth || 1280")
        height = await page.evaluate("() => window.innerHeight || 800")
    except Exception:
        width, height = 1280, 800

    try:
        for _ in range(random.randint(1, 3)):
            target_x = random.randint(0, int(max(width, 1)))
            target_y = random.randint(0, int(max(height, 1)))
            steps = random.randint(3, 7)
            await page.mouse.move(target_x, target_y, steps=steps)
            await human_wait(120, 320, obey_policy=False)
    except Exception:
        # Non-fatal; simply skip cursor jitter if Playwright rejects the move.
        return


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


async def _extract_store_meta(card: Any) -> tuple[str | None, str | None, str | None, str | None]:
    """Return (store_name, store_id, match_zip, text) for a locator card."""

    text = await inner_text_safe(card)
    store_name = None
    if text:
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith(("Show Less", "Show More")):
                store_name = cleaned
                break

    store_id = await _safe_get_attribute(card, "data-storeid")
    if not store_id and text:
        match = _STORE_ID_PATTERN.search(text)
        if match:
            store_id = match.group(1)

    candidate_zip = (
        await _safe_get_attribute(card, "data-zip")
        or await _safe_get_attribute(card, "data-zipcode")
    )
    match_zip = candidate_zip
    if text:
        match = _ZIP_PATTERN.search(text)
        if match:
            match_zip = match.group(1)

    return store_name, store_id, match_zip, text


async def _find_store_result_button(page: Any, zip_code: str) -> _StoreChoice:
    """Return the store selection choice that matches *zip_code*."""

    try:
        cards = page.locator(selectors.STORE_RESULT_ITEM)
    except Exception:
        LOGGER.debug("STORE_RESULT_ITEM locator unavailable; falling back to generic buttons")
        return _StoreChoice(button=None, store_id=None, store_name=None, zip_code=None)

    try:
        count = await cards.count()
    except Exception:
        count = 0

    if count == 0:
        LOGGER.warning("No store cards rendered for zip=%s", zip_code)
        return _StoreChoice(button=None, store_id=None, store_name=None, zip_code=None)

    fallback_choice: _StoreChoice | None = None

    for idx in range(count):
        card = cards.nth(idx)
        store_name, store_id, match_zip, card_text = await _extract_store_meta(card)
        LOGGER.info(
            "Store candidate | idx=%s | store=%s | store_id=%s | candidate_zip=%s",
            idx,
            (store_name or "unknown").strip(),
            (store_id or "unknown").strip(),
            match_zip or "n/a",
            extra={"zip": zip_code},
        )

        button_locators = [
            card.locator("button:has-text('Set Store')"),
            card.locator("button:has-text('Make This My Store')"),
            card.locator("button:has-text('Select Store')"),
        ]
        try:
            button_locators.append(card.get_by_role("button", name=_STORE_BUTTON_TEXT))
        except Exception:
            pass

        button = await _first_locator(button_locators)
        if button is None:
            continue

        choice = _StoreChoice(
            button=button,
            store_id=(store_id.strip() if store_id else None),
            store_name=store_name,
            zip_code=(match_zip.strip() if match_zip else None),
        )
        _cache_store_candidate(
            zip_code,
            store_id=choice.store_id,
            store_name=choice.store_name,
            modal_zip=choice.zip_code,
            raw_text=card_text,
        )

        if match_zip and match_zip.strip() == zip_code:
            LOGGER.info(
                "Selected matching store '%s' (store_id=%s) for zip=%s via candidate index=%s",
                store_name or "unknown",
                store_id or "unknown",
                zip_code,
                idx,
            )
            return choice

        if fallback_choice is None:
            fallback_choice = choice

    LOGGER.info(
        "No exact zip match; accepting first available store for zip=%s",
        zip_code,
    )
    if fallback_choice is not None:
        return fallback_choice

    LOGGER.error("Store selector failed to expose actionable buttons for zip=%s", zip_code)
    return _StoreChoice(button=None, store_id=None, store_name=None, zip_code=None)


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
    await human_wait(900, 1500)
    await _jitter_mouse(page)

    cached_store = _get_cached_store(zip_code)
    badge_locator = await _locator_or_none(page, selectors.STORE_BADGE)
    badge_text = None
    badge_store_id = None
    if badge_locator is not None:
        try:
            await badge_locator.wait_for(state="visible", timeout=6000)
        except Exception:
            pass
        badge_text = await inner_text_safe(badge_locator)
        badge_store_id = await _safe_get_attribute(badge_locator, "data-storeid")

    if _store_badge_matches_cached(
        cached_store,
        badge_store_id=badge_store_id,
        badge_text=badge_text,
    ):
        resolved_name = badge_text or (cached_store or {}).get("store_name") or f"Lowe's ({zip_code})"
        resolved_id = badge_store_id or (cached_store or {}).get("store_id") or f"{zip_code}:{resolved_name.strip()}"
        LOGGER.info(
            "Store already set via persistent profile | store=%s | zip=%s",
            resolved_name.strip(),
            zip_code,
        )
        _cache_store_selection(zip_code, resolved_id, resolved_name)
        return resolved_id.strip(), resolved_name.strip()

    triggers: list[Any] = []
    if badge_locator is not None:
        triggers.append(badge_locator)
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
    await _jitter_mouse(page)

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

    await human_wait(800, 1600)
    await _jitter_mouse(page)

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

    store_choice = await _find_store_result_button(page, zip_code)
    store_button = store_choice.button
    if store_button is None:
        LOGGER.warning("Falling back to generic store button selection | zip=%s", zip_code)
        store_button = await _first_locator(option_locators)
        store_choice = _StoreChoice(
            button=store_button,
            store_id=None,
            store_name=None,
            zip_code=None,
        )
    if store_button is None:
        raise StoreContextError(zip_code=zip_code)

    store_id = await _safe_get_attribute(store_button, "data-storeid")
    if store_id is None:
        store_id = await _safe_get_attribute(store_button, "data-store-id")
    if store_id is None:
        store_id = store_choice.store_id
    if store_id is None:
        cached_modal = _STORE_MODAL_CACHE.get(zip_code)
        if cached_modal and cached_modal.get("store_id"):
            store_id = cached_modal.get("store_id")

    try:
        await store_button.click()
    except Exception as exc:
        raise StoreContextError(zip_code=zip_code) from exc

    await human_wait(1400, 2200, obey_policy=False)
    await _jitter_mouse(page)

    badge_locator = await _locator_or_none(page, selectors.STORE_BADGE)
    store_name = None
    if badge_locator is not None:
        try:
            await badge_locator.wait_for(state="visible", timeout=10000)
            store_name = await inner_text_safe(badge_locator)
            badge_store_id = await _safe_get_attribute(badge_locator, "data-storeid")
            if badge_store_id:
                store_id = badge_store_id
        except Exception:
            LOGGER.warning("Store badge did not confirm selection for zip=%s", zip_code)
    else:
        LOGGER.warning("Store badge locator missing after selecting zip=%s", zip_code)

    if not store_name:
        store_name = store_choice.store_name or f"Lowe's ({zip_code})"
    if store_id is None:
        store_id = store_choice.store_id or f"{zip_code}:{store_name.strip()}"
    if store_id is None:
        store_id = f"{zip_code}:{store_name.strip()}"

    _cache_store_selection(zip_code, store_id, store_name)

    LOGGER.info(
        "store=%s zip=%s",
        store_name.strip(),
        zip_code,
        extra={"zip": zip_code},
    )
    return store_id.strip(), store_name.strip()


def _prepare_category_url(url: str, store_id: str | None) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("pickupType", "pickupToday")
    params.setdefault("availability", "pickupToday")
    params.setdefault("inStock", "true")
    if store_id and store_id.strip():
        params.setdefault("storeNumber", store_id.strip())
    rebuilt = parsed._replace(query=urlencode(params, doseq=True))
    return rebuilt.geturl()


async def _wait_for_product_grid(page: Any) -> bool:
    selectors_to_try = [selectors.CARD]
    alt = getattr(selectors, "CARD_ALT", None)
    if alt:
        selectors_to_try.append(alt)
    for selector in selectors_to_try:
        if not selector:
            continue
        try:
            await page.wait_for_selector(selector, timeout=25000)
            return True
        except Exception:
            continue
    return False


async def scrape_category(
    page: Any,
    url: str,
    category_name: str,
    zip_code: str,
    store_id: str | None,
    *,
    clearance_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    """Scrape a Back Aisle listing page via DOM extraction."""

    _ensure_selectors_configured()

    target_url = _prepare_category_url(url, store_id)
    LOGGER.debug(
        "Loading category page",
        extra={"zip": zip_code, "category": category_name, "url": target_url},
    )

    try:
        await page.goto(target_url, wait_until="domcontentloaded")
    except Exception as exc:  # pragma: no cover - navigation failure
        raise PageLoadError(url=target_url, zip_code=zip_code, category=category_name) from exc

    await _safe_wait_for_load(page, "networkidle")
    await human_wait(400, 900)

    products: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    pages = 0

    while True:
        page_rows = await _extract_products_from_dom(
            page,
            category_name=category_name,
            zip_code=zip_code,
            clearance_threshold=clearance_threshold,
            seen_keys=seen_keys,
        )
        if page_rows:
            products.extend(page_rows)
            LOGGER.debug(
                "Extracted %s Back Aisle rows on page %s",
                len(page_rows),
                pages + 1,
                extra={"zip": zip_code, "category": category_name, "url": target_url},
            )

        pages += 1
        advanced = await paginate_or_scroll(page, selectors.NEXT_BTN)
        if not advanced:
            break

        await human_wait()

    if not products:
        LOGGER.info(
            "No Back Aisle items detected for category=%s zip=%s",
            category_name,
            zip_code,
            extra={"zip": zip_code, "category": category_name, "url": target_url},
        )
        return []

    LOGGER.info(
        "Scraped %d Lowe's rows for category=%s zip=%s",
        len(products),
        category_name,
        zip_code,
        extra={"zip": zip_code, "category": category_name, "url": target_url},
    )
    return products


async def _extract_products_from_dom(
    page: Any,
    *,
    category_name: str,
    zip_code: str,
    clearance_threshold: float,
    seen_keys: set[tuple[str | None, str | None]],
) -> list[dict[str, Any]]:
    script_locator = page.locator("script[type='application/ld+json']")
    try:
        count = await script_locator.count()
    except Exception:
        count = 0

    if count == 0:
        return []

    rows: list[dict[str, Any]] = []

    for index in range(count):
        try:
            raw = await script_locator.nth(index).inner_text()
        except Exception:
            continue
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for product in _collect_product_dicts(payload):
            row = _product_dict_to_row(
                product,
                category_name=category_name,
                zip_code=zip_code,
                clearance_threshold=clearance_threshold,
            )
            if row is None:
                continue
            key = (
                row.get("sku") or row.get("product_url"),
                row.get("product_url"),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            rows.append(row)

    return rows


def _collect_product_dicts(obj: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if (value.get("@type") or "").lower() == "product":
                results.append(value)
            else:
                for nested in value.values():
                    _walk(nested)
        elif isinstance(value, list):
            for entry in value:
                _walk(entry)

    _walk(obj)
    return results


def _normalize_image_url(value: Any) -> str | None:
    if isinstance(value, list):
        for entry in value:
            normalized = _normalize_image_url(entry)
            if normalized:
                return normalized
        return None

    if not isinstance(value, str) or not value:
        return None

    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return urljoin(BASE_URL, value)
    return value


def _product_dict_to_row(
    product: dict[str, Any],
    *,
    category_name: str,
    zip_code: str,
    clearance_threshold: float,
) -> dict[str, Any] | None:
    if not isinstance(product, dict):
        return None

    offers: Any = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}

    price = schemas.parse_price(str(offers.get("price")))
    if price is None:
        return None

    price_was = schemas.parse_price(str(offers.get("priceWas")))
    product_url = offers.get("url") or product.get("url")
    if product_url:
        product_url = urljoin(BASE_URL, product_url)

    image_url = _normalize_image_url(product.get("image"))
    sku = product.get("sku") or product.get("productID") or product.get("itemNumber")
    availability = offers.get("availability") or ""
    title = (product.get("name") or product.get("description") or "Lowe's item").strip()
    pct_off = schemas.compute_pct_off(price, price_was)

    return {
        "retailer": "lowes",
        "title": title,
        "price": price,
        "price_was": price_was,
        "availability": availability,
        "image_url": image_url,
        "product_url": product_url,
        "sku": sku,
        "category": category_name,
        "zip": zip_code,
        "clearance": True,
        "pct_off": pct_off,
    }

async def run_for_zip(
    playwright: Any | None,
    zip_code: str,
    categories: list[dict[str, Any]],
    *,
    clearance_threshold: float = 0.25,
    browser: Any | None = None,
    shared_context: Any | None = None,
) -> list[dict[str, Any]]:
    """Execute the Lowe's workflow for a single ZIP."""

    async def _execute(active_playwright: Any) -> list[dict[str, Any]]:
        extra = {"zip": zip_code}
        active_browser = browser
        owns_browser = active_browser is None
        user_agent = _resolve_user_agent()

        try:
            if owns_browser:
                active_browser = await active_playwright.chromium.launch(
                    headless=headless_enabled()
                )

            assert active_browser is not None

            context_kwargs: dict[str, Any] = {
                "viewport": {"width": 1440, "height": 900},
                "storage_state": None,
            }
            if user_agent:
                context_kwargs["user_agent"] = user_agent

            results: list[dict[str, Any]] = []

            context: Any | None = None
            owns_context = False
            page: Any | None = None
            try:
                if shared_context is not None:
                    context = shared_context
                else:
                    context = await active_browser.new_context(**context_kwargs)
                    owns_context = True

                page = await context.new_page()
                await _jitter_mouse(page)
                store_id, store_name = await set_store_context(
                    page,
                    zip_code,
                    user_agent=user_agent,
                )

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
                            store_id,
                            clearance_threshold=clearance_threshold,
                        )

                    category_rows = await _scrape()
                    for row in category_rows:
                        row.setdefault("store_id", store_id)
                        row.setdefault("store_name", store_name)
                    results.extend(category_rows)
                    LOGGER.debug(
                        "Category complete",
                        extra={
                            "zip": zip_code,
                            "category": name,
                            "items": len(category_rows),
                        },
                    )
                    await _category_pause()
            finally:
                if page is not None:
                    try:
                        await page.close()
                    except Exception as exc:
                        LOGGER.warning(
                            "Failed to close page: %s",
                            exc,
                            extra=extra,
                        )
                if owns_context and context is not None:
                    try:
                        await context.close()
                    except Exception as exc:
                        LOGGER.warning(
                            "Failed to close context: %s",
                            exc,
                            extra=extra,
                        )

            return results
        finally:
            try:
                if owns_browser and active_browser is not None:
                    await active_browser.close()
            except Exception as exc:
                LOGGER.warning(
                    "Failed to close browser: %s",
                    exc,
                    extra=extra,
                )
            LOGGER.info("Resource cleanup complete", extra=extra)

    if playwright is None:
        async with async_playwright() as auto_playwright:
            apply_stealth(auto_playwright)
            return await _execute(auto_playwright)

    return await _execute(playwright)
