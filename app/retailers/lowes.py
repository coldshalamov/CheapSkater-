"""Lowe's retailer scraping interface."""

from __future__ import annotations
import json
import os
import random
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from tenacity import retry, stop_after_attempt, wait_random_exponential

from playwright.async_api import async_playwright, Error as PlaywrightError

import app.selectors as selectors
from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors import schemas
from app.extractors.dom_utils import human_wait, inner_text_safe
from app.logging_config import get_logger
from app.normalizers import normalize_availability
from app.playwright_env import (
    apply_stealth,
    category_delay_bounds,
    headless_enabled,
    mouse_jitter_enabled,
)
from app.playwright_env import headless_enabled

LOGGER = get_logger(__name__)
BASE_URL = "https://www.lowes.com"
GOTO_TIMEOUT_MS = 60000
BACK_AISLE_PAGE_SIZE = 24
MAX_BACK_AISLE_PAGES = 80
MAX_EMPTY_PAGE_RESULTS = 1
BACK_AISLE_DEPARTMENTS: dict[str, str] = {
    "Flooring": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294934373",
    "Hardware": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294934474",
    "Building Supplies": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294934297",
    "Lawn & Garden": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=1011552124422",
    "Plumbing": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294935907",
    "Lighting & Ceiling Fans": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294935637",
    "Tools": "https://www.lowes.com/pl/The-back-aisle/2021454685607?refinement=2&catalog=4294936478",
}


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


def _extract_sku_from_text(value: str | None) -> str | None:
    if not value:
        return None
    for pattern in _SKU_PATTERNS:
        match = pattern.search(value)
        if match:
            return match.group(1)
    return None


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


async def _page_body_text(page: Any) -> str | None:
    try:
        locator = page.locator("body")
        await locator.wait_for(timeout=1500)
        content = await locator.inner_text()
    except Exception:
        return None
    if not content:
        return None
    stripped = content.strip()
    return stripped or None


async def _ensure_not_blocked(
    page: Any,
    *,
    zip_code: str | None,
    url: str | None = None,
    context: str = "request",
) -> None:
    text = await _page_body_text(page)
    if not text:
        return
    lowered = text.lower()
    trigger_tokens = (
        "access denied",
        "you don't have permission",
        "edgesuite.net",
        "reference #",
    )
    if any(token in lowered for token in trigger_tokens):
        message = f"Access denied while {context}"
        raise StoreContextError(message=message, zip_code=zip_code, url=url)


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
            lowered = cleaned.lower()
            if not cleaned:
                continue
            if cleaned.isdigit():
                continue
            if "miles" in lowered:
                continue
            if lowered.startswith(("show less", "show more", "set as", "store:#")):
                continue
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


def _clean_store_name(value: str | None) -> str | None:
    if not value:
        return None
    collapsed = " ".join(value.split())
    if not collapsed:
        return None
    lowered = collapsed.lower()
    if "find a store" in lowered and "near me" in lowered:
        return None
    return collapsed


async def _find_store_result_button(
    page: Any,
    zip_code: str,
    *,
    preferred_store_id: str | None = None,
) -> _StoreChoice:
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

        trimmed_store_id = store_id.strip() if store_id else None

        if preferred_store_id and trimmed_store_id and trimmed_store_id == preferred_store_id.strip():
            LOGGER.info(
                "Selected preferred store '%s' (store_id=%s) for zip=%s via candidate index=%s",
                store_name or "unknown",
                trimmed_store_id,
                zip_code,
                idx,
            )
            return choice

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


async def _wait_for_store_cards(page: Any, timeout: int = 20000) -> bool:
    """Wait for the store result grid to become visible."""

    if not selectors.STORE_RESULT_ITEM:
        return False

    try:
        await page.wait_for_selector(selectors.STORE_RESULT_ITEM, timeout=timeout)
        return True
    except Exception:
        return False


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
    store_hint: dict[str, str] | None = None,
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
        await page.goto("https://www.lowes.com/", wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
    except Exception as exc:  # pragma: no cover - network failure
        raise StoreContextError(zip_code=zip_code) from exc

    await _safe_wait_for_load(page, "networkidle")
    await _ensure_not_blocked(
        page,
        zip_code=zip_code,
        url="https://www.lowes.com/",
        context="setting store context",
    )
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
    try:
        search_locators.append(page.get_by_placeholder(re.compile("zip|store|city", re.I)))
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

    submit_attempts = 0
    while submit_attempts < 2:
        submit_attempts += 1
        await human_wait(800, 1600)
        await _jitter_mouse(page)

        try:
            await zip_input.press("Enter")
        except Exception:
            try:
                await zip_input.evaluate("(el) => el.form && el.form.submit && el.form.submit()")
            except Exception:
                pass

        await human_wait(600, 1200)
        if await _wait_for_store_cards(page, timeout=14000):
            break

        LOGGER.warning(
            "Store results did not load for zip=%s on attempt=%s; retrying form submission",
            zip_code,
            submit_attempts,
        )
        try:
            await zip_input.fill("")
        except Exception:
            pass
        await human_wait(200, 400)
        await zip_input.fill(zip_code)

    if not await _wait_for_store_cards(page, timeout=12000):
        raise StoreContextError(zip_code=zip_code)

    option_locators: list[Any] = []
    option_locators.append(page.locator("button:has-text('Set Store')"))
    option_locators.append(page.locator("button:has-text('Make This My Store')"))
    option_locators.append(page.locator("button:has-text('Select Store')"))
    try:
        option_locators.append(page.get_by_role("button", name=_STORE_BUTTON_TEXT))
    except Exception:
        pass

    target_store_id = (store_hint or {}).get("store_id")
    store_choice = await _find_store_result_button(
        page,
        zip_code,
        preferred_store_id=target_store_id,
    )
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

    hinted_name = (store_hint or {}).get("store_name")
    hinted_id = (store_hint or {}).get("store_id")

    if not store_name:
        store_name = store_choice.store_name or hinted_name or f"Lowe's ({zip_code})"
    if store_id is None:
        store_id = store_choice.store_id or hinted_id or f"{zip_code}:{store_name.strip()}"
    if store_id is None:
        store_id = f"{zip_code}:{store_name.strip()}"

    store_name = _clean_store_name(store_name) or hinted_name or f"Lowe's ({zip_code})"

    _cache_store_selection(zip_code, store_id, store_name)

    LOGGER.info(
        "store=%s zip=%s",
        store_name.strip(),
        zip_code,
        extra={"zip": zip_code},
    )
    return store_id.strip(), store_name.strip()


def _prepare_category_url(url: str, store_id: str | None, *, offset: int = 0) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # Default to minimal URLs to reduce fingerprinting/risk of blocks.
    minimal = os.getenv("BACK_AISLE_MINIMAL_URL", "1") in {"1", "true", "True"}
    if not minimal:
        params.setdefault("pickupType", "pickupToday")
        params.setdefault("availability", "pickupToday")
        params["inStock"] = "1"
        params.setdefault("rollUpVariants", "0")
        if store_id and store_id.strip():
            params.setdefault("storeNumber", store_id.strip())
    params["offset"] = str(max(offset, 0))
    rebuilt = parsed._replace(query=urlencode(params, doseq=True))
    return rebuilt.geturl()


def _clean_department_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = re.sub(r"\(\s*\d+\s*\)$", "", name)
    return cleaned.strip(" \u2013\u2014-")


def _is_back_aisle_category(name: str | None, url: str | None) -> bool:
    lower_name = (name or "").lower()
    lower_url = (url or "").lower()
    return "back aisle" in lower_name or "the-back-aisle" in lower_url


async def _warmup_home(page: Any, zip_code: str | None = None) -> None:
    """Open the Lowe's homepage once to establish cookies before deep-linking."""

    if os.getenv("LOWES_WARMUP", "0") in {"0", "false", "False"}:
        return
    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await _safe_wait_for_load(page, "networkidle")
        await _ensure_not_blocked(
            page,
            zip_code=zip_code,
            url=BASE_URL,
            context="warming homepage",
        )
        await human_wait(300, 600)
    except Exception:
        # Non-fatal; continue even if warmup fails.
        return


async def _discover_back_aisle_departments(
    page: Any,
    base_url: str,
    *,
    store_id: str | None,
    zip_code: str,
) -> list[dict[str, str]]:
    """Return department-level Back Aisle URLs discovered from the sidebar."""

    fallback: dict[str, str] = dict(BACK_AISLE_DEPARTMENTS)
    # To avoid extra requests that can trip Akamai, let callers opt out of live discovery.
    if os.getenv("BACK_AISLE_DISCOVERY", "0") not in {"1", "true", "True"}:
        return [{"name": name, "url": url} for name, url in sorted(fallback.items()) if name and url]
    target_url = _prepare_category_url(base_url, store_id, offset=0)
    try:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        await _safe_wait_for_load(page, "networkidle")
        await _ensure_not_blocked(
            page,
            zip_code=zip_code,
            url=target_url,
            context="discovering Back Aisle departments",
        )
        await human_wait(180, 360)
        try:
            see_all = page.locator("button:has-text('See All'), a:has-text('See All')")
            count = await see_all.count()
        except Exception:
            count = 0
        for idx in range(count):
            try:
                await see_all.nth(idx).click(timeout=2500)
                await human_wait(120, 240)
            except Exception:
                continue

        try:
            anchors = await page.eval_on_selector_all(
                "a[href*='catalog=']",
                """(els) => els.map((el) => ({
                    href: el.href || '',
                    text: (el.textContent || '').trim()
                }))""",
            )
        except Exception:
            anchors = []

        discovered: dict[str, str] = {}
        for anchor in anchors or []:
            href = (anchor.get("href") or "").strip()
            text = _clean_department_name(anchor.get("text"))
            if not href or not text:
                continue
            if "the-back-aisle" not in href.lower():
                continue
            discovered[text] = href

        merged = {**fallback, **discovered}
        return [{"name": name, "url": url} for name, url in sorted(merged.items()) if name and url]
    except Exception as exc:  # pragma: no cover - defensive discovery
        LOGGER.warning("Back Aisle department discovery failed: %s", exc)
        return [{"name": name, "url": url} for name, url in sorted(fallback.items()) if name and url]


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

    products: list[dict[str, Any]] = []
    seen_keys: set[tuple[str | None, str | None]] = set()
    page_index = 0
    offset = 0
    empty_pages = 0

    while page_index < MAX_BACK_AISLE_PAGES:
        target_url = _prepare_category_url(url, store_id, offset=offset)
        LOGGER.debug(
            "Loading category page",
            extra={
                "zip": zip_code,
                "category": category_name,
                "url": target_url,
                "offset": offset,
                "page": page_index + 1,
            },
        )

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        except Exception as exc:  # pragma: no cover - navigation failure
            raise PageLoadError(url=target_url, zip_code=zip_code, category=category_name) from exc

        await _safe_wait_for_load(page, "networkidle")
        await _ensure_not_blocked(
            page,
            zip_code=zip_code,
            url=target_url,
            context=f"loading category page offset={offset}",
        )
        await _wait_for_product_grid(page)
        await human_wait(260, 540)

        page_index += 1
        page_rows = await _extract_products_from_dom(
            page,
            category_name=category_name,
            zip_code=zip_code,
            store_id=store_id,
            clearance_threshold=clearance_threshold,
            seen_keys=seen_keys,
        )
        row_count = len(page_rows)
        if row_count:
            products.extend(page_rows)
            empty_pages = 0
        else:
            empty_pages += 1
        LOGGER.info(
            "Back Aisle page=%s rows=%s offset=%s zip=%s",
            page_index,
            row_count,
            offset,
            zip_code,
            extra={
                "zip": zip_code,
                "category": category_name,
                "url": target_url,
                "offset": offset,
                "page": page_index,
            },
        )

        if row_count < BACK_AISLE_PAGE_SIZE or empty_pages > MAX_EMPTY_PAGE_RESULTS:
            break

        offset += BACK_AISLE_PAGE_SIZE

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
    store_id: str | None,
    clearance_threshold: float,
    seen_keys: set[tuple[str | None, str | None]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    rows.extend(
        await _extract_products_from_json_scripts(
            page,
            category_name=category_name,
            zip_code=zip_code,
            store_id=store_id,
            clearance_threshold=clearance_threshold,
            seen_keys=seen_keys,
        )
    )

    rows.extend(
        await _extract_rows_from_cards(
            page,
            category_name=category_name,
            zip_code=zip_code,
            store_id=store_id,
            clearance_threshold=clearance_threshold,
            seen_keys=seen_keys,
        )
    )

    return rows


async def _extract_products_from_json_scripts(
    page: Any,
    *,
    category_name: str,
    zip_code: str,
    store_id: str | None,
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
                store_id=store_id,
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


async def _extract_rows_from_cards(
    page: Any,
    *,
    category_name: str,
    zip_code: str,
    store_id: str | None,
    clearance_threshold: float,
    seen_keys: set[tuple[str | None, str | None]],
) -> list[dict[str, Any]]:
    selector = selectors.CARD
    if not selector:
        return []

    try:
        cards = page.locator(selector)
        total = await cards.count()
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for index in range(total):
        card = cards.nth(index)
        row = await _card_locator_to_row(
            card,
            category_name=category_name,
            zip_code=zip_code,
            store_id=store_id,
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


def _ensure_store_product_url(url: str | None, store_id: str | None) -> str | None:
    if not url:
        return None

    absolute = urljoin(BASE_URL, url)
    if not store_id:
        return absolute

    parsed = urlparse(absolute)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    has_store_param = any(key.lower() == "storenumber" for key, _ in params)
    if not has_store_param and store_id and store_id.strip():
        params.append(("storeNumber", store_id.strip()))

    if not params:
        return absolute

    query_text = urlencode(params, doseq=True)
    updated = parsed._replace(query=query_text)
    return urlunparse(updated)


def _product_dict_to_row(
    product: dict[str, Any],
    *,
    category_name: str,
    zip_code: str,
    store_id: str | None,
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
    product_url = _ensure_store_product_url(offers.get("url") or product.get("url"), store_id)

    image_url = _normalize_image_url(product.get("image"))
    sku = product.get("sku") or product.get("productID") or product.get("itemNumber")
    availability = normalize_availability(offers.get("availability"))
    title = (product.get("name") or product.get("description") or "Lowe's item").strip()
    pct_off = schemas.compute_pct_off(price, price_was)
    clearance_flag = pct_off is None or pct_off >= max(clearance_threshold, 0)

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
        "clearance": clearance_flag,
        "pct_off": pct_off,
    }


async def _card_locator_to_row(
    card: Any,
    *,
    category_name: str,
    zip_code: str,
    store_id: str | None,
    clearance_threshold: float,
) -> dict[str, Any] | None:
    title = await _first_card_text(card, (selectors.TITLE,))
    if not title:
        fallback_text = await inner_text_safe(card)
        if not fallback_text:
            return None
        title = fallback_text.splitlines()[0].strip()

    price_text = await _first_card_text(card, (selectors.PRICE, selectors.PRICE_ALT))
    price = schemas.parse_price(price_text)
    if price is None:
        return None

    was_text = await _first_card_text(card, (selectors.WAS_PRICE,))
    price_was = schemas.parse_price(was_text)

    availability = normalize_availability(await _first_card_text(card, (selectors.AVAIL,)))
    product_url = await _extract_card_href(card)
    product_url = _ensure_store_product_url(product_url, store_id)
    image_url = await _extract_card_image(card)
    sku = await _extract_card_sku(card, product_url)
    pct_off = schemas.compute_pct_off(price, price_was)
    clearance_flag = pct_off is None or pct_off >= max(clearance_threshold, 0)

    return {
        "retailer": "lowes",
        "title": title.strip(),
        "price": price,
        "price_was": price_was,
        "availability": (availability or "").strip(),
        "image_url": image_url,
        "product_url": product_url,
        "sku": sku,
        "category": category_name,
        "zip": zip_code,
        "clearance": clearance_flag,
        "pct_off": pct_off,
    }


async def _first_card_text(card: Any, selectors_to_try: tuple[str, ...]) -> str | None:
    for selector in selectors_to_try:
        if not selector:
            continue
        locator = await _locator_or_none(card, selector)
        if locator is None:
            continue
        text = await inner_text_safe(locator)
        if text:
            return text
    return None


async def _extract_card_href(card: Any) -> str | None:
    locator = await _locator_or_none(card, selectors.LINK)
    href: str | None = None
    if locator is not None:
        href = await _safe_get_attribute(locator, "href")
        if not href:
            href = await _safe_get_attribute(locator, "data-href")
    if not href:
        return None
    return urljoin(BASE_URL, href)


async def _extract_card_image(card: Any) -> str | None:
    locator = await _locator_or_none(card, selectors.IMG)
    if locator is None:
        return None
    for attr in ("src", "data-src", "data-original", "data-srcset"):
        value = await _safe_get_attribute(locator, attr)
        if value:
            candidate = value.split(",")[0].strip()
            normalized = _normalize_image_url(candidate)
            if normalized:
                return normalized
    return None


async def _extract_card_sku(card: Any, product_url: str | None) -> str | None:
    dataset_attributes = (
        "data-itemid",
        "data-item-id",
        "data-sku",
        "data-sku-id",
        "data-model-id",
        "data-modelnumber",
        "data-product-id",
        "data-productid",
        "data-itemnumber",
    )
    for attr in dataset_attributes:
        value = await _safe_get_attribute(card, attr)
        sku = _extract_sku_from_text(value)
        if sku:
            return sku

    sku = _extract_sku_from_text(product_url)
    if sku:
        return sku

    card_text = await inner_text_safe(card)
    return _extract_sku_from_text(card_text)

async def run_for_zip(
    playwright: Any | None,
    zip_code: str,
    categories: list[dict[str, Any]],
    *,
    clearance_threshold: float = 0.25,
    browser: Any | None = None,
    shared_context: Any | None = None,
    store_hints: dict[str, list[dict[str, str]]] | None = None,
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
                page_crashed = False
                crash_reason = "page closed unexpectedly"

                def _mark_crash(reason: str) -> None:
                    nonlocal page_crashed, crash_reason
                    if not page_crashed:
                        crash_reason = reason
                        page_crashed = True
                        LOGGER.error(
                            "Playwright page event=%s zip=%s",
                            reason,
                            zip_code,
                        )

                try:
                    page.on("crash", lambda _: _mark_crash("crash"))
                except Exception:
                    pass
                try:
                    page.on("close", lambda _: _mark_crash("page_close"))
                except Exception:
                    pass

                def _ensure_page_active() -> None:
                    if page_crashed:
                        raise PlaywrightError(f"browser page inactive ({crash_reason})")

                await _jitter_mouse(page)
                store_hint_entry: dict[str, str] | None = None
                if store_hints:
                    hinted = store_hints.get(zip_code)
                    if hinted:
                        store_hint_entry = hinted[0]
                        LOGGER.info(
                            "Using store hint for zip=%s -> %s (%s)",
                            zip_code,
                            store_hint_entry.get("store_name"),
                            store_hint_entry.get("store_id"),
                        )
                # Establish cookies before hitting deep Back Aisle links.
                await _warmup_home(page, zip_code)
                store_id, store_name = await set_store_context(
                    page,
                    zip_code,
                    user_agent=user_agent,
                    store_hint=store_hint_entry,
                )
                _ensure_page_active()

                categories_to_scrape: list[dict[str, str]] = []
                for category in categories:
                    name = (category or {}).get("name")
                    url = (category or {}).get("url")
                    if not name or not url:
                        continue
                    if _is_back_aisle_category(name, url):
                        # Legacy default: stick to a single Back Aisle URL to minimise requests.
                        if os.getenv("BACK_AISLE_LEGACY", "1") in {"1", "true", "True"}:
                            categories_to_scrape.append({"name": name, "url": url})
                            continue
                        discovered = await _discover_back_aisle_departments(
                            page,
                            url,
                            store_id=store_id,
                            zip_code=zip_code,
                        )
                        if discovered:
                            categories_to_scrape.extend(discovered)
                            continue
                    categories_to_scrape.append({"name": name, "url": url})

                for category in categories_to_scrape:
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
                        _ensure_page_active()
                        return await scrape_category(
                            page,
                            url,
                            name,
                            zip_code,
                            store_id,
                            clearance_threshold=clearance_threshold,
                        )

                    category_rows = await _scrape()
                    _ensure_page_active()
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
