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


async def human_wait(min_ms: int = 600, max_ms: int = 1600) -> None:
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


async def paginate_or_scroll(page: Any, next_selector: str | None, *, max_scroll_attempts: int = 4) -> bool:
    """Advance pagination via a next button or perform an infinite scroll step.

    Returns ``True`` when additional content is likely available, otherwise ``False``.
    """

    if next_selector:
        try:
            locator = page.locator(next_selector).first
        except _HANDLEABLE_ERRORS:
            return False

        try:
            if await locator.count() == 0:
                return False
            if not (await locator.is_enabled() and await locator.is_visible()):
                return False
        except _HANDLEABLE_ERRORS:
            return False

        try:
            await locator.scroll_into_view_if_needed()
        except _HANDLEABLE_ERRORS:
            pass

        await human_wait()

        try:
            await locator.click()
        except _HANDLEABLE_ERRORS:
            return False

        try:
            await page.wait_for_load_state("networkidle")
        except _HANDLEABLE_ERRORS:
            pass

        await human_wait()
        return True

    baseline = await _get_scroll_height(page)
    if baseline is None:
        return False

    stagnant_readings = 0

    for _ in range(max_scroll_attempts):
        if (
            await _safe_evaluate(
                page,
                "(() => { window.scrollBy(0, Math.max(window.innerHeight || 0, 600)); return true; })()",
            )
            is None
        ):
            return False

        await human_wait()

        updated = await _get_scroll_height(page)
        if updated is None:
            continue

        if updated > baseline:
            return True

        if updated == baseline:
            stagnant_readings += 1
            if stagnant_readings >= 2:
                return False
        else:
            stagnant_readings = 0

    return False


async def _safe_evaluate(page: Any, script: str) -> Any:
    """Evaluate *script* on the page, swallowing transient browser errors."""

    try:
        return await page.evaluate(script)
    except _HANDLEABLE_ERRORS:
        return None


async def _get_scroll_height(page: Any) -> int | None:
    """Return the current scroll height if available."""

    value = await _safe_evaluate(page, "(() => document.body ? document.body.scrollHeight : null)()")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
