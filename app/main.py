"""Command-line interface entry point for the CheapSkater application."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any, Iterable

import requests
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from app.alerts.notifier import Notifier
from app.errors import PageLoadError, SelectorChangedError, StoreContextError
from app.extractors import schemas
from app.logging_config import get_logger
from app.retailers.lowes import run_for_zip
from app.storage import repo
from app.storage.db import get_engine, init_db, make_session
from app.storage.models_sql import Alert, Item, Observation


LOGGER = get_logger(__name__)


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
        "--retailer",
        choices=["lowes", "homedepot"],
        default="lowes",
        help="Retailer to target for scraping.",
    )
    parser.add_argument(
        "--zips",
        type=str,
        help="Comma-separated list of ZIP codes to override configuration values.",
    )
    parser.add_argument(
        "--categories",
        type=str,
        help="Comma-separated list of category names to filter (case-insensitive substring match).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    args.zips = (
        [zip_code.strip() for zip_code in args.zips.split(",") if zip_code.strip()]
        if args.zips
        else []
    )
    args.categories = (
        [cat.strip() for cat in args.categories.split(",") if cat.strip()]
        if args.categories
        else []
    )
    return args


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _normalise_categories(
    categories: list[dict[str, Any]], filters: list[str]
) -> list[dict[str, Any]]:
    if not filters:
        return categories

    needles = [needle.lower() for needle in filters]
    filtered: list[dict[str, Any]] = []
    for category in categories:
        name = str(category.get("name", ""))
        name_lower = name.lower()
        if any(needle in name_lower for needle in needles):
            filtered.append(category)
    return filtered


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


def _derive_city_from_store_name(store_name: str | None) -> str:
    if not store_name:
        return "Unknown"
    parts = re.split(r"[-–|,]", store_name)
    for part in parts:
        cleaned = part.strip()
        if cleaned:
            return cleaned
    return store_name.strip() or "Unknown"


async def _run_cycle(
    args: argparse.Namespace,
    config: dict[str, Any],
    session_factory,
    notifier: Notifier,
) -> tuple[int, int]:
    start = time.monotonic()
    total_items = 0
    total_alerts = 0

    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    zips = args.zips or [str(z) for z in lowes_conf.get("zips", [])]
    categories = lowes_conf.get("categories", [])
    categories = _normalise_categories(categories, args.categories)

    if not zips:
        LOGGER.warning("No ZIP codes configured; skipping cycle")
        return total_items, total_alerts

    if not categories:
        LOGGER.warning("No categories matched filters; skipping cycle")
        return total_items, total_alerts

    pct_threshold = float(config.get("alerts", {}).get("pct_drop", 0.25) or 0.25)

    LOGGER.info(
        "Starting run cycle | retailer=lowes | zips=%d | categories=%d",
        len(zips),
        len(categories),
    )

    any_zip_success = False

    try:
        async with async_playwright() as playwright:
            for zip_code in zips:
                try:
                    rows = await run_for_zip(playwright, zip_code, categories)
                except StoreContextError as exc:
                    LOGGER.error("Unable to set store for ZIP %s: %s", zip_code, exc)
                    continue
                except SelectorChangedError as exc:
                    LOGGER.warning(
                        "No products parsed for ZIP %s (category=%s url=%s): %s",
                        zip_code,
                        getattr(exc, "category", "unknown"),
                        getattr(exc, "url", "unknown"),
                        exc,
                    )
                    continue
                except PageLoadError as exc:
                    LOGGER.warning(
                        "Page load error for ZIP %s (category=%s url=%s): %s",
                        zip_code,
                        getattr(exc, "category", "unknown"),
                        getattr(exc, "url", "unknown"),
                        exc,
                    )
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.exception(
                        "Unexpected failure scraping ZIP %s: %s", zip_code, exc
                    )
                    continue

                any_zip_success = True

                if not rows:
                    LOGGER.info(
                        "Scrape returned no rows for ZIP %s; continuing", zip_code
                    )
                    continue

                for row in rows:
                    processed = await _process_row(
                        row,
                        zip_code,
                        session_factory,
                        notifier,
                        pct_threshold,
                    )
                    total_items += processed[0]
                    total_alerts += processed[1]
    finally:
        duration = time.monotonic() - start

    if any_zip_success:
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
) -> tuple[int, int]:
    title = (row.get("title") or "").strip()
    sku = (row.get("sku") or "").strip()
    category = (row.get("category") or "").strip() or "Uncategorised"
    product_url = (row.get("product_url") or "").strip()
    if product_url.startswith("/"):
        product_url = f"https://www.lowes.com{product_url}"
    image_url = (row.get("image_url") or None)
    if isinstance(image_url, str):
        image_url = image_url.strip() or None

    if not title or not sku or not product_url:
        LOGGER.debug(
            "Skipping row with insufficient data (sku=%s title=%s)", sku, title
        )
        return 0, 0

    store_id_raw = (row.get("store_id") or "").strip()
    row_zip = (row.get("zip") or zip_code or "").strip()
    store_name_raw = (row.get("store_name") or "").strip()
    store_zip = row_zip or (zip_code or "").strip()
    store_id = store_id_raw or (f"zip:{store_zip}" if store_zip else f"zip:{zip_code}")
    store_name = store_name_raw or f"Lowe's {store_zip or zip_code or 'unknown'}"

    price = row.get("price")
    price_was = row.get("price_was")
    availability = (row.get("availability") or None)
    if isinstance(availability, str):
        availability = availability.strip() or None

    clearance_value = row.get("clearance")
    clearance_flag: bool | None
    if clearance_value is None:
        clearance_flag = None
    elif isinstance(clearance_value, str):
        clearance_flag = clearance_value.strip().lower() in {"1", "true", "yes", "y"}
    else:
        clearance_flag = bool(clearance_value)

    ts_now = datetime.now(timezone.utc)

    item_model = Item(
        sku=sku,
        retailer="lowes",
        title=title,
        category=category,
        product_url=product_url,
        image_url=image_url,
    )

    obs_model = Observation(
        ts_utc=ts_now,
        store_id=store_id,
        sku=sku,
        price=price,
        price_was=price_was,
        availability=availability,
        clearance=clearance_flag,
    )
    setattr(obs_model, "zip", store_zip)
    setattr(obs_model, "store_name", store_name)

    pct_off = schemas.compute_pct_off(price, price_was)

    alerts_created = 0

    try:
        with session_factory() as session:
            repo.upsert_store(
                session,
                store_id=store_id,
                retailer="lowes",
                name=store_name,
                city=_derive_city_from_store_name(store_name),
                state=_infer_state_from_zip(store_zip),
                zip_code=store_zip or zip_code or "00000",
            )
            last_obs = repo.get_last_observation(session, store_id, sku)
            repo.upsert_item(session, item_model)
            repo.insert_observation(session, obs_model)
            session.commit()

            new_clearance = repo.should_alert_new_clearance(last_obs, obs_model)
            drop_ok, pct_drop = repo.should_alert_price_drop(
                last_obs, obs_model, pct_threshold
            )

            if new_clearance:
                delta = 0.0
                if obs_model.price is not None and obs_model.price_was is not None:
                    delta = obs_model.price_was - obs_model.price
                alert = Alert(
                    ts_utc=ts_now,
                    store_id=store_id,
                    sku=sku,
                    rule="new_clearance",
                    old_price=obs_model.price_was,
                    new_price=obs_model.price,
                    delta=delta,
                )
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_new_clearance(item_model, obs_model, pct_off)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error("Notifier failed for clearance alert (sku=%s): %s", sku, exc)
                alerts_created += 1

            if drop_ok:
                delta = 0.0
                if last_obs is not None and last_obs.price is not None and obs_model.price is not None:
                    delta = last_obs.price - obs_model.price
                alert = Alert(
                    ts_utc=ts_now,
                    store_id=store_id,
                    sku=sku,
                    rule="price_drop",
                    old_price=last_obs.price if last_obs else None,
                    new_price=obs_model.price,
                    delta=delta,
                )
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_price_drop(item_model, last_obs, obs_model, pct_drop)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error("Notifier failed for price drop (sku=%s): %s", sku, exc)
                alerts_created += 1
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Failed to persist row for sku=%s: %s", sku, exc)
        return 0, 0

    return 1, alerts_created


def _export_csv(config: dict[str, Any], session_factory) -> None:
    csv_path = config.get("output", {}).get("csv_path")
    if not csv_path:
        return
    try:
        with session_factory() as session:
            rows = repo.flatten_for_csv(session)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to query rows for CSV export: %s", exc)
        return

    try:
        repo.write_csv(rows, csv_path)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.error("Failed to write CSV to %s: %s", csv_path, exc)


def _ping_healthcheck(config: dict[str, Any]) -> None:
    url = (config or {}).get("healthcheck_url")
    if not url:
        return
    try:
        response = requests.get(url, timeout=5)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Healthcheck ping failed: %s", exc)
        return
    if response.status_code >= 400:
        LOGGER.warning(
            "Healthcheck returned status %s: %s",
            response.status_code,
            response.text,
        )


async def _async_main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    LOGGER.info(
        "Parsed arguments: once=%s retailer=%s zips=%s categories=%s",
        args.once,
        args.retailer,
        args.zips,
        args.categories,
    )

    if args.retailer != "lowes":
        LOGGER.error("Retailer '%s' is not supported yet", args.retailer)
        return

    load_dotenv()

    config_path = Path("app/config.yml")
    config = _load_config(config_path)

    engine = get_engine(config.get("output", {}).get("sqlite_path", "orwa_lowes.sqlite"))
    init_db(engine)
    session_factory = make_session(engine)

    notifier = Notifier()

    try:
        await _run_cycle(args, config, session_factory, notifier)
    except Exception:
        LOGGER.exception("Initial run cycle failed")
        raise

    if args.once:
        return

    interval_minutes = config.get("schedule", {}).get("minutes", 180) or 180
    if interval_minutes <= 0:
        interval_minutes = 180

    scheduler = AsyncIOScheduler()

    async def scheduled_cycle() -> None:
        try:
            await _run_cycle(args, config, session_factory, notifier)
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


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:  # pragma: no cover - interactive safety
        LOGGER.info("Interrupted by user")


if __name__ == "__main__":
    main()
