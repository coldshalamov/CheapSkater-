"""Helper utilities for safely interacting with retailer DOM content."""

from __future__ import annotations

import asyncio
import random
import re
from typing import Any

try:  # Prefer Playwright's TimeoutError when available.
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except Exception:  # pragma: no cover - fallback for environments without Playwright.
    PlaywrightTimeoutError = None  # type: ignore[misc]

if PlaywrightTimeoutError is not None:
    _HANDLEABLE_ERRORS: tuple[type[BaseException], ...] = (PlaywrightTimeoutError, Exception)
else:  # pragma: no cover - executed only when Playwright is absent.
    _HANDLEABLE_ERRORS = (Exception,)


async def human_wait(min_ms: int = 200, max_ms: int = 900) -> None:
    """Sleep for a random, human-like interval between the provided bounds."""

    if min_ms < 0:
        min_ms = 0
    if max_ms < min_ms:
        max_ms = min_ms

    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)


async def inner_text_safe(locator: Any, timeout: int = 3000) -> str | None:
    """Return the stripped inner text for *locator* while ignoring DOM failures."""

    if locator is None:
        return None

    try:
        result = await locator.inner_text(timeout=timeout)
    except _HANDLEABLE_ERRORS:
        return None

    if result is None:
        return None

    return result.strip()


_NUMBER_PATTERN = re.compile(
    r"([-+]?)\s*(?:\$)?\s*((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)",
    re.UNICODE,
)


def price_to_float(text: str | None) -> float | None:
    """Convert a currency-like string to a float value when possible."""

    if text is None:
        return None

    match = _NUMBER_PATTERN.search(text)
    if not match:
        return None

    sign, number = match.groups()
    normalized = number.replace(",", "")

    try:
        value = float(normalized)
    except ValueError:
        return None

    if sign == "-":
        value *= -1
    return value


async def paginate_or_scroll(page: Any, next_selector: str | None, max_pages: int = 25) -> None:
    """Advance pagination or perform infinite scrolling without raising errors."""

    if max_pages <= 0:
        return

    if next_selector:
        await _paginate_by_button(page, next_selector, max_pages)
    else:
        await _infinite_scroll(page, max_pages)


async def _paginate_by_button(page: Any, selector: str, max_pages: int) -> None:
    """Click through pagination links while they remain interactable."""

    for _ in range(max_pages):
        try:
            locator = page.locator(selector)
        except _HANDLEABLE_ERRORS:
            break

        try:
            visible = await locator.is_visible()
            enabled = await locator.is_enabled()
        except _HANDLEABLE_ERRORS:
            break

        if not (visible and enabled):
            break

        await human_wait()

        try:
            await locator.scroll_into_view_if_needed()
        except _HANDLEABLE_ERRORS:
            pass

        try:
            await locator.click()
        except _HANDLEABLE_ERRORS:
            break

        try:
            await page.wait_for_load_state("networkidle")
        except _HANDLEABLE_ERRORS:
            pass

        await human_wait()


async def _infinite_scroll(page: Any, max_pages: int) -> None:
    """Perform incremental scrolling until content growth stops."""

    last_height: int | None = None
    for _ in range(max_pages):
        if (
            await _safe_evaluate(
                page,
                "(() => { window.scrollBy(0, Math.max(400, window.innerHeight || 0)); return true; })()",
            )
            is None
        ):
            break

        await human_wait()

        if (
            await _safe_evaluate(
                page,
                "(() => { window.scrollTo(0, document.body ? document.body.scrollHeight || 0 : 0); return true; })()",
            )
            is None
        ):
            break

        await human_wait()

        height = await _safe_evaluate(
            page, "(() => (document.body ? document.body.scrollHeight : null))()"
        )
        if height is None:
            break

        try:
            height_value = int(height)
        except (TypeError, ValueError):
            break

        if last_height is not None and height_value <= last_height:
            break

        last_height = height_value


async def _safe_evaluate(page: Any, script: str) -> Any:
    """Evaluate *script* on the page, swallowing transient browser errors."""

    try:
        return await page.evaluate(script)
    except _HANDLEABLE_ERRORS:
        return None
