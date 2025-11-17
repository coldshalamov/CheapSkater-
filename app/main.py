"""Command-line interface entry point for the CheapSkater application."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import re
import threading
import time
from typing import Any, Iterable
import random
import shutil
import sqlite3
import sys

import requests
import uvicorn
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Error as PlaywrightError

from app.catalog.discover_lowes import (
    discover_categories,
    discover_stores_WA_OR,
    write_catalog_yaml,
    write_zips_yaml,
)
from app.alerts.notifier import Notifier
from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors import schemas
from app.extractors.dom_utils import human_wait
from app.logging_config import get_logger
from app.health import HealthMonitor, HealthState
from app.normalizers import normalize_availability
from app.retailers.lowes import run_for_zip
from app.storage import repo
from app.storage.db import check_quarantine_table, get_engine, init_db_safe, make_session
from app.storage.models_sql import Alert, Observation
import app.selectors as selectors
from app.playwright_env import (
    apply_stealth,
    close_browser,
    launch_browser,
    selector_validation_skipped,
    zip_delay_bounds,
)


LOGGER = get_logger(__name__)


class PreflightError(RuntimeError):
    """Raised when the environment is not ready for scraping."""


DEFAULT_CONFIG: dict[str, Any] = {
    "retailers": {
        "lowes": {
            "enabled": True,
            "zips": [
                "98101",
                "98115",
                "98052",
                "98402",
                "99201",
                "98661",
                "97204",
                "97223",
                "97005",
                "97301",
                "97401",
                "97702",
            ],
            "catalog_path": "catalog/building_materials.lowes.yml",
        }
    },
    "output": {
        "csv_path": "outputs/orwa_items.csv",
        "sqlite_path": "orwa_lowes.sqlite",
    },
    "schedule": {"minutes": 180},
    "alerts": {"pct_drop": 0.25, "abs_thresholds": {}},
    "material_keywords": [
        "roofing",
        "drywall",
        "sheetrock",
        "insulation",
        "lumber",
        "plywood",
        "flooring",
        "tile",
        "deck",
        "fence",
        "concrete",
        "cement",
        "mortar",
        "siding",
        "trim",
        "moulding",
        "plumbing",
        "electrical",
        "hardware",
        "tool",
        "back aisle",
    ],
    "quarantine_retention_days": 7,
    "healthcheck_url": "",
    "max_concurrency": 3,
}

def _parse_threshold(env_suspect: str, env_block: str, default_suspect: int, default_block: int) -> tuple[int, int]:
    suspect = max(1, int(os.getenv(env_suspect, str(default_suspect))))
    block = int(os.getenv(env_block, str(default_block)))
    if block <= suspect:
        block = suspect + 1
    return suspect, block


BROWSER_RECOVERY_ATTEMPTS = max(0, int(os.getenv("BROWSER_RECOVERY_ATTEMPTS", "2")))
BROWSER_RESTART_DELAY = float(os.getenv("BROWSER_RESTART_DELAY", "6"))
HEALTH_LOG_FILE = Path(os.getenv("HEALTH_LOG_FILE", "logs/health.log"))
ZERO_THRESHOLDS = _parse_threshold("HEALTH_ZERO_SUSPECT", "HEALTH_ZERO_BLOCK", 3, 6)
HTTP_THRESHOLDS = _parse_threshold("HEALTH_HTTP_SUSPECT", "HEALTH_HTTP_BLOCK", 2, 4)
DOM_THRESHOLDS = _parse_threshold("HEALTH_DOM_SUSPECT", "HEALTH_DOM_BLOCK", 2, 4)


SELECTOR_VALIDATION_URL = "https://www.lowes.com/"


@dataclass
class ProcessingStats:
    processed: int = 0
    valid: int = 0
    quarantined: int = 0
    duplicates: int = 0
    reasons: Counter[str] = field(default_factory=Counter)


async def _zip_pause() -> None:
    """Global pacing hook between ZIPs to avoid bursty traffic."""

    min_ms, max_ms = zip_delay_bounds()
    if max_ms <= 0:
        return
    await human_wait(min_ms, max_ms, obey_policy=False)


async def validate_selectors() -> dict[str, Any]:
    """Validate known selectors against the Lowe's homepage."""

    counts: dict[str, int] = {}
    errors: list[str] = []
    selector_skip = getattr(selectors, "NON_SELECTOR_CONSTANTS", set())

    if selector_validation_skipped():
        LOGGER.info("Selector validation skipped via CHEAPSKATER_SKIP_PREFLIGHT")
        return {"counts": counts, "errors": errors}

    async with async_playwright() as playwright:
        apply_stealth(playwright)
        browser, persistent_context = await launch_browser(playwright)
        page = (
            await persistent_context.new_page()
            if persistent_context is not None
            else await browser.new_page()
        )
        try:
            await page.goto(SELECTOR_VALIDATION_URL, wait_until="networkidle")
            await human_wait(0.5, 1.5)
        except Exception as exc:  # pragma: no cover - network issues
            message = (
                f"Failed to load {SELECTOR_VALIDATION_URL}: {exc}"
            )
            LOGGER.error(message)
            errors.append(message)
            try:
                await browser.close()
            finally:
                return {"counts": counts, "errors": errors}

        try:
            for name in dir(selectors):
                if not name.isupper():
                    continue
                if name in selector_skip:
                    continue
                selector_value = getattr(selectors, name)
                if not isinstance(selector_value, str):
                    continue
                try:
                    count = await page.locator(selector_value).count()
                    counts[name] = count
                    if count == 0:
                        message = (
                            f"Selector '{name}' returned 0 matches at {SELECTOR_VALIDATION_URL}"
                        )
                        LOGGER.error(message)
                        errors.append(message)
                except Exception as exc:  # pragma: no cover - selector issues
                    counts[name] = 0
                    error_message = (
                        f"Selector '{name}' evaluation failed: {exc}"
                    )
                    LOGGER.exception(
                        "Selector '%s' evaluation failed", name, exc_info=exc
                    )
                    errors.append(error_message)
        finally:
            await close_browser(browser, persistent_context)

    return {"counts": counts, "errors": errors}


async def preflight_check(config: dict[str, Any]) -> None:
    """Validate environment prerequisites prior to running a scrape (async-safe)."""

    skip_browser = os.environ.get("CHEAPSKATER_SKIP_PREFLIGHT") == "1"

    errors: list[str] = []

    required_paths: set[Path] = {Path("requirements.txt")}
    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})

    catalog_path_value = lowes_conf.get("catalog_path")
    if catalog_path_value:
        required_paths.add(_resolve_config_path(catalog_path_value))
    zips_path_value = lowes_conf.get("zips_path")
    if zips_path_value:
        required_paths.add(_resolve_config_path(zips_path_value))

    for path in sorted(required_paths):
        if not path.exists():
            errors.append(f"Required file missing: {path}")

    sqlite_target = _resolve_config_path(
        config.get("output", {}).get("sqlite_path", "orwa_lowes.sqlite")
    )
    sqlite_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(sqlite_target)
        try:
            connection.execute("PRAGMA journal_mode")
        finally:
            connection.close()
    except Exception as exc:
        errors.append(f"SQLite database not writable at {sqlite_target}: {exc}")

    try:
        response = requests.get("https://www.lowes.com/", timeout=5)
        if response.status_code >= 400:
            errors.append(
                "Network check to https://www.lowes.com/ returned "
                f"HTTP {response.status_code}"
            )
    except Exception as exc:  # pragma: no cover - network failures
        errors.append(f"Unable to reach https://www.lowes.com/: {exc}")

    try:
        disk_path = sqlite_target.parent if sqlite_target.parent.exists() else Path.cwd()
        disk_usage = shutil.disk_usage(disk_path)
        if disk_usage.free < 1_000_000_000:
            errors.append(
                f"Insufficient free disk space at {disk_path} "
                f"({disk_usage.free / (1024 ** 3):.2f} GiB available)"
            )
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"Unable to determine free disk space: {exc}")

    if sys.version_info < (3, 11):
        errors.append(
            "Python 3.11 or newer is required. "
            f"Detected {sys.version_info.major}.{sys.version_info.minor}"
        )

    selector_errors: list[str] = []
    if not skip_browser:
        try:
            async with async_playwright() as p:
                apply_stealth(p)
                browser, persistent_context = await launch_browser(p)
                try:
                    context = (
                        persistent_context
                        if persistent_context is not None
                        else await browser.new_context()
                    )
                    page = await context.new_page()
                    await page.set_content("<html><body></body></html>")
                    # Syntactic sanity-check for selectors. Do NOT require matches.
                    selector_skip = getattr(
                        selectors, "NON_SELECTOR_CONSTANTS", set()
                    )
                    for name in dir(selectors):
                        if not name.isupper():
                            continue
                        if name in selector_skip:
                            continue
                        selector_value = getattr(selectors, name)
                        if not isinstance(selector_value, str) or not selector_value.strip():
                            continue
                        try:
                            _ = await page.query_selector_all(selector_value)
                        except Exception as exc:
                            selector_errors.append(f"Selector '{name}' invalid: {exc}")
                finally:
                    await close_browser(browser, persistent_context)
        except Exception as exc:
            selector_errors.append(f"Selector validation failed: {exc}")

    errors.extend(selector_errors)
    if errors:
        raise PreflightError("; ".join(errors))


def _increment_quarantine(stats: ProcessingStats, label: str) -> None:
    stats.quarantined += 1
    stats.reasons[label] += 1


def _format_quarantine_summary(reasons: Counter[str], total: int) -> str:
    if total <= 0:
        return "Quarantined: 0 items"
    parts = [f"{count} {label}" for label, count in reasons.most_common()]
    return f"Quarantined: {total} items ({', '.join(parts)})"


def generate_test_data(session_factory, *, item_count: int = 100) -> None:
    """Populate the database with synthetic observations for testing."""

    session = None
    stores = [
        ("wa-seattle", "Lowe's of Seattle", "98101", "Seattle", "WA"),
        ("wa-bellevue", "Lowe's of Bellevue", "98004", "Bellevue", "WA"),
        ("or-portland", "Lowe's of Portland", "97204", "Portland", "OR"),
        ("or-salem", "Lowe's of Salem", "97301", "Salem", "OR"),
    ]
    categories = [
        "Roofing",
        "Lumber",
        "Flooring",
        "Plumbing",
        "Electrical",
        "Hardware",
    ]

    now = datetime.now(timezone.utc)

    try:
        session = session_factory()
        for store_id, name, zip_code, city, state in stores:
            repo.upsert_store(
                session,
                store_id,
                name,
                zip_code,
                city=city,
                state=state,
            )

        for index in range(item_count):
            store_id, store_name, zip_code, _, _ = random.choice(stores)
            category = random.choice(categories)
            sku = f"FAKE{index:05d}"
            title = f"Test Item {index:03d}"
            price = round(random.uniform(5.0, 500.0), 2)
            previous_price = price + round(random.uniform(1.0, 50.0), 2)
            pct_off = round((previous_price - price) / previous_price, 2)
            product_url = f"https://example.com/product/{sku}"

            repo.upsert_item(
                session,
                sku,
                "lowes",
                title,
                category,
                product_url,
                image_url=f"https://example.com/images/{sku}.jpg",
            )

            observation = Observation(
                ts_utc=now - timedelta(minutes=random.randint(0, 720)),
                retailer="lowes",
                store_id=store_id,
                store_name=store_name,
                zip=zip_code,
                sku=sku,
                title=title,
                category=category,
                price=price,
                price_was=previous_price,
                pct_off=pct_off,
                availability="In Stock",
                product_url=product_url,
                image_url=f"https://example.com/images/{sku}.jpg",
                clearance=True,
            )
            repo.insert_observation(session, observation)
            repo.update_price_history(
                session,
                retailer="lowes",
                store_id=store_id,
                sku=sku,
                title=title,
                category=category,
                ts_utc=observation.ts_utc,
                price=price,
                price_was=previous_price,
                pct_off=pct_off,
                availability="In Stock",
                product_url=product_url,
                image_url=f"https://example.com/images/{sku}.jpg",
                clearance=True,
            )

        session.commit()
        LOGGER.info("Generated %d synthetic items for testing", item_count)
    except Exception:
        if session is not None:
            session.rollback()
        raise
    finally:
        if session is not None:
            session.close()


def _record_selector_quarantine(
    session_factory,
    stats: ProcessingStats,
    *,
    zip_code: str,
    category: str | None,
    url: str | None,
    error: Exception,
    dry_run: bool,
) -> None:
    _increment_quarantine(stats, "selector changed")
    if dry_run:
        return

    session = None
    try:
        session = session_factory()
        repo.insert_quarantine(
            session,
            retailer="lowes",
            store_id=None,
            sku=None,
            zip_code=zip_code,
            state=_infer_state_from_zip(zip_code),
            category=category,
            reason="selector_changed",
            payload={
                "error": str(error),
                "url": url,
                "category": category,
                "zip": zip_code,
            },
        )
        session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning(
            "Failed to record selector quarantine | zip=%s | category=%s | error=%s",
            zip_code,
            category or "unknown",
            exc,
        )
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            LOGGER.debug("Session closed")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the application."""

    parser = argparse.ArgumentParser(
        description="Run the CheapSkater price monitoring pipeline."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the pipeline a single time instead of on a schedule.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Quick sanity check: scrape one category at one ZIP and exit.",
    )
    parser.add_argument(
        "--discover-categories",
        action="store_true",
        help="Run catalog discovery for Lowe's and write catalog/all.lowes.yml.",
    )
    parser.add_argument(
        "--discover-stores",
        action="store_true",
        help="Discover all WA/OR Lowe's stores and write catalog/wa_or_stores.yml.",
    )
    parser.add_argument(
        "--zip",
        "--zips",
        dest="zips",
        type=str,
        help="Comma-separated list of ZIP codes to override configuration values.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of ZIP codes to process concurrently (default: 3).",
    )
    parser.add_argument(
        "--categories",
        dest="categories_filter",
        type=str,
        help="Regex/substring filter applied to catalog category names (case-insensitive).",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start the FastAPI dashboard on port 8000 while the scraper runs.",
    )
    parser.add_argument(
        "--generate-test-data",
        action="store_true",
        help="Populate the database with synthetic data and exit.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run the pipeline without persisting data to the database.",
    )
    parser.add_argument(
        "--ignore-quarantine",
        action="store_true",
        help="Retry categories that were previously quarantined.",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.concurrency is None or args.concurrency <= 0:
        parser.error("--concurrency must be a positive integer")

    zip_arg = args.zips or ""
    args.zips = [zip_code.strip() for zip_code in zip_arg.split(",") if zip_code.strip()]

    pattern_text = (args.categories_filter or "").strip()
    if pattern_text:
        try:
            args.categories_pattern = re.compile(pattern_text, re.IGNORECASE)
        except re.error as exc:
            parser.error(f"Invalid --categories pattern: {exc}")
    else:
        args.categories_pattern = None

    args.categories_filter = None
    return args


def _deep_merge(default: Any, override: Any) -> Any:
    if not isinstance(default, dict) or not isinstance(override, dict):
        return deepcopy(override)

    merged: dict[str, Any] = deepcopy(default)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _validate_material_keywords(raw_value: Any) -> None:
    if raw_value is None:
        LOGGER.warning("material_keywords missing in configuration; using defaults")
        return

    if isinstance(raw_value, (list, tuple, set)):
        cleaned = [str(item).strip() for item in raw_value if str(item).strip()]
        if not cleaned:
            LOGGER.warning(
                "material_keywords is empty after cleanup; using defaults",
            )
        return

    LOGGER.warning(
        "material_keywords must be a sequence of strings; using defaults",
    )


def _load_config(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    else:
        LOGGER.warning("Configuration file %s not found; using defaults", path)
        data = {}

    merged = _deep_merge(DEFAULT_CONFIG, data) if data else deepcopy(DEFAULT_CONFIG)
    _validate_material_keywords(merged.get("material_keywords"))
    return merged


def _load_catalog(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Catalog file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    categories = data.get("categories") or []
    cleaned: list[dict[str, str]] = []
    for entry in categories:
        name = str((entry or {}).get("name", "")).strip()
        url = str((entry or {}).get("url", "")).strip()
        if name and url:
            cleaned.append({"name": name, "url": url})
    if not cleaned:
        raise RuntimeError(f"No categories defined in catalog: {path}")
    return cleaned


def _resolve_config_path(path_value: str | Path | None) -> Path:
    if not path_value:
        raise RuntimeError("Missing configuration path value.")
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _resolve_catalog_path(config: dict[str, Any]) -> Path:
    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    catalog_value = lowes_conf.get("catalog_path") or config.get("catalog_path")
    if not catalog_value:
        raise RuntimeError("catalog_path is missing in app/config.yml")
    return _resolve_config_path(catalog_value)


def _load_zips_file(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"ZIP file not found: {path}. Run `python -m app.main --discover-stores` first."
        )
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    zips = [str(z).strip() for z in data.get("zips", []) if str(z).strip()]
    if not zips:
        raise RuntimeError(f"No ZIP codes defined in {path}")
    return zips


def _load_store_directory(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    entries = data.get("stores") or []
    directory: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        zip_code = str(entry.get("zip") or "").strip()
        store_id = str(entry.get("store_id") or "").strip()
        store_name = (entry.get("store_name") or entry.get("name") or "").strip()
        if not zip_code:
            continue
        payload: dict[str, str] = {}
        if store_id:
            payload["store_id"] = store_id
        if store_name:
            payload["store_name"] = store_name
        directory.setdefault(zip_code, []).append(payload)
    return directory


def _filter_categories(
    categories: list[dict[str, str]], pattern: re.Pattern[str] | None
) -> list[dict[str, str]]:
    if pattern is None:
        return categories
    filtered: list[dict[str, str]] = []
    for category in categories:
        name = category.get("name", "")
        if pattern.search(name):
            filtered.append(category)
    return filtered


def _resolve_zips(args: argparse.Namespace, config: dict[str, Any]) -> list[str]:
    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    if args.zips:
        return [zip_code for zip_code in args.zips if zip_code]

    zips_path = lowes_conf.get("zips_path")
    if zips_path:
        path = _resolve_config_path(zips_path)
        return _load_zips_file(path)

    base = [str(z) for z in lowes_conf.get("zips", [])]
    zips = [zip_code for zip_code in base if zip_code]
    if not zips:
        raise RuntimeError("No ZIP codes configured. Provide zips or run discovery.")
    return zips


def _load_zip_resume(zips: list[str]) -> tuple[list[str], str | None]:
    if not ZIP_RESUME_ENABLED:
        return zips, None
    try:
        data = json.loads(ZIP_CURSOR_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return zips, None
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Unable to read zip cursor file %s: %s", ZIP_CURSOR_FILE, exc)
        return zips, None
    last_zip = data.get("last_zip")
    if not last_zip or last_zip not in zips:
        return zips, None
    idx = zips.index(last_zip)
    if idx == len(zips) - 1:
        return zips, last_zip
    rotated = zips[idx + 1 :] + zips[: idx + 1]
    return rotated, last_zip


def _persist_zip_cursor(zip_code: str) -> None:
    if not ZIP_RESUME_ENABLED:
        return
    try:
        ZIP_CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_zip": zip_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        ZIP_CURSOR_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Unable to write zip cursor file %s: %s", ZIP_CURSOR_FILE, exc)

def _resolve_store_hints(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    zips_path = lowes_conf.get("zips_path")
    if not zips_path:
        return {}
    path = _resolve_config_path(zips_path)
    return _load_store_directory(path)


def _get_pct_threshold(config: dict[str, Any]) -> float:
    try:
        value = float(config.get("alerts", {}).get("pct_drop", 0.25) or 0.25)
    except (TypeError, ValueError):
        value = 0.25
    if value <= 0:
        return 0.25
    return value


def _infer_state_from_zip(zip_code: str | None) -> str:
    if not zip_code:
        return "UNKNOWN"
    digits = "".join(ch for ch in zip_code if ch.isdigit())
    if len(digits) < 3:
        return "UNKNOWN"
    prefix = int(digits[:3])
    if 970 <= prefix <= 979:
        return "OR"
    if 980 <= prefix <= 994:
        return "WA"
    return "UNKNOWN"


def _derive_sku(raw_sku: str | None, product_url: str) -> str | None:
    candidate = (raw_sku or "").strip()
    if candidate:
        return candidate
    match = re.search(r"(\d{5,})", product_url)
    return match.group(1) if match else None


def _normalize_product_url(product_url: str | None) -> str:
    url = (product_url or "").strip()
    if url.startswith("/"):
        url = f"https://www.lowes.com{url}"
    return url


def _extract_identifiers(row: dict[str, Any]) -> tuple[str | None, str]:
    product_url = _normalize_product_url(row.get("product_url"))
    sku = _derive_sku(row.get("sku"), product_url)
    canonical = sku or (product_url or None)
    return canonical, product_url


_BUILDING_MATERIAL_KEYWORDS = {
    "roof",
    "drywall",
    "sheetrock",
    "insulation",
    "lumber",
    "plywood",
    "floor",
    "tile",
    "deck",
    "fence",
    "concrete",
    "cement",
    "mortar",
    "siding",
    "door",
    "window",
    "trim",
    "moulding",
    "paint",
    "primer",
    "plumbing",
    "pipe",
    "fixture",
    "electrical",
    "lighting",
    "hardware",
    "tool",
    "fastener",
    "cement board",
    "roofing",
    "joist",
    "beam",
    "stud",
    "sheathing",
    "back aisle",
}


_MATERIAL_KEYWORDS: set[str] = set(_BUILDING_MATERIAL_KEYWORDS)


def _configure_material_keywords(config: dict[str, Any]) -> None:
    """Load building-material keywords from *config* into module state."""

    global _MATERIAL_KEYWORDS

    candidates = config.get("material_keywords")
    if isinstance(candidates, (list, tuple, set)):
        cleaned = {
            str(keyword).strip().lower()
            for keyword in candidates
            if str(keyword).strip()
        }
        if cleaned:
            _MATERIAL_KEYWORDS = cleaned
            return

    _MATERIAL_KEYWORDS = set(_BUILDING_MATERIAL_KEYWORDS)


def _is_building_material_category(category: str) -> bool:
    """Return True when *category* is relevant to building materials."""

    normalized = (category or "").strip().lower()
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _MATERIAL_KEYWORDS)


_LOWES_PREFIX_RE = re.compile(r"(?i)^l\s*owe'?s(?:\s+home\s+improvement)?(?:\s+of)?\s*")
_STATE_SUFFIX_RE = re.compile(r"(?i)\b(?:washington|oregon|wa|or)\b")


def _derive_city_from_store_name(store_name: str | None) -> str:
    """Return a best-effort city name extracted from a Lowe's store label."""

    if not store_name:
        return "Unknown"

    name = store_name.strip()
    if not name:
        return "Unknown"

    name = _LOWES_PREFIX_RE.sub("", name)
    name = re.sub(r"(?i)home\s*center", "", name)
    name = re.sub(r"(?i)store\s*#?\d+", "", name)

    candidates = [
        segment.strip()
        for segment in re.split(r"[|\-/–]|,|\(|\)", name)
        if segment.strip()
    ]

    for candidate in candidates:
        cleaned = _STATE_SUFFIX_RE.sub("", candidate)
        cleaned = re.sub(r"\d", "", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            return cleaned.title()

    cleaned_name = _STATE_SUFFIX_RE.sub("", name)
    cleaned_name = re.sub(r"\d", "", cleaned_name).strip()
    return cleaned_name.title() if cleaned_name else "Unknown"


async def _run_cycle(
    args: argparse.Namespace,
    config: dict[str, Any],
    categories: list[dict[str, str]],
    session_factory,
    notifier: Notifier,
) -> tuple[int, int]:
    await preflight_check(config)

    start = time.monotonic()
    total_items = 0
    total_alerts = 0
    stats = ProcessingStats()
    dry_run = bool(getattr(args, "validate", False) or getattr(args, "probe", False))

    zips = _resolve_zips(args, config)
    resume_enabled = (
        ZIP_RESUME_ENABLED
        and not dry_run
        and not args.probe
        and not getattr(args, "zips", None)
    )
    zip_timeout_seconds = max(60.0, ZIP_PROGRESS_TIMEOUT_MINUTES * 60.0)
    browser_restart_interval = 0 if args.probe else BROWSER_ZIP_RESTART_LIMIT
    if resume_enabled:
        zips, resume_marker = _load_zip_resume(zips)
        if resume_marker:
            LOGGER.info("Resuming ZIP queue after %s", resume_marker)
    store_hints = _resolve_store_hints(args, config)

    if not zips:
        LOGGER.warning("No ZIP codes configured; skipping cycle")
        return total_items, total_alerts

    categories_to_use = list(categories)
    if not categories_to_use:
        LOGGER.warning("No categories available; skipping cycle")
        return total_items, total_alerts

    if not getattr(args, "ignore_quarantine", False):
        session = None
        quarantined_categories: set[str] = set()
        try:
            session = session_factory()
            quarantined_categories = set(
                repo.list_quarantined_categories(
                    session, retailer="lowes", reason="selector_changed"
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to load quarantined categories: %s", exc)
        finally:
            try:
                if session is not None:
                    session.close()
            finally:
                LOGGER.debug("Session closed")

        if quarantined_categories:
            filtered_categories = [
                entry
                for entry in categories_to_use
                if entry.get("name") not in quarantined_categories
            ]
            skipped = len(categories_to_use) - len(filtered_categories)
            if skipped > 0:
                LOGGER.info(
                    "Skipping %d quarantined categories: %s",
                    skipped,
                    ", ".join(sorted(quarantined_categories)),
                )
            categories_to_use = filtered_categories

    if not categories_to_use:
        LOGGER.warning(
            "No categories available after quarantine filtering; skipping cycle"
        )
        return total_items, total_alerts

    pct_threshold = _get_pct_threshold(config)
    abs_map_raw = (config.get("alerts") or {}).get("abs_thresholds") or {}
    if isinstance(abs_map_raw, dict):
        abs_map = {
            (key or "").strip().lower(): value for key, value in abs_map_raw.items()
        }
    else:
        abs_map = {}

    LOGGER.info(
        "Starting run cycle | retailer=lowes | zips=%d | categories=%d",
        len(zips),
        len(categories_to_use),
    )

    any_zip_success = False
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    health_monitor = HealthMonitor(
        run_id=run_id,
        log_path=HEALTH_LOG_FILE,
        zero_threshold=ZERO_THRESHOLDS,
        http_threshold=HTTP_THRESHOLDS,
        dom_threshold=DOM_THRESHOLDS,
    )

    try:
        if args.probe:
            validation = await validate_selectors()
            card_count = validation["counts"].get("CARD", 0)
            if validation["errors"]:
                print(
                    json.dumps(
                        {"status": "scrape_error", "reason": "selector_validation"},
                        ensure_ascii=False,
                    )
                )
                return 0, 0

            target_zip = zips[0]
            target_category = categories_to_use[0]
            category_name = target_category.get("name", "unknown")
            LOGGER.info(
                "Probe mode | zip=%s | category=%s",
                target_zip,
                category_name,
            )

            async with async_playwright() as playwright:
                apply_stealth(playwright)
                browser, persistent_context = await launch_browser(playwright)
                try:
                    try:
                        rows = await run_for_zip(
                            playwright,
                            target_zip,
                            [target_category],
                            clearance_threshold=pct_threshold,
                            browser=browser,
                            shared_context=persistent_context,
                            store_hints=store_hints,
                        )
                    except StoreContextError as exc:
                        LOGGER.error(
                            "Probe failed to set store context for zip=%s: %s",
                            target_zip,
                            exc,
                        )
                        print(
                            json.dumps(
                                {"status": "scrape_error", "reason": "store_context"},
                                ensure_ascii=False,
                            )
                        )
                        return 0, 0
                    except SelectorChangedError as exc:
                        LOGGER.error(
                            "Probe selector failure | zip=%s | category=%s | url=%s | error=%s",
                            target_zip,
                            getattr(exc, "category", category_name),
                            getattr(exc, "url", "unknown"),
                            exc,
                        )
                        _record_selector_quarantine(
                            session_factory,
                            stats,
                            zip_code=target_zip,
                            category=getattr(exc, "category", None),
                            url=getattr(exc, "url", None),
                            error=exc,
                            dry_run=True,
                        )
                        print(
                            json.dumps(
                                {"status": "scrape_error", "reason": "selector_changed"},
                                ensure_ascii=False,
                            )
                        )
                        return 0, 0
                    except PageLoadError as exc:
                        LOGGER.error(
                            "Probe page load error | zip=%s | category=%s | url=%s | error=%s",
                            target_zip,
                            getattr(exc, "category", category_name),
                            getattr(exc, "url", "unknown"),
                            exc,
                        )
                        print(
                            json.dumps(
                                {"status": "scrape_error", "reason": "page_load"},
                                ensure_ascii=False,
                            )
                        )
                        return 0, 0

                    if not rows:
                        LOGGER.warning(
                            "Probe returned zero rows | zip=%s | category=%s",
                            target_zip,
                            category_name,
                        )
                        print(
                            json.dumps(
                                {"status": "scrape_error", "reason": "empty"},
                                ensure_ascii=False,
                            )
                        )
                        return 0, 0

                    processed_items = 0
                    processed_alerts = 0
                    seen_keys: set[tuple[str, str | None]] = set()
                    for row in rows[:5]:
                        stats.processed += 1
                        canonical, _ = _extract_identifiers(row)
                        key = (target_zip, canonical)
                        if canonical and key in seen_keys:
                            stats.duplicates += 1
                            continue
                        if canonical:
                            seen_keys.add(key)
                        items, alerts = await _process_row(
                            row,
                            target_zip,
                            session_factory,
                            notifier,
                            pct_threshold,
                            abs_map,
                            stats=stats,
                            dry_run=True,
                        )
                        processed_items += items
                        processed_alerts += alerts

                    LOGGER.info(
                        "Probe complete | zip=%s | category=%s | scraped=%d | processed=%d | alerts=%d",
                        target_zip,
                        category_name,
                        len(rows),
                        processed_items,
                        processed_alerts,
                    )
                    print(
                        json.dumps(
                            {
                                "status": "ok",
                                "items": processed_items,
                                "alerts": processed_alerts,
                            },
                            ensure_ascii=False,
                        )
                    )
                    return processed_items, processed_alerts
                finally:
                    await close_browser(browser, persistent_context)

        async with async_playwright() as playwright:
            apply_stealth(playwright)
            browser, persistent_context = await launch_browser(playwright)

            raw_max = config.get("max_concurrency", 3)
            try:
                configured_max = int(raw_max)
            except (TypeError, ValueError):
                configured_max = 3
            if configured_max <= 0:
                configured_max = 3

            desired = args.concurrency or configured_max
            effective_concurrency = max(1, min(desired, configured_max))
            if persistent_context is not None and effective_concurrency > 1:
                LOGGER.warning(
                    "Persistent Chromium profile detected; forcing concurrency=1 to avoid session conflicts"
                )
                effective_concurrency = 1
            LOGGER.debug("Using concurrency=%s (max=%s)", effective_concurrency, configured_max)
            semaphore = asyncio.Semaphore(effective_concurrency)
            browser_restart_lock = asyncio.Lock()

            async def _restart_browser(reason: str) -> None:
                nonlocal browser, persistent_context
                async with browser_restart_lock:
                    LOGGER.warning("Restarting Playwright browser (%s)", reason)
                    await close_browser(browser, persistent_context)
                    health_monitor.record_browser_restart(reason=reason)
                    browser, persistent_context = await launch_browser(playwright)

            async def _scrape_zip_with_recovery(
                zip_code: str,
                *,
                zip_extra: dict[str, Any],
            ) -> list[dict[str, Any]]:
                attempts = 0
                while True:
                    try:
                        return await run_for_zip(
                            playwright,
                            zip_code,
                            categories_to_use,
                            clearance_threshold=pct_threshold,
                            browser=browser,
                            shared_context=persistent_context,
                            store_hints=store_hints,
                        )
                    except PlaywrightError as exc:
                        attempts += 1
                        health_monitor.record_http_error(
                            zip_code=zip_code,
                            reason="playwright_error",
                            details={"attempt": attempts, "message": str(exc)},
                        )
                        LOGGER.warning(
                            "Playwright failure scraping zip %s attempt %s/%s: %s",
                            zip_code,
                            attempts,
                            max(1, BROWSER_RECOVERY_ATTEMPTS),
                            exc,
                            extra=zip_extra,
                        )
                        if attempts > BROWSER_RECOVERY_ATTEMPTS:
                            raise
                        await _restart_browser("playwright_error")
                        if BROWSER_RESTART_DELAY > 0:
                            await asyncio.sleep(BROWSER_RESTART_DELAY)

            async def _process_zip(zip_code: str) -> tuple[int, int, bool]:
                async with semaphore:
                    try:
                        zip_extra = {"zip": zip_code}
                        rows = await _scrape_zip_with_recovery(
                            zip_code,
                            zip_extra=zip_extra,
                        )
                    except StoreContextError as exc:
                        LOGGER.error(
                            "Unable to set store for ZIP %s: %s",
                            zip_code,
                            exc,
                            extra=zip_extra,
                        )
                        health_monitor.record_dom_error(
                            zip_code=zip_code,
                            reason="store_context_error",
                            details={"message": str(exc)},
                        )
                        return 0, 0, False
                    except SelectorChangedError as exc:
                        extra = {
                            "zip": zip_code,
                            "category": getattr(exc, "category", None),
                            "url": getattr(exc, "url", None),
                        }
                        LOGGER.warning(
                            "No products parsed for ZIP %s (category=%s url=%s): %s",
                            zip_code,
                            extra["category"] or "unknown",
                            extra["url"] or "unknown",
                            exc,
                            extra=extra,
                        )
                        _record_selector_quarantine(
                            session_factory,
                            stats,
                            zip_code=zip_code,
                            category=extra["category"],
                            url=extra["url"],
                            error=exc,
                            dry_run=dry_run,
                        )
                        health_monitor.record_dom_error(
                            zip_code=zip_code,
                            reason="selector_changed",
                            details=extra,
                        )
                        return 0, 0, False
                    except PageLoadError as exc:
                        extra = {
                            "zip": zip_code,
                            "category": getattr(exc, "category", None),
                            "url": getattr(exc, "url", None),
                        }
                        LOGGER.warning(
                            "Page load error for ZIP %s (category=%s url=%s): %s",
                            zip_code,
                            extra["category"] or "unknown",
                            extra["url"] or "unknown",
                            exc,
                            extra=extra,
                        )
                        health_monitor.record_http_error(
                            zip_code=zip_code,
                            reason="page_load",
                            details=extra,
                        )
                        return 0, 0, False
                    except Exception as exc:  # pragma: no cover - defensive
                        LOGGER.exception(
                            "Unexpected failure scraping ZIP %s: %s",
                            zip_code,
                            exc,
                            extra=zip_extra,
                        )
                        health_monitor.record_http_error(
                            zip_code=zip_code,
                            reason="unexpected_error",
                            details={"message": str(exc)},
                        )
                        return 0, 0, False

                    else:
                        if not rows:
                            LOGGER.info(
                                "Scrape returned no rows for ZIP %s; continuing",
                                zip_code,
                                extra=zip_extra,
                            )
                            health_monitor.record_zero_items(
                                zip_code=zip_code,
                                message="run_for_zip returned no rows",
                            )
                            return 0, 0, True
                        else:
                            health_monitor.record_items(
                                zip_code=zip_code,
                                count=len(rows),
                            )
                            numeric_prices = [
                                (row.get("price") or 0)
                                for row in rows
                                if isinstance(row.get("price"), (int, float))
                            ]
                            if not numeric_prices:
                                health_monitor.record_data_anomaly(
                                    zip_code=zip_code,
                                    detail="all_prices_missing",
                                    metrics={"rows": len(rows)},
                                )
                            distinct_skus = {
                                (row.get("sku") or row.get("history_id"))
                                for row in rows
                                if row.get("sku") or row.get("history_id")
                            }
                            if len(distinct_skus) <= 1 and len(rows) >= 5:
                                health_monitor.record_data_anomaly(
                                    zip_code=zip_code,
                                    detail="single_sku_multiple_rows",
                                    metrics={"rows": len(rows)},
                                )

                        items = 0
                        alerts = 0
                        seen_keys: set[tuple[str, str | None]] = set()
                        for row in rows:
                            stats.processed += 1
                            canonical, _ = _extract_identifiers(row)
                            key = (zip_code, canonical)
                            if canonical and key in seen_keys:
                                stats.duplicates += 1
                                continue
                            if canonical:
                                seen_keys.add(key)
                            processed = await _process_row(
                                row,
                                zip_code,
                                session_factory,
                                notifier,
                                pct_threshold,
                                abs_map,
                                stats=stats,
                                dry_run=dry_run,
                            )
                            items += processed[0]
                            alerts += processed[1]
                        return items, alerts, True
                    finally:
                        await _zip_pause()
                        extra_delay = health_monitor.recommended_extra_delay()
                        if extra_delay > 0:
                            LOGGER.debug(
                                "Health state %s -> sleeping extra %.1fs",
                                health_monitor.state.value,
                                extra_delay,
                            )
                            await asyncio.sleep(extra_delay)

            zip_cursor_lock = asyncio.Lock()
            restart_counter_lock = asyncio.Lock()
            zips_since_restart = 0

            async def _process_zip_with_cursor(zip_code: str) -> tuple[int, int, bool]:
                nonlocal zips_since_restart
                try:
                    result = await asyncio.wait_for(
                        _process_zip(zip_code),
                        timeout=zip_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    LOGGER.error(
                        "ZIP %s timed out after %.1f minutes; restarting browser",
                        zip_code,
                        ZIP_PROGRESS_TIMEOUT_MINUTES,
                    )
                    await _restart_browser("zip_timeout")
                    result = (0, 0, False)
                if resume_enabled:
                    async with zip_cursor_lock:
                        _persist_zip_cursor(zip_code)
                if browser_restart_interval:
                    async with restart_counter_lock:
                        nonlocal zips_since_restart
                        zips_since_restart += 1
                        if zips_since_restart >= browser_restart_interval:
                            LOGGER.info(
                                "Restarting browser after %s ZIPs to avoid resource exhaustion",
                                browser_restart_interval,
                            )
                            await _restart_browser("zip_interval")
                            zips_since_restart = 0
                return result

            try:
                results = await asyncio.gather(
                    *(_process_zip_with_cursor(zip_code) for zip_code in zips)
                )
                for items, alerts, success in results:
                    total_items += items
                    total_alerts += alerts
                    any_zip_success = any_zip_success or success
            finally:
                await close_browser(browser, persistent_context)
    finally:
        duration = time.monotonic() - start

    LOGGER.info(
        "Processed %d rows: %d valid, %d quarantined, %d duplicates",
        stats.processed,
        stats.valid,
        stats.quarantined,
        stats.duplicates,
    )
    if stats.quarantined:
        summary = _format_quarantine_summary(stats.reasons, stats.quarantined)
        LOGGER.info(summary)
        if stats.processed and stats.quarantined / max(stats.processed, 1) > 0.1:
            rate = (stats.quarantined / stats.processed) * 100 if stats.processed else 0.0
            LOGGER.warning("High quarantine rate detected: %.1f%%", rate)

    if any_zip_success:
        if not dry_run:
            _export_csv(config, session_factory)
        _ping_healthcheck(config)
        LOGGER.info(
            "cycle ok | retailer=lowes | zips=%d | items=%d | alerts=%d | duration=%.1fs",
            len(zips),
            total_items,
            total_alerts,
            duration,
        )
    else:
        LOGGER.error(
            "cycle failed | retailer=lowes | zips=%d | items=%d | alerts=%d | duration=%.1fs",
            len(zips),
            total_items,
            total_alerts,
            duration,
        )
    return total_items, total_alerts


async def _process_row(
    row: dict[str, Any],
    zip_code: str,
    session_factory,
    notifier: Notifier,
    pct_threshold: float,
    abs_map: dict[str, Any],
    *,
    stats: ProcessingStats,
    dry_run: bool,
) -> tuple[int, int]:
    def _coerce_price(
        value: Any,
        field_name: str,
        *,
        required: bool,
    ) -> tuple[float | None, str | None]:
        if value is None:
            return (None, f"missing_{field_name}") if required else (None, None)
        if isinstance(value, (int, float)):
            v = float(value)
        elif isinstance(value, str):
            v = schemas.parse_price(value)
            if v is None:
                return None, f"invalid_{field_name}_format"
        else:
            return None, f"invalid_{field_name}_type"

        if v is None:
            return None, f"invalid_{field_name}_format"
        if v < 0.01 or v > 100_000:
            return None, f"out_of_range_{field_name}"
        return float(v), None

    def _quarantine_row(
        reason: str, payload: dict[str, Any], *, summary_label: str | None = None
    ) -> None:
        label = summary_label or reason.replace("_", " ")
        _increment_quarantine(stats, label)
        if dry_run:
            return

        session = None
        try:
            session = session_factory()
            repo.insert_quarantine(
                session,
                retailer="lowes",
                store_id=store_id,
                sku=canonical_sku,
                zip_code=store_zip,
                state=store_state,
                category=category,
                reason=reason,
                payload=payload,
            )
            session.commit()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception(
                "Failed to record quarantine for sku=%s: %s",
                canonical_sku,
                exc,
                extra={"zip": zip_code, "category": category, "url": product_url},
            )
        finally:
            try:
                if session is not None:
                    session.close()
            finally:
                LOGGER.debug("Session closed")

    title = (row.get("title") or "").strip()
    category = (row.get("category") or "").strip() or "Uncategorised"
    canonical_sku, product_url = _extract_identifiers(row)
    product_url = product_url or ""
    image_url = (row.get("image_url") or None)
    if isinstance(image_url, str):
        image_url = image_url.strip() or None

    canonical_sku = canonical_sku or product_url

    if not title or not product_url or not canonical_sku:
        LOGGER.debug(
            "Skipping row with insufficient data (sku=%s title=%s)",
            canonical_sku,
            title,
            extra={"zip": zip_code, "category": category, "url": product_url},
        )
        return 0, 0

    store_id_raw = (row.get("store_id") or "").strip()
    row_zip = (row.get("zip") or zip_code or "").strip()
    store_name_raw = (row.get("store_name") or "").strip()
    store_zip = row_zip or (zip_code or "").strip() or "00000"
    store_id = store_id_raw or f"zip:{store_zip}"
    store_name = store_name_raw or f"Lowe's {store_zip}"
    store_state = _infer_state_from_zip(store_zip)

    if not _is_building_material_category(category):
        LOGGER.debug(
            "Skipping non-building-material category",
            extra={
                "zip": zip_code,
                "category": category,
                "sku": canonical_sku,
            },
        )
        return 0, 0

    price, price_reason = _coerce_price(row.get("price"), "price", required=True)
    if price_reason:
        _quarantine_row(price_reason, {"row": row}, summary_label="price errors")
        return 0, 0

    price_was, price_was_reason = _coerce_price(
        row.get("price_was"), "price_was", required=False
    )
    if price_was_reason:
        LOGGER.debug(
            "price_was invalid; defaulting to None",
            extra={
                "zip": zip_code,
                "category": category,
                "sku": canonical_sku,
                "reason": price_was_reason,
            },
        )
        price_was = None
    availability = row.get("availability")
    if isinstance(availability, str):
        availability = availability.strip()
    availability = normalize_availability(availability)

    pct_off = row.get("pct_off")
    if isinstance(pct_off, str):
        try:
            pct_off = float(pct_off)
        except ValueError:
            pct_off = None
    elif isinstance(pct_off, (int, float)):
        pct_off = float(pct_off)
    else:
        pct_off = None

    computed_pct_off = schemas.compute_pct_off(price, price_was)
    if pct_off is None:
        pct_off = computed_pct_off

    clearance_value = row.get("clearance")
    if clearance_value is None:
        clearance_flag: bool | None = None
    elif isinstance(clearance_value, str):
        clearance_flag = clearance_value.strip().lower() in {"1", "true", "yes", "y"}
    else:
        clearance_flag = bool(clearance_value)

    if clearance_flag is not True and pct_off is not None and pct_off >= pct_threshold:
        clearance_flag = True

    ts_now = datetime.now(timezone.utc)
    alerts_created = 0

    session = None
    try:
        session = session_factory()
        last_obs = repo.get_last_observation(
            session, store_id, canonical_sku, product_url
        )
        obs_model = Observation(
            ts_utc=ts_now,
            store_id=store_id,
            sku=canonical_sku,
            retailer="lowes",
            store_name=store_name,
            zip=store_zip,
            title=title,
            category=category,
            product_url=product_url,
            image_url=image_url,
            price=price,
            price_was=price_was,
            pct_off=pct_off,
            clearance=clearance_flag,
            availability=availability,
        )

        if not dry_run:
            repo.upsert_store(
                session,
                store_id,
                store_name,
                zip_code=store_zip,
                city=_derive_city_from_store_name(store_name),
                state=store_state,
            )
            repo.upsert_item(
                session,
                canonical_sku,
                "lowes",
                title,
                category,
                product_url,
                image_url=image_url,
            )
            repo.insert_observation(session, obs_model)
            repo.update_price_history(
                session,
                retailer="lowes",
                store_id=store_id,
                sku=canonical_sku,
                title=title,
                category=category,
                ts_utc=ts_now,
                price=price,
                price_was=price_was,
                pct_off=pct_off,
                availability=availability,
                product_url=product_url,
                image_url=image_url,
                clearance=clearance_flag,
            )
            session.commit()

        new_clearance = repo.should_alert_new_clearance(last_obs, obs_model)
        triggered: list[str] = []
        price_drop = repo.should_alert_price_drop(last_obs, obs_model, pct_threshold)
        if price_drop:
            triggered.append(f"pct>={pct_threshold:.2f}")

        # Absolute-drop logic (category-specific or default)
        abs_key = (category or "").strip().lower()
        abs_th = abs_map.get(abs_key, abs_map.get("default"))
        if abs_th and (
            last_obs
            and last_obs.price is not None
            and obs_model.price is not None
        ):
            try:
                if (last_obs.price - obs_model.price) >= float(abs_th):
                    triggered.append(f"abs>={abs_th}")
                    price_drop = True
            except Exception:
                pass

        LOGGER.debug(
            "alert check sku=%s rules=%s",
            canonical_sku,
            ",".join(triggered),
        )

        if new_clearance:
            alert = Alert(
                ts_utc=ts_now,
                alert_type="new_clearance",
                store_id=store_id,
                sku=canonical_sku,
                retailer="lowes",
                pct_off=obs_model.pct_off,
                price=obs_model.price,
                price_was=obs_model.price_was,
                note=f"zip={store_zip}",
            )
            if not dry_run:
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_new_clearance(obs_model)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error(
                        "Notifier failed for clearance (sku=%s): %s",
                        canonical_sku,
                        exc,
                        extra={
                            "zip": zip_code,
                            "category": category,
                            "url": product_url,
                        },
                    )
            alerts_created += 1

        if price_drop and last_obs is not None:
            drop_pct = None
            if (
                last_obs.price is not None
                and last_obs.price > 0
                and obs_model.price is not None
            ):
                drop_pct = (last_obs.price - obs_model.price) / last_obs.price

            alert = Alert(
                ts_utc=ts_now,
                alert_type="price_drop",
                store_id=store_id,
                sku=canonical_sku,
                retailer="lowes",
                pct_off=drop_pct,
                price=obs_model.price,
                price_was=last_obs.price,
                note=f"zip={store_zip}",
            )
            if not dry_run:
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_price_drop(obs_model, last_obs)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error(
                        "Notifier failed for price drop (sku=%s): %s",
                        canonical_sku,
                        exc,
                        extra={
                            "zip": zip_code,
                            "category": category,
                            "url": product_url,
                        },
                    )
            alerts_created += 1
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception(
            "Failed to persist row for sku=%s: %s",
            canonical_sku,
            exc,
            extra={"zip": zip_code, "category": category, "url": product_url},
        )
        return 0, 0
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            LOGGER.debug("Session closed")

    stats.valid += 1
    return 1, alerts_created



def _export_csv(config: dict[str, Any], session_factory) -> None:
    csv_path = config.get("output", {}).get("csv_path")
    if not csv_path:
        return
    session = None
    try:
        session = session_factory()
        rows = repo.flatten_for_csv(session)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to query rows for CSV export: %s", exc)
        return
    finally:
        try:
            if session is not None:
                session.close()
        finally:
            LOGGER.debug("Session closed")

    try:
        repo.write_csv(rows, csv_path)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to write CSV to %s: %s", csv_path, exc)


def _ping_healthcheck(config: dict[str, Any]) -> None:
    url = (config or {}).get("healthcheck_url")
    if not url:
        LOGGER.info("healthcheck: disabled")
        return
    host = urlparse(str(url)).netloc or urlparse(str(url)).path
    verify_env = os.getenv("HEALTHCHECK_VERIFY")
    verify = True if verify_env is None else verify_env.strip().lower() not in {"0", "false", "no"}
    try:
        response = requests.get(url, timeout=5, verify=verify)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Healthcheck ping failed for host=%s: %s", host, exc)
        return
    if response.status_code >= 400:
        LOGGER.warning(
            "Healthcheck returned status %s for host=%s",
            response.status_code,
            host,
        )
    else:
        LOGGER.info(
            "healthcheck ok | host=%s status=%s",
            host,
            response.status_code,
        )


def _start_dashboard_background(host: str = "0.0.0.0", port: int = 8000) -> tuple[uvicorn.Server, threading.Thread]:
    LOGGER.info("Starting dashboard thread | host=%s port=%s", host, port)
    config = uvicorn.Config(
        "app.dashboard:app",
        host=host,
        port=port,
        reload=False,
        log_config=None,
    )
    server = uvicorn.Server(config)

    def run_dashboard() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()

    thread = threading.Thread(
        target=run_dashboard,
        name="dashboard-server",
        daemon=True,
    )
    thread.start()
    LOGGER.info("Dashboard thread launched (pid=%s)", os.getpid())
    return server, thread


def _stop_dashboard_background(
    server: uvicorn.Server | None, thread: threading.Thread | None
) -> tuple[uvicorn.Server | None, threading.Thread | None]:
    if server is not None:
        server.should_exit = True
    if thread is not None:
        thread.join(timeout=5)
        LOGGER.info("Dashboard thread joined")
    return None, None


async def _async_main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    if args.validate:
        args.once = True
    LOGGER.info(
        "Parsed arguments: once=%s discover_categories=%s discover_stores=%s concurrency=%s zips=%s categories_pattern=%s validate=%s ignore_quarantine=%s",
        args.once,
        args.discover_categories,
        args.discover_stores,
        args.concurrency,
        args.zips,
        getattr(args, "categories_pattern", None).pattern  # type: ignore[attr-defined]
        if getattr(args, "categories_pattern", None)
        else None,
        args.validate,
        args.ignore_quarantine,
    )

    load_dotenv()

    config_path = Path("app/config.yml")
    config = _load_config(config_path)
    _configure_material_keywords(config)

    catalog_file = _resolve_catalog_path(config)
    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    zips_path_value = lowes_conf.get("zips_path")
    zips_file = _resolve_config_path(zips_path_value) if zips_path_value else None

    if args.discover_categories or args.discover_stores:
        async with async_playwright() as playwright:
            apply_stealth(playwright)
            if args.discover_categories:
                categories = await discover_categories(playwright)
                if not categories:
                    raise RuntimeError(
                        "Discovery returned zero catalog URLs. Check selectors or rerun later."
                    )
                write_catalog_yaml(catalog_file, categories)
                LOGGER.info(
                    "Discovered %d Lowe's catalog URLs -> %s",
                    len(categories),
                    catalog_file,
                )
            if args.discover_stores:
                if zips_file is None:
                    raise RuntimeError(
                        "zips_path is missing in configuration; cannot write discovery results."
                    )
                stores = await discover_stores_WA_OR(playwright)
                if not stores:
                    raise RuntimeError(
                        "Discovery returned zero stores. Check selectors or rerun later."
                    )
                write_zips_yaml(zips_file, stores)
                LOGGER.info(
                    "Discovered %d Lowe's WA/OR stores -> %s",
                    len(stores),
                    zips_file,
                )
        return

    if not catalog_file.exists():
        raise FileNotFoundError(
            f"Catalog file not found at {catalog_file}. Run `python -m app.main --discover-categories` first."
        )

    catalog_categories = _load_catalog(catalog_file)
    categories = _filter_categories(catalog_categories, getattr(args, "categories_pattern", None))
    if not categories:
        raise RuntimeError("No categories matched the provided filter.")

    engine = get_engine(config.get("output", {}).get("sqlite_path", "orwa_lowes.sqlite"))
    if args.validate:
        LOGGER.info("Validate mode: skipping database schema initialisation")
    else:
        init_db_safe(engine)
        LOGGER.info("Database initialized (existing tables preserved)")
    session_factory = make_session(engine)

    if not args.validate:
        session = None
        try:
            session = session_factory()
            updates = repo.normalize_availability_records(session)
            if updates:
                session.commit()
                LOGGER.info("Normalised legacy availability strings | rows=%d", updates)
            else:
                session.rollback()
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Availability normalisation pass failed: %s", exc)
        finally:
            if session is not None:
                session.close()

    if getattr(args, "generate_test_data", False):
        generate_test_data(session_factory)
        return

    notifier = Notifier()

    dashboard_server: uvicorn.Server | None = None
    dashboard_thread: threading.Thread | None = None
    if args.dashboard:
        dashboard_server, dashboard_thread = _start_dashboard_background()
        print("Dashboard running at http://localhost:8000")

    try:
        await _run_cycle(args, config, categories, session_factory, notifier)
    except Exception:
        LOGGER.exception("Initial run cycle failed")
        dashboard_server, dashboard_thread = _stop_dashboard_background(dashboard_server, dashboard_thread)
        raise

    interval_minutes = config.get("schedule", {}).get("minutes", 180) or 180
    retention_value = config.get("quarantine_retention_days", 30)
    try:
        retention_days = int(retention_value)
    except (TypeError, ValueError):
        retention_days = 30

    if retention_days > 0 and not args.validate:
        if check_quarantine_table(engine):
            session = None
            try:
                session = session_factory()
                removed = repo.cleanup_quarantine(session, days=retention_days)
                session.commit()
                LOGGER.info(
                    "Quarantine cleanup completed | removed=%d | retention_days=%d",
                    removed,
                    retention_days,
                )
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Quarantine cleanup failed: %s", exc)
            finally:
                try:
                    if session is not None:
                        session.close()
                finally:
                    LOGGER.debug("Session closed")
        else:
            LOGGER.info("Quarantine cleanup skipped: quarantine table missing")
    elif args.validate:
        LOGGER.info("Validate mode: skipping quarantine cleanup")

    if args.once or args.probe:
        if args.dashboard:
            print("Scrape complete. Dashboard live at http://localhost:8000 — press Ctrl+C to exit.")
            try:
                await asyncio.Event().wait()
            except (KeyboardInterrupt, SystemExit):
                LOGGER.info("Shutdown signal received; exiting one-off dashboard session")
        dashboard_server, dashboard_thread = _stop_dashboard_background(dashboard_server, dashboard_thread)
        return

    if interval_minutes <= 0:
        interval_minutes = 180

    scheduler = AsyncIOScheduler()

    async def scheduled_cycle() -> None:
        try:
            await _run_cycle(args, config, categories, session_factory, notifier)
        except PreflightError as exc:
            LOGGER.exception("Scheduled preflight check failed")
            raise
        except Exception:
            LOGGER.exception("Scheduled run cycle failed")

    scheduler.add_job(scheduled_cycle, "interval", minutes=interval_minutes)
    scheduler.start()
    LOGGER.info("Scheduler started with interval=%s minutes", interval_minutes)

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Shutdown signal received; stopping scheduler")
    finally:
        scheduler.shutdown(wait=False)
        dashboard_server, dashboard_thread = _stop_dashboard_background(dashboard_server, dashboard_thread)


def main() -> None:
    try:
        asyncio.run(_async_main())
    except PreflightError as exc:
        LOGGER.error("Preflight check failed: %s", exc)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:  # pragma: no cover - interactive safety
        LOGGER.info("Interrupted by user")


if __name__ == "__main__":
    main()
ZIP_CURSOR_FILE = Path(os.getenv("CHEAPSKATER_ZIP_CURSOR", "logs/zip_cursor.json"))
ZIP_RESUME_ENABLED = os.getenv("CHEAPSKATER_RESUME_ZIPS", "1") not in {"0", "false", "False"}
ZIP_PROGRESS_TIMEOUT_MINUTES = float(os.getenv("CHEAPSKATER_ZIP_TIMEOUT_MINUTES", "45"))
BROWSER_ZIP_RESTART_LIMIT = max(0, int(os.getenv("CHEAPSKATER_BROWSER_ZIP_LIMIT", "10")))
