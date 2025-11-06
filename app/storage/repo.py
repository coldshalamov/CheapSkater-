"""Repository helpers for interacting with persistent storage."""

from __future__ import annotations

import csv
import os
from datetime import timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.extractors import schemas
from .models_sql import Alert, Item, Observation, Store


def upsert_store(
    session: Session,
    store_id: str,
    retailer: str,
    name: str,
    city: str,
    state: str,
    zip_code: str,
) -> None:
    """Insert or update a :class:`Store` record."""

    if not store_id:
        return

    store = session.get(Store, store_id)
    if store is None:
        store = Store(
            store_id=store_id,
            retailer=retailer,
            name=name,
            city=city,
            state=state,
            zip=zip_code,
        )
        session.add(store)
        return

    store.retailer = retailer
    store.name = name
    store.city = city
    store.state = state
    store.zip = zip_code


def upsert_item(session: Session, item: Item) -> None:
    """Insert or update an :class:`Item` record."""

    identity = (item.sku, item.retailer)
    existing = session.get(Item, identity)
    if existing is None:
        session.add(item)
        return

    existing.title = item.title
    existing.category = item.category
    existing.product_url = item.product_url
    existing.image_url = item.image_url


def insert_observation(session: Session, obs: Observation) -> Observation:
    """Insert a new observation record."""

    session.add(obs)
    session.flush()
    return obs


def get_last_observation(session: Session, store_id: str, sku: str) -> Observation | None:
    """Return the most recent observation for a store and SKU."""

    stmt = (
        select(Observation)
        .where(Observation.store_id == store_id, Observation.sku == sku)
        .order_by(Observation.ts_utc.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def insert_alert(session: Session, alert: Alert) -> Alert:
    """Insert an alert record."""

    session.add(alert)
    session.flush()
    return alert


def flatten_for_csv(session: Session, limit: int = 1000) -> list[schemas.FlattenedRow]:
    """Return denormalised rows ready for CSV export."""

    row_number = func.row_number().over(
        partition_by=(Observation.store_id, Observation.sku),
        order_by=Observation.ts_utc.desc(),
    )

    ranked_observations = (
        select(
            Observation.store_id.label("store_id"),
            Observation.sku.label("sku"),
            Observation.ts_utc.label("ts_utc"),
            Observation.price.label("price"),
            Observation.price_was.label("price_was"),
            Observation.availability.label("availability"),
            Observation.clearance.label("clearance"),
            row_number.label("row_number"),
        )
        .subquery()
    )

    latest_observations = (
        select(*ranked_observations.c)
        .where(ranked_observations.c.row_number == 1)
        .subquery()
    )

    stmt = (
        select(
            latest_observations.c.ts_utc,
            Item.retailer,
            latest_observations.c.store_id,
            Store.name,
            Store.zip,
            Item.sku,
            Item.title,
            Item.category,
            latest_observations.c.price,
            latest_observations.c.price_was,
            latest_observations.c.availability,
            Item.product_url,
            Item.image_url,
        )
        .select_from(latest_observations)
        .join(Store, Store.store_id == latest_observations.c.store_id, isouter=True)
        .join(
            Item,
            and_(
                Item.sku == latest_observations.c.sku,
                or_(
                    Store.retailer.is_(None),
                    Item.retailer == Store.retailer,
                ),
            ),
        )
        .order_by(latest_observations.c.ts_utc.desc())
        .limit(limit)
    )

    result = session.execute(stmt).all()
    rows: list[schemas.FlattenedRow] = []
    for row in result:
        pct_off = schemas.compute_pct_off(row.price, row.price_was)
        rows.append(
            schemas.FlattenedRow(
                ts_utc=row.ts_utc,
                retailer=row.retailer,
                store_id=row.store_id,
                store_name=row.name,
                zip=row.zip,
                sku=row.sku,
                title=row.title,
                category=row.category,
                price=row.price,
                price_was=row.price_was,
                pct_off=pct_off,
                clearance=row.clearance,
                availability=row.availability,
                product_url=row.product_url,
                image_url=row.image_url,
            )
        )
    return rows


def should_alert_new_clearance(last_obs: Observation | None, new_obs: Observation) -> bool:
    """Return ``True`` if a new clearance price should trigger an alert."""

    new_flag = getattr(new_obs, "clearance", None)
    last_flag = getattr(last_obs, "clearance", None) if last_obs else None

    if new_flag is True:
        return last_flag is not True

    if new_flag is False:
        return False

    if last_flag is True:
        return False

    if new_obs.price is None or new_obs.price_was is None:
        return False

    if new_obs.price <= 0 or new_obs.price_was <= 0:
        return False

    if new_obs.price >= new_obs.price_was:
        return False

    if last_obs is None:
        return True

    if last_obs.price_was is None or last_obs.price_was == 0:
        return True

    return False


def should_alert_price_drop(
    last_obs: Observation | None, new_obs: Observation, pct_threshold: float
) -> tuple[bool, float]:
    """Return whether a price drop meets the percentage threshold."""

    if (
        last_obs is None
        or last_obs.price is None
        or new_obs.price is None
        or last_obs.price <= 0
        or new_obs.price >= last_obs.price
    ):
        return False, 0.0

    drop = (last_obs.price - new_obs.price) / last_obs.price
    return (drop >= pct_threshold, drop)


def write_csv(rows: list[schemas.FlattenedRow], csv_path: str) -> None:
    """Write flattened rows to ``csv_path`` as CSV."""

    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    header = [
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
        "clearance",
        "availability",
        "product_url",
        "image_url",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            ts = row.ts_utc.astimezone(timezone.utc)
            ts_iso = ts.isoformat().replace("+00:00", "Z")
            writer.writerow(
                [
                    ts_iso,
                    row.retailer or "",
                    row.store_id or "",
                    row.store_name or "",
                    row.zip or "",
                    row.sku,
                    row.title,
                    row.category,
                    "" if row.price is None else f"{row.price}",
                    "" if row.price_was is None else f"{row.price_was}",
                    "" if row.pct_off is None else f"{row.pct_off}",
                    ""
                    if row.clearance is None
                    else ("true" if row.clearance else "false"),
                    row.availability or "",
                    row.product_url,
                    row.image_url or "",
                ]
            )
