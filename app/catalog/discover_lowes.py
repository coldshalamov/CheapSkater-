"""Discovery utilities for Lowe's catalog and store data."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

import yaml

import app.selectors as selectors
from app.extractors.dom_utils import human_wait, inner_text_safe, paginate_or_scroll

BASE_URL = "https://www.lowes.com/"
_CATEGORY_RE = re.compile(r"^/(?:c|pl)/", re.I)
_ZIP_RE = re.compile(r"\b(\d{5})\b")


@dataclass(slots=True)
class _CategoryCandidate:
    """Intermediate representation while crawling category listings."""

    path: str
    url: str
    names: set[str]


async def discover_categories(playwright: Any, max_depth: int = 3) -> list[dict[str, str]]:
    """Return a list of category dictionaries discovered from Lowe's public DOM."""

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await human_wait()

        candidates: dict[str, _CategoryCandidate] = {}
        queue: deque[tuple[str, int]] = deque()
        visited: set[str] = set()

        async def _record_anchor(anchor_locator, depth: int) -> None:
            try:
                href = await anchor_locator.get_attribute("href")
            except Exception:
                return
            if not href:
                return
            absolute = urljoin(BASE_URL, href)
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/")
            if not path or not _CATEGORY_RE.match(path):
                return
            normalized = f"{BASE_URL.rstrip('/')}{path}"

            try:
                text = await inner_text_safe(anchor_locator)
            except Exception:
                text = None

            entry = candidates.get(path)
            if entry is None:
                entry = _CategoryCandidate(path=path, url=normalized, names=set())
                candidates[path] = entry
            if text:
                entry.names.add(text.strip())

            if path not in visited and all(path != existing_path for existing_path, _ in queue):
                queue.append((normalized, depth))

        nav_buttons = page.locator(selectors.GLOBAL_NAV_BUTTONS)
        try:
            count = await nav_buttons.count()
        except Exception:
            count = 0

        for idx in range(count):
            button = nav_buttons.nth(idx)
            try:
                await button.hover()
            except Exception:
                pass
            await human_wait(300, 700)
            try:
                await button.click()
            except Exception:
                pass
            await human_wait(300, 700)

            megamenu_links = page.locator(selectors.MEGAMENU_LINKS)
            try:
                menu_count = await megamenu_links.count()
            except Exception:
                menu_count = 0
            for midx in range(menu_count):
                await _record_anchor(megamenu_links.nth(midx), 1)

        # Visit queued department pages breadth-first.
        while queue:
            url, depth = queue.popleft()
            parsed = urlparse(url)
            path = parsed.path.rstrip("/")
            if path in visited or depth > max_depth:
                continue
            visited.add(path)

            try:
                await page.goto(url, wait_until="domcontentloaded")
            except Exception:
                continue
            await page.wait_for_load_state("networkidle")
            await human_wait()

            entry = candidates.get(path)
            if entry is not None and not entry.names:
                header_locator = page.locator(selectors.PAGE_H1).first
                header_text = await inner_text_safe(header_locator)
                if header_text:
                    entry.names.add(header_text)

            hub_links = page.locator(selectors.DEPARTMENT_HUB_LINKS)
            try:
                hub_count = await hub_links.count()
            except Exception:
                hub_count = 0
            for hidx in range(hub_count):
                locator = hub_links.nth(hidx)
                await _record_anchor(locator, depth + 1)

        results: list[dict[str, str]] = []
        for candidate in candidates.values():
            name = next(iter(candidate.names), candidate.path.split("/")[-1].replace("-", " ").title())
            results.append({"name": name.strip(), "url": candidate.url})

        results.sort(key=lambda item: item["name"].lower())
        return results
    finally:
        await _safe_close(context, browser)


async def discover_stores_WA_OR(playwright: Any) -> list[dict[str, str]]:
    """Discover all Washington and Oregon stores from the public store locator."""

    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await context.new_page()

    try:
        await page.goto(BASE_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        await human_wait()

        locator = page.locator(selectors.STORE_LOCATOR_LINK).first
        target_url = None
        try:
            if await locator.count() > 0:
                target_url = await locator.get_attribute("href")
        except Exception:
            target_url = None

        if target_url:
            await page.goto(urljoin(BASE_URL, target_url), wait_until="domcontentloaded")
        else:
            try:
                await locator.click()
            except Exception:
                pass
        await page.wait_for_load_state("networkidle")
        await human_wait()

        stores: dict[tuple[str, str], dict[str, str]] = {}

        async def _collect_current_results() -> None:
            items = page.locator(selectors.STORE_RESULT_ITEM)
            try:
                count = await items.count()
            except Exception:
                count = 0
            for idx in range(count):
                item = items.nth(idx)
                text = await inner_text_safe(item)
                zip_code = await _extract_zip(item, text)
                if not zip_code:
                    continue
                name = await _extract_store_name(item, text)
                key = (name, zip_code)
                if key not in stores:
                    stores[key] = {"name": name, "zip": zip_code}

        for state_name in ("Washington", "Oregon"):
            search = page.locator(selectors.STORE_SEARCH_INPUT).first
            try:
                await search.wait_for(state="visible", timeout=10000)
            except Exception as exc:
                raise RuntimeError(
                    f"Store locator search input unavailable for {state_name}."
                ) from exc

            try:
                await search.fill("")
            except Exception:
                pass
            await human_wait(300, 600)
            await search.fill(state_name)
            await human_wait(300, 600)

            submitted = False
            try:
                await search.press("Enter")
                submitted = True
            except Exception:
                submitted = False

            if not submitted:
                try:
                    await page.keyboard.press("Enter")
                    submitted = True
                except Exception:
                    submitted = False

            if not submitted:
                try:
                    submit_button = page.get_by_role(
                        "button", name=re.compile("search|find", re.I)
                    )
                    await submit_button.first.click()
                    submitted = True
                except Exception:
                    submitted = False

            if not submitted:
                raise RuntimeError(
                    f"Unable to submit store search for {state_name}."
                )

            await page.wait_for_timeout(1500)
            await page.wait_for_load_state("networkidle")
            await human_wait()

            while True:
                await _collect_current_results()
                advanced = await paginate_or_scroll(page, selectors.NEXT_BTN)
                if not advanced:
                    break
                await page.wait_for_load_state("networkidle")
                await human_wait()
            await page.goto(page.url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")

        return sorted(stores.values(), key=lambda entry: (entry["zip"], entry["name"].lower()))
    finally:
        await _safe_close(context, browser)


def write_catalog_yaml(path: str | Path, categories: Iterable[dict[str, str]]) -> None:
    """Persist catalog categories to *path* in YAML format."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"categories": list(categories)}
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def write_zips_yaml(path: str | Path, stores: Iterable[dict[str, str]]) -> None:
    """Persist store ZIP codes derived from *stores* to YAML."""

    unique_zips = sorted({store["zip"] for store in stores if store.get("zip")})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"zips": unique_zips}
    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


async def _safe_close(context: Any, browser: Any) -> None:
    try:
        await context.close()
    except Exception:
        pass
    try:
        await browser.close()
    except Exception:
        pass


async def _extract_store_name(item, text: str | None) -> str:
    if text:
        first_line = text.strip().splitlines()[0].strip()
        if first_line:
            return first_line
    try:
        name_attr = await item.get_attribute("data-name")
        if name_attr:
            return name_attr.strip()
    except Exception:
        pass
    return "Unknown Store"


async def _extract_zip(item, text: str | None) -> str | None:
    if text:
        match = _ZIP_RE.search(text)
        if match:
            return match.group(1)
    try:
        zip_attr = await item.get_attribute("data-zip")
        if zip_attr:
            match = _ZIP_RE.search(zip_attr)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None
