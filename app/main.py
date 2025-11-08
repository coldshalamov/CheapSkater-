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
from app.storage.models_sql import Alert, Observation


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
        "--probe",
        action="store_true",
        help="Set store context, load one category, and exit after reporting card counts.",
    )
    parser.add_argument(
        "--retailer",
        default="lowes",
        help="Retailer to target (only 'lowes' is supported).",
    )
    parser.add_argument(
        "--zip",
        "--zips",
        dest="zips",
        type=str,
        help="Comma-separated list of ZIP codes to override configuration values.",
    )
    parser.add_argument(
        "--categories",
        dest="categories_filter",
        type=str,
        help="Regex/substring filter applied to catalog category names (case-insensitive).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    retailer_value = (args.retailer or "").strip().lower()
    if retailer_value and retailer_value != "lowes":
        parser.error("Only 'lowes' is supported in pilot. Home Depot is not yet implemented.")
    args.retailer = retailer_value or "lowes"

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


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
    base = args.zips or [str(z) for z in lowes_conf.get("zips", [])]
    return [zip_code for zip_code in base if zip_code]


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
    categories: list[dict[str, str]],
    session_factory,
    notifier: Notifier,
) -> tuple[int, int]:
    start = time.monotonic()
    total_items = 0
    total_alerts = 0

    retailers = config.get("retailers", {})
    lowes_conf = retailers.get("lowes", {})
    zips = args.zips or [str(z) for z in lowes_conf.get("zips", [])]

    if not zips:
        LOGGER.warning("No ZIP codes configured; skipping cycle")
        return total_items, total_alerts

    if not categories:
        LOGGER.warning("No categories available; skipping cycle")
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
                    rows = await run_for_zip(
                        playwright,
                        zip_code,
                        categories,
                        clearance_threshold=pct_threshold,
                    )
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


async def _run_probe(
    args: argparse.Namespace,
    config: dict[str, Any],
    categories: list[dict[str, str]],
) -> None:
    zips = _resolve_zips(args, config)
    if not zips:
        raise RuntimeError("No ZIP codes available for probe.")
    if not categories:
        raise RuntimeError("No categories available for probe.")

    target_zip = zips[0]
    target_category = categories[0]
    pct_threshold = _get_pct_threshold(config)

    async with async_playwright() as playwright:
        rows = await run_for_zip(
            playwright,
            target_zip,
            [target_category],
            clearance_threshold=pct_threshold,
        )

    titles = sum(1 for row in rows if row.get("title"))
    priced = sum(1 for row in rows if row.get("price") is not None)
    print(
        "probe ok | zip={zip} | category={category} | cards={cards} | titles={titles} | prices={prices}".format(
            zip=target_zip,
            category=target_category["name"],
            cards=len(rows),
            titles=titles,
            prices=priced,
        )
    )


async def _process_row(
    row: dict[str, Any],
    zip_code: str,
    session_factory,
    notifier: Notifier,
    pct_threshold: float,
) -> tuple[int, int]:
    def _coerce_price(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return schemas.parse_price(value)
        return None

    def _derive_sku(raw_sku: str | None, product_url: str) -> str | None:
        candidate = (raw_sku or "").strip()
        if candidate:
            return candidate
        match = re.search(r"(\d{5,})", product_url)
        return match.group(1) if match else None

    title = (row.get("title") or "").strip()
    category = (row.get("category") or "").strip() or "Uncategorised"
    product_url = (row.get("product_url") or "").strip()
    if product_url.startswith("/"):
        product_url = f"https://www.lowes.com{product_url}"
    sku = _derive_sku(row.get("sku"), product_url)
    image_url = (row.get("image_url") or None)
    if isinstance(image_url, str):
        image_url = image_url.strip() or None

    if not title or not sku or not product_url:
        LOGGER.debug("Skipping row with insufficient data (sku=%s title=%s)", sku, title)
        return 0, 0

    store_id_raw = (row.get("store_id") or "").strip()
    row_zip = (row.get("zip") or zip_code or "").strip()
    store_name_raw = (row.get("store_name") or "").strip()
    store_zip = row_zip or (zip_code or "").strip() or "00000"
    store_id = store_id_raw or f"zip:{store_zip}"
    store_name = store_name_raw or f"Lowe's {store_zip}"

    price = _coerce_price(row.get("price"))
    price_was = _coerce_price(row.get("price_was"))
    availability = (row.get("availability") or None)
    if isinstance(availability, str):
        availability = availability.strip() or None

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

    try:
        with session_factory() as session:
            repo.upsert_store(
                session,
                store_id,
                store_name,
                zip_code=store_zip,
                city=_derive_city_from_store_name(store_name),
                state=_infer_state_from_zip(store_zip),
            )
            last_obs = repo.get_last_observation(session, store_id, sku)
            repo.upsert_item(
                session,
                sku,
                "lowes",
                title,
                category,
                product_url,
                image_url=image_url,
            )
            obs_model = Observation(
                ts_utc=ts_now,
                store_id=store_id,
                sku=sku,
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
            repo.insert_observation(session, obs_model)
            session.commit()

            new_clearance = repo.should_alert_new_clearance(last_obs, obs_model)
            price_drop = repo.should_alert_price_drop(last_obs, obs_model, pct_threshold)

            if new_clearance:
                alert = Alert(
                    ts_utc=ts_now,
                    alert_type="new_clearance",
                    store_id=store_id,
                    sku=sku,
                    retailer="lowes",
                    pct_off=obs_model.pct_off,
                    price=obs_model.price,
                    price_was=obs_model.price_was,
                    note=f"zip={store_zip}",
                )
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_new_clearance(obs_model)
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.error("Notifier failed for clearance (sku=%s): %s", sku, exc)
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
                    sku=sku,
                    retailer="lowes",
                    pct_off=drop_pct,
                    price=obs_model.price,
                    price_was=last_obs.price,
                    note=f"zip={store_zip}",
                )
                repo.insert_alert(session, alert)
                session.commit()
                try:
                    notifier.notify_price_drop(obs_model, last_obs)
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
        "Parsed arguments: once=%s probe=%s retailer=%s zips=%s categories_pattern=%s",
        args.once,
        args.probe,
        args.retailer,
        args.zips,
        getattr(args, "categories_pattern", None).pattern  # type: ignore[attr-defined]
        if getattr(args, "categories_pattern", None)
        else None,
    )

    load_dotenv()

    config_path = Path("app/config.yml")
    config = _load_config(config_path)

    catalog_path = config.get("catalog_path")
    if not catalog_path:
        raise RuntimeError("catalog_path is missing in app/config.yml")
    catalog_file = Path(catalog_path)
    if not catalog_file.is_absolute():
        catalog_file = Path.cwd() / catalog_file
    catalog_categories = _load_catalog(catalog_file)
    categories = _filter_categories(catalog_categories, getattr(args, "categories_pattern", None))
    if not categories:
        raise RuntimeError("No categories matched the provided filter.")

    if args.probe:
        await _run_probe(args, config, categories)
        return

    engine = get_engine(config.get("output", {}).get("sqlite_path", "orwa_lowes.sqlite"))
    init_db(engine)
    session_factory = make_session(engine)

    notifier = Notifier()

    try:
        await _run_cycle(args, config, categories, session_factory, notifier)
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
            await _run_cycle(args, config, categories, session_factory, notifier)
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
