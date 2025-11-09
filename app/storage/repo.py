"""Repository helpers for interacting with persistent storage."""

from __future__ import annotations

import csv
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from .models_sql import Alert, Item, Observation, Quarantine, Store

CSV_HEADER = [
    "ts_utc",
    "retailer",
    "store_id",
    "store_name",
    "zip",
    "sku",
    "title",
    "category",
    "price",
    "price_was",
    "pct_off",
    "availability",
    "product_url",
    "image_url",
    "state",
]


def upsert_store(
    session: Session,
    store_id: str,
    name: str,
    zip_code: str,
    *,
    city: str | None = None,
    state: str | None = None,
) -> Store:
    store = session.get(Store, store_id)
    if store is None:
        store = Store(id=store_id, name=name, city=city, state=state, zip=zip_code)
        session.add(store)
    else:
        store.name = name
        store.city = city
        store.state = state
        store.zip = zip_code
    session.flush()
    return store


def upsert_item(
    session: Session,
    sku: str,
    retailer: str,
    title: str,
    category: str,
    product_url: str,
    *,
    image_url: str | None = None,
) -> Item:
    identity = (sku, retailer)
    item = session.get(Item, identity)
    if item is None:
        item = Item(
            sku=sku,
            retailer=retailer,
            title=title,
            category=category,
            product_url=product_url,
            image_url=image_url,
        )
        session.add(item)
    else:
        item.title = title
        item.category = category
        item.product_url = product_url
        item.image_url = image_url
    session.flush()
    return item


def insert_observation(session: Session, obs: Observation) -> Observation:
    session.add(obs)
    session.flush()
    return obs


def get_last_observation(
    session: Session,
    store_id: str,
    sku: str | None,
    product_url: str | None,
) -> Observation | None:
    stmt = select(Observation).where(Observation.store_id == store_id)
    if sku:
        stmt = stmt.where(Observation.sku == sku)
    elif product_url:
        stmt = stmt.where(Observation.product_url == product_url)
    else:
        return None

    stmt = stmt.order_by(Observation.ts_utc.desc()).limit(1)
    return session.execute(stmt).scalar_one_or_none()


def insert_alert(session: Session, alert: Alert) -> Alert:
    session.add(alert)
    session.flush()
    return alert


def should_alert_new_clearance(
    last_obs: Observation | None,
    new_obs: Observation,
) -> bool:
    return bool(new_obs.clearance) and not (last_obs and last_obs.clearance)


def should_alert_price_drop(
    last_obs: Observation | None,
    new_obs: Observation,
    pct_threshold: float,
) -> bool:
    if (
        last_obs is None
        or last_obs.price is None
        or new_obs.price is None
        or last_obs.price <= 0
    ):
        return False
    return new_obs.price <= last_obs.price * (1 - pct_threshold)


def flatten_for_csv(session: Session) -> list[dict[str, object]]:
    key_value = func.coalesce(Observation.sku, Observation.product_url)
    row_number = func.row_number().over(
        partition_by=(Observation.store_id, key_value),
        order_by=Observation.ts_utc.desc(),
    )

    latest = (
        select(
            Observation.ts_utc,
            Observation.retailer,
            Observation.store_id,
            Observation.store_name,
            Observation.zip,
            Observation.sku,
            Observation.title,
            Observation.category,
            Observation.price,
            Observation.price_was,
            Observation.pct_off,
            Observation.availability,
            Observation.product_url,
            Observation.image_url,
            row_number.label("rn"),
        )
        .subquery()
    )

    stmt = (
        select(
            latest.c.ts_utc,
            latest.c.retailer,
            latest.c.store_id,
            func.coalesce(Store.name, latest.c.store_name).label("store_name"),
            func.coalesce(Store.zip, latest.c.zip).label("zip"),
            Store.state.label("state"),
            latest.c.sku,
            latest.c.title,
            latest.c.category,
            latest.c.price,
            latest.c.price_was,
            latest.c.pct_off,
            latest.c.availability,
            latest.c.product_url,
            latest.c.image_url,
        )
        .select_from(latest)
        .where(latest.c.rn == 1)
        .join(Store, Store.id == latest.c.store_id, isouter=True)
    )

    rows: list[dict[str, object]] = []
    for record in session.execute(stmt):
        rows.append(
            {
                "ts_utc": record.ts_utc,
                "retailer": record.retailer,
                "store_id": record.store_id,
                "store_name": record.store_name,
                "zip": record.zip,
                "state": record.state,
                "sku": record.sku,
                "title": record.title,
                "category": record.category,
                "price": record.price,
                "price_was": record.price_was,
                "pct_off": record.pct_off,
                "availability": record.availability,
                "product_url": record.product_url,
                "image_url": record.image_url,
            }
        )
    return rows


def write_csv(rows: Iterable[dict[str, object]], csv_path: str) -> None:
    path = Path(csv_path)
    os.makedirs(path.parent, exist_ok=True)

    with NamedTemporaryFile(
        mode="w", newline="", encoding="utf-8", dir=str(path.parent), delete=False
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow(_row_to_values(row))
        handle.flush()
        os.fsync(handle.fileno())
        tmp_name = handle.name

    os.replace(tmp_name, path)


def get_clearance_items(
    session: Session,
    *,
    state: str | None = None,
    category: str | None = None,
    limit: int = 1000,
) -> list[Observation]:
    """Return the most recent clearance observations ordered by deal quality."""

    stmt = _latest_observation_query(state=state, category=category)
    stmt = (
        stmt.where(Observation.clearance.is_(True))
        .order_by(
            Observation.pct_off.desc().nullslast(),
            Observation.price.asc().nullslast(),
            Observation.ts_utc.desc(),
        )
        .limit(limit)
    )
    return session.scalars(stmt).all()


def get_new_clearance_today(
    session: Session,
    *,
    state: str | None = None,
    category: str | None = None,
) -> list[Observation]:
    """Return items that transitioned to clearance within the last 24 hours."""

    key_value = func.coalesce(Observation.sku, Observation.product_url)
    row_number = func.row_number().over(
        partition_by=(Observation.store_id, key_value),
        order_by=Observation.ts_utc.desc(),
    )
    prev_clearance = func.lag(Observation.clearance).over(
        partition_by=(Observation.store_id, key_value),
        order_by=Observation.ts_utc.desc(),
    )

    latest = (
        select(
            Observation.id.label("id"),
            row_number.label("rn"),
            prev_clearance.label("prev_clearance"),
        )
        .subquery()
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    stmt = (
        _latest_observation_query(state=state, category=category)
        .join(latest, Observation.id == latest.c.id)
        .where(latest.c.rn == 1)
        .where(Observation.clearance.is_(True))
        .where(Observation.ts_utc >= cutoff)
        .where(
            or_(
                latest.c.prev_clearance.is_(False),
                latest.c.prev_clearance.is_(None),
            )
        )
        .order_by(
            Observation.pct_off.desc().nullslast(),
            Observation.ts_utc.desc(),
        )
    )

    return session.scalars(stmt).all()


def get_clearance_by_category(
    session: Session,
    category: str,
    *,
    state: str | None = None,
    limit: int = 1000,
) -> list[Observation]:
    """Return clearance observations filtered by category name."""

    return get_clearance_items(
        session,
        state=state,
        category=category,
        limit=limit,
    )


def count_observations(session: Session) -> int:
    stmt = select(func.count(Observation.id))
    return int(session.scalar(stmt) or 0)


def count_quarantine(session: Session) -> int:
    stmt = select(func.count(Quarantine.id))
    return int(session.scalar(stmt) or 0)


def get_latest_timestamp(session: Session) -> datetime | None:
    """Return the most recent observation timestamp."""

    stmt = select(func.max(Observation.ts_utc))
    return session.scalar(stmt)


def list_distinct_categories(session: Session) -> list[str]:
    """Return sorted list of categories with active clearance inventory."""

    stmt = (
        select(Observation.category)
        .where(Observation.clearance.is_(True))
        .distinct()
        .order_by(Observation.category.asc())
    )
    return [row[0] for row in session.execute(stmt)]


def insert_quarantine(
    session: Session,
    *,
    retailer: str,
    store_id: str | None,
    sku: str | None,
    zip_code: str | None,
    state: str | None,
    category: str | None,
    reason: str,
    payload: dict[str, object],
) -> None:
    """Persist a quarantine record for inspection."""

    entry = Quarantine(
        ts_utc=datetime.now(timezone.utc),
        retailer=retailer,
        store_id=store_id,
        sku=sku,
        zip=zip_code,
        state=state,
        category=category,
        reason=reason,
        payload=json.dumps(payload, ensure_ascii=False, default=str),
    )
    session.add(entry)
    session.flush()


def list_quarantined_categories(
    session: Session,
    *,
    retailer: str,
    reason: str | None = None,
) -> list[str]:
    """Return sorted list of quarantined category names for *retailer*."""

    stmt = select(Quarantine.category).where(Quarantine.retailer == retailer)
    if reason:
        stmt = stmt.where(Quarantine.reason == reason)
    categories = {
        (row[0] or "").strip()
        for row in session.execute(stmt)
        if (row[0] or "").strip()
    }
    return sorted(categories)


def cleanup_quarantine(session: Session, *, days: int = 30) -> int:
    """Remove quarantine records older than *days* days."""

    if days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = delete(Quarantine).where(Quarantine.ts_utc < cutoff)
    result = session.execute(stmt)
    return int(result.rowcount or 0)


def _row_to_values(row: dict[str, object]) -> list[str]:
    ts = row["ts_utc"]
    if hasattr(ts, "astimezone"):
        ts_iso = ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:  # pragma: no cover - defensive
        ts_iso = str(ts)

    def _fmt(value: object | None) -> str:
        return "" if value is None else f"{value}"

    return [
        ts_iso,
        row.get("retailer", ""),
        row.get("store_id", "") or "",
        row.get("store_name", "") or "",
        row.get("zip", "") or "",
        row.get("sku", ""),
        row.get("title", ""),
        row.get("category", ""),
        _fmt(row.get("price")),
        _fmt(row.get("price_was")),
        _fmt(row.get("pct_off")),
        row.get("availability", "") or "",
        row.get("product_url", ""),
        row.get("image_url", "") or "",
        row.get("state", "") or "",
    ]


def _latest_observation_query(
    *,
    state: str | None = None,
    category: str | None = None,
):
    key_value = func.coalesce(Observation.sku, Observation.product_url)
    row_number = func.row_number().over(
        partition_by=(Observation.store_id, key_value),
        order_by=Observation.ts_utc.desc(),
    )

    latest = select(Observation.id.label("id"), row_number.label("rn")).subquery()

    stmt = (
        select(Observation)
        .join(latest, Observation.id == latest.c.id)
        .join(Store, Store.id == Observation.store_id, isouter=True)
        .where(latest.c.rn == 1)
    )

    if state:
        stmt = stmt.where(
            func.upper(func.coalesce(Store.state, "")) == state.upper()
        )

    if category:
        stmt = stmt.where(Observation.category == category)

    return stmt
