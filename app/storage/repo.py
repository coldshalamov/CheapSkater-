"""Repository helpers for interacting with persistent storage."""

from __future__ import annotations

import csv
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from sqlalchemy import and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.normalizers import normalize_availability

from .models_sql import Alert, Item, Observation, Quarantine, Store, StorePriceHistory

CSV_HEADER = [
    "ts_utc",
    "retailer",
    "store_id",
    "store_name",
    "state",
    "zip",
    "sku",
    "title",
    "category",
    "price",
    "price_was",
    "pct_off",
    "availability",
    "added_at",
    "last_seen",
    "price_change_at",
    "prev_price",
    "prev_price_was",
    "prev_updated_at",
    "product_url",
    "image_url",
]

DEFAULT_MAX_LISTING_AGE_DAYS = 30


def get_max_listing_age_days() -> int:
    """Return the maximum age for listings that should still appear live."""

    raw = (os.getenv("CHEAPSKATER_MAX_LISTING_AGE_DAYS") or "").strip()
    if not raw:
        return DEFAULT_MAX_LISTING_AGE_DAYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_LISTING_AGE_DAYS
    return value if value > 0 else DEFAULT_MAX_LISTING_AGE_DAYS


def _active_listing_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=get_max_listing_age_days())


def upsert_store(
    session: Session,
    store_id: str,
    name: str,
    zip_code: str,
    *,
    city: str | None = None,
    state: str | None = None,
    region: str | None = None,
) -> Store:
    store = session.get(Store, store_id)
    if store is None:
        store = Store(
            id=store_id, name=name, city=city, state=state, zip=zip_code, region=region
        )
        session.add(store)
    else:
        store.name = name
        store.city = city
        store.state = state
        store.zip = zip_code
        if region is not None:
            store.region = region
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


def _history_state_matches(
    entry: StorePriceHistory,
    *,
    price: float | None,
    price_was: float | None,
    pct_off: float | None,
    availability: str | None,
    clearance: bool | None,
) -> bool:
    def _coerce(value: object | None) -> object | None:
        if isinstance(value, str):
            return value.strip()
        return value

    def _float_equal(
        left: float | None, right: float | None, *, tol: float = 1e-6
    ) -> bool:
        if left is None or right is None:
            return left is right
        try:
            return abs(float(left) - float(right)) <= tol
        except Exception:
            return left == right

    return (
        _float_equal(entry.price, price)
        and _float_equal(entry.price_was, price_was)
        and _float_equal(entry.pct_off, pct_off)
        and _coerce(entry.availability) == _coerce(availability)
        and entry.clearance == clearance
    )


def update_price_history(
    session: Session,
    *,
    retailer: str,
    store_id: str,
    sku: str,
    title: str,
    category: str,
    ts_utc: datetime,
    price: float | None,
    price_was: float | None,
    pct_off: float | None,
    availability: str | None,
    product_url: str,
    image_url: str | None,
    clearance: bool | None,
    region: str | None = None,
    category_url: str | None = None,
) -> StorePriceHistory:
    """Record a compressed price history entry for a store listing."""

    normalized_availability = normalize_availability(availability)

    keep_history_rows = 2
    try:
        keep_history_rows = int(os.getenv("CHEAPSKATER_HISTORY_KEEP_ROWS", "2"))
    except Exception:
        keep_history_rows = 2

    stmt = (
        select(StorePriceHistory)
        .where(
            StorePriceHistory.retailer == retailer,
            StorePriceHistory.store_id == store_id,
            StorePriceHistory.sku == sku,
        )
        .order_by(StorePriceHistory.updated_at.desc(), StorePriceHistory.id.desc())
        .limit(1)
    )
    last_entry = session.execute(stmt).scalar_one_or_none()

    state_matches = False
    if last_entry:
        state_matches = _history_state_matches(
            last_entry,
            price=price,
            price_was=price_was,
            pct_off=pct_off,
            availability=normalized_availability,
            clearance=clearance,
        )

    # Default behavior (keep_history_rows=1): overwrite the last entry for a store/SKU.
    # If keep_history_rows > 1, we keep a small bounded history for deltas (prev_*).
    if last_entry and keep_history_rows <= 1:
        # Preserve first-seen semantics in started_at so the "age" of the listing
        # remains stable even as price changes. If the clearance flag flips, reset
        # started_at because the listing's state meaningfully changed.
        if last_entry.clearance != clearance:
            last_entry.started_at = ts_utc

        last_entry.updated_at = ts_utc
        last_entry.price = price
        last_entry.price_was = price_was
        last_entry.pct_off = pct_off
        last_entry.availability = normalized_availability
        last_entry.product_url = product_url
        last_entry.category_url = category_url
        last_entry.title = title
        last_entry.category = category
        last_entry.clearance = clearance
        if image_url:
            last_entry.image_url = image_url
        if region is not None:
            last_entry.region = region
        entry = last_entry

    elif last_entry and state_matches:
        last_entry.updated_at = ts_utc
        last_entry.product_url = product_url
        last_entry.category_url = category_url
        last_entry.title = title
        last_entry.category = category
        if image_url:
            last_entry.image_url = image_url
        if region is not None:
            last_entry.region = region
        entry = last_entry

    else:
        entry = StorePriceHistory(
            retailer=retailer,
            store_id=store_id,
            sku=sku,
            title=title,
            category=category,
            category_url=category_url,
            started_at=ts_utc,
            updated_at=ts_utc,
            price=price,
            price_was=price_was,
            pct_off=pct_off,
            availability=normalized_availability,
            product_url=product_url,
            image_url=image_url,
            clearance=clearance,
            region=region,
        )
        session.add(entry)
        session.flush()

    if keep_history_rows > 0:
        ids_to_delete = session.scalars(
            select(StorePriceHistory.id)
            .where(
                StorePriceHistory.retailer == retailer,
                StorePriceHistory.store_id == store_id,
                StorePriceHistory.sku == sku,
            )
            .order_by(StorePriceHistory.updated_at.desc(), StorePriceHistory.id.desc())
            .offset(keep_history_rows)
        ).all()
        if ids_to_delete:
            session.execute(
                delete(StorePriceHistory).where(StorePriceHistory.id.in_(ids_to_delete))
            )

    return entry


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
    stmt, _ = _latest_history_statement()
    rows = session.execute(stmt).all()
    listings = [_row_to_listing(row) for row in rows]
    for listing in listings:
        listing["state"] = listing.get("store_state")
    return listings


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


def _latest_history_statement(
    *,
    state: str | None = None,
    category: str | None = None,
    region: str | None = None,
):
    history_alias = aliased(StorePriceHistory)
    partition_cols = (history_alias.store_id, history_alias.sku)
    row_number = func.row_number().over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )
    first_seen = func.min(history_alias.started_at).over(partition_by=partition_cols)
    prev_price = func.lag(history_alias.price).over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )
    prev_price_was = func.lag(history_alias.price_was).over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )
    prev_pct_off = func.lag(history_alias.pct_off).over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )
    prev_updated_at = func.lag(history_alias.updated_at).over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )
    prev_clearance = func.lag(history_alias.clearance).over(
        partition_by=partition_cols,
        order_by=history_alias.updated_at.desc(),
    )

    base = select(
        history_alias.id.label("history_id"),
        history_alias.retailer,
        history_alias.store_id,
        history_alias.sku,
        history_alias.title,
        history_alias.category,
        history_alias.started_at.label("price_started_at"),
        history_alias.updated_at.label("updated_at"),
        history_alias.price,
        history_alias.price_was,
        history_alias.pct_off,
        history_alias.availability,
        history_alias.product_url,
        history_alias.image_url,
        history_alias.clearance,
        Store.name.label("store_name"),
        Store.city.label("store_city"),
        Store.state.label("store_state"),
        Store.zip.label("store_zip"),
        Store.id.label("store_pk"),
        row_number.label("rn"),
        first_seen.label("first_seen"),
        prev_price.label("prev_price"),
        prev_price_was.label("prev_price_was"),
        prev_pct_off.label("prev_pct_off"),
        prev_updated_at.label("prev_updated_at"),
        prev_clearance.label("prev_clearance"),
    ).join(Store, Store.id == history_alias.store_id, isouter=True)

    subquery = base.subquery()
    stmt = (
        select(subquery).where(subquery.c.rn == 1).where(subquery.c.clearance.is_(True))
    )
    stmt = stmt.where(
        func.coalesce(subquery.c.updated_at, subquery.c.price_started_at)
        >= _active_listing_cutoff()
    )

    if region:
        stmt = stmt.join(Store, Store.id == subquery.c.store_id, isouter=True)
        stmt = stmt.where(Store.region == region)
    if state:
        stmt = stmt.where(
            func.upper(func.coalesce(subquery.c.store_state, "")) == state.upper()
        )
    if category:
        stmt = stmt.where(subquery.c.category == category)

    return stmt, subquery


def _row_to_listing(row) -> dict[str, object]:
    return {
        "history_id": row.history_id,
        "retailer": row.retailer,
        "store_id": row.store_id,
        "store_name": row.store_name,
        "store_city": row.store_city,
        "store_state": row.store_state,
        "store_zip": row.store_zip,
        "sku": row.sku,
        "title": row.title,
        "category": row.category,
        "price": row.price,
        "price_was": row.price_was,
        "pct_off": row.pct_off,
        "availability": row.availability,
        "product_url": row.product_url,
        "image_url": row.image_url,
        "clearance": row.clearance,
        "first_seen": row.first_seen,
        "price_started_at": row.price_started_at,
        "updated_at": row.updated_at,
        "prev_price": row.prev_price,
        "prev_price_was": row.prev_price_was,
        "prev_pct_off": row.prev_pct_off,
        "prev_updated_at": row.prev_updated_at,
        "prev_clearance": row.prev_clearance,
    }


def get_listing_for_store_and_sku(
    session: Session,
    *,
    store_id: str,
    sku: str,
) -> dict[str, object] | None:
    """Return the freshest listing for a specific store/SKU pair."""

    if not store_id or not sku:
        return None
    stmt, subquery = _latest_history_statement()
    stmt = (
        stmt.where(subquery.c.store_id == store_id)
        .where(subquery.c.sku == sku)
        .limit(1)
    )
    row = session.execute(stmt).one_or_none()
    if row is None:
        return None
    return _row_to_listing(row)


def get_clearance_items(
    session: Session,
    *,
    state: str | None = None,
    category: str | None = None,
    region: str | None = None,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Return the latest clearance listings per store/SKU."""

    stmt, subquery = _latest_history_statement(
        state=state, category=category, region=region
    )
    stmt = stmt.order_by(
        subquery.c.pct_off.desc().nullslast(),
        subquery.c.price.asc().nullslast(),
        subquery.c.updated_at.desc(),
    )
    if limit:
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    return [_row_to_listing(row) for row in rows]


def get_new_clearance_today(
    session: Session,
    *,
    state: str | None = None,
    category: str | None = None,
    region: str | None = None,
) -> list[dict[str, object]]:
    """Return items that transitioned to clearance within the last 24 hours."""

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    stmt, subquery = _latest_history_statement(
        state=state, category=category, region=region
    )
    stmt = stmt.where(subquery.c.price_started_at >= cutoff).where(
        or_(
            subquery.c.prev_clearance.is_(False),
            subquery.c.prev_clearance.is_(None),
        )
    )
    stmt = stmt.order_by(
        subquery.c.pct_off.desc().nullslast(),
        subquery.c.price_started_at.desc(),
    )
    rows = session.execute(stmt).all()
    return [_row_to_listing(row) for row in rows]


def get_older_clearance_items(
    session: Session,
    *,
    state: str | None = None,
    category: str | None = None,
    region: str | None = None,
    min_days_old: int = 5,
) -> list[dict[str, object]]:
    """Return clearance items that are at least min_days_old days old (for free tier).

    Important: "age" for the paywall is based on *last seen* time, not when the
    clearance price first started. Otherwise an item that went on clearance 2
    weeks ago but was scraped 5 minutes ago would look "fresh" in the UI even
    for free users.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(days=min_days_old)
    stmt, subquery = _latest_history_statement(
        state=state, category=category, region=region
    )
    # Filter by last observation time to enforce the 72h delayed view.
    stmt = stmt.where(func.coalesce(subquery.c.updated_at, subquery.c.price_started_at) <= cutoff)
    stmt = stmt.order_by(
        subquery.c.pct_off.desc().nullslast(),
        subquery.c.price_started_at.desc(),
    )
    rows = session.execute(stmt).all()
    return [_row_to_listing(row) for row in rows]


def get_clearance_by_category(
    session: Session,
    category: str,
    *,
    state: str | None = None,
    region: str | None = None,
    limit: int | None = None,
) -> list[Observation]:
    """Return clearance observations filtered by category name."""

    return get_clearance_items(
        session,
        state=state,
        category=category,
        region=region,
        limit=limit,
    )


def delete_store_listing(
    session: Session,
    *,
    retailer: str,
    store_id: str,
    product_url: str,
    category_url: str | None = None,
) -> dict[str, int | bool]:
    """Delete all stored records for a single store-specific listing."""

    if not store_id or not product_url:
        return {
            "removed": False,
            "history_rows_deleted": 0,
            "observation_rows_deleted": 0,
        }

    history_conditions = [
        StorePriceHistory.retailer == retailer,
        StorePriceHistory.store_id == store_id,
        StorePriceHistory.product_url == product_url,
    ]
    observation_conditions = [
        Observation.retailer == retailer,
        Observation.store_id == store_id,
        Observation.product_url == product_url,
    ]
    if category_url:
        history_conditions.append(
            or_(
                StorePriceHistory.category_url == category_url,
                StorePriceHistory.category_url.is_(None),
            )
        )
        observation_conditions.append(
            or_(
                Observation.category_url == category_url,
                Observation.category_url.is_(None),
            )
        )

    history_rows_deleted = (
        session.execute(delete(StorePriceHistory).where(and_(*history_conditions))).rowcount
        or 0
    )
    observation_rows_deleted = (
        session.execute(delete(Observation).where(and_(*observation_conditions))).rowcount
        or 0
    )

    return {
        "removed": (history_rows_deleted + observation_rows_deleted) > 0,
        "history_rows_deleted": int(history_rows_deleted),
        "observation_rows_deleted": int(observation_rows_deleted),
    }


def cleanup_stale_clearance_data(
    session: Session,
    *,
    retailer: str = "lowes",
    max_age_days: int | None = None,
) -> dict[str, int]:
    """Delete old clearance rows so stale data does not accumulate forever."""

    resolved_days = max_age_days if max_age_days is not None else get_max_listing_age_days()
    if resolved_days <= 0:
        return {"history_rows_deleted": 0, "observation_rows_deleted": 0}

    cutoff = datetime.now(timezone.utc) - timedelta(days=resolved_days)
    stale_history_pairs = (
        select(StorePriceHistory.store_id, StorePriceHistory.sku)
        .where(StorePriceHistory.retailer == retailer)
        .group_by(StorePriceHistory.store_id, StorePriceHistory.sku)
        .having(func.max(StorePriceHistory.updated_at) < cutoff)
        .subquery()
    )
    stale_observation_pairs = (
        select(Observation.store_id, Observation.sku)
        .where(Observation.retailer == retailer)
        .group_by(Observation.store_id, Observation.sku)
        .having(func.max(Observation.ts_utc) < cutoff)
        .subquery()
    )
    history_rows_deleted = (
        session.execute(
            delete(StorePriceHistory).where(
                StorePriceHistory.retailer == retailer,
                exists(
                    select(1)
                    .select_from(stale_history_pairs)
                    .where(stale_history_pairs.c.store_id == StorePriceHistory.store_id)
                    .where(stale_history_pairs.c.sku == StorePriceHistory.sku)
                ),
            )
        ).rowcount
        or 0
    )
    observation_rows_deleted = (
        session.execute(
            delete(Observation).where(
                Observation.retailer == retailer,
                exists(
                    select(1)
                    .select_from(stale_observation_pairs)
                    .where(stale_observation_pairs.c.store_id == Observation.store_id)
                    .where(stale_observation_pairs.c.sku == Observation.sku)
                ),
            )
        ).rowcount
        or 0
    )

    return {
        "history_rows_deleted": int(history_rows_deleted),
        "observation_rows_deleted": int(observation_rows_deleted),
    }


def normalize_availability_records(session: Session) -> int:
    """Backfill stored availability text to human-readable values."""

    total_updates = 0

    schema_filter = or_(
        Observation.availability.like("http://schema.org/%"),
        Observation.availability.like("https://schema.org/%"),
    )
    for obs in session.scalars(select(Observation).where(schema_filter)):
        normalized = normalize_availability(obs.availability)
        if normalized != obs.availability:
            obs.availability = normalized
            total_updates += 1

    history_filter = or_(
        StorePriceHistory.availability.like("http://schema.org/%"),
        StorePriceHistory.availability.like("https://schema.org/%"),
    )
    for entry in session.scalars(select(StorePriceHistory).where(history_filter)):
        normalized = normalize_availability(entry.availability)
        if normalized != entry.availability:
            entry.availability = normalized
            total_updates += 1

    if total_updates:
        session.flush()

    return total_updates


def count_observations(session: Session) -> int:
    stmt = select(func.count(Observation.id))
    return int(session.scalar(stmt) or 0)


def count_quarantine(session: Session) -> int:
    stmt = select(func.count(Quarantine.id))
    return int(session.scalar(stmt) or 0)


def get_latest_timestamp(session: Session) -> datetime | None:
    """Return the most recent observation timestamp."""

    obs_ts = session.scalar(select(func.max(Observation.ts_utc)))
    hist_ts = session.scalar(select(func.max(StorePriceHistory.updated_at)))

    if obs_ts and hist_ts:
        return max(obs_ts, hist_ts)
    return obs_ts or hist_ts or None


def list_distinct_categories(
    session: Session,
    *,
    state: str | None = None,
    region: str | None = None,
    min_pct_off: float | None = None,
) -> list[str]:
    """Return sorted list of categories with active clearance inventory."""

    _, subquery = _latest_history_statement(state=state, region=region)
    stmt = (
        select(subquery.c.category)
        .where(subquery.c.rn == 1)
        .where(subquery.c.clearance.is_(True))
    )
    if min_pct_off is not None:
        stmt = stmt.where(subquery.c.pct_off >= min_pct_off)

    stmt = stmt.distinct().order_by(subquery.c.category.asc())

    resolved: dict[str, str] = {}
    for row in session.execute(stmt):
        raw = (row[0] or "").strip()
        if not raw:
            continue
        key = raw.casefold()
        resolved.setdefault(key, raw)
    return sorted(resolved.values(), key=lambda value: value.casefold())


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
    def _ts(value: object | None) -> str:
        if hasattr(value, "astimezone"):
            return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")  # type: ignore[attr-defined]
        return str(value) if value is not None else ""

    def _fmt(value: object | None) -> str:
        return "" if value is None else f"{value}"

    observed_ts = (
        row.get("ts_utc") or row.get("first_seen") or row.get("price_started_at")
    )

    return [
        _ts(observed_ts),
        row.get("retailer", "") or "",
        row.get("store_id", "") or "",
        row.get("store_name", "") or "",
        row.get("state", "") or row.get("store_state", "") or "",
        row.get("store_zip", "") or row.get("zip", "") or "",
        row.get("sku", "") or "",
        row.get("title", "") or "",
        row.get("category", "") or "",
        _fmt(row.get("price")),
        _fmt(row.get("price_was")),
        _fmt(row.get("pct_off")),
        row.get("availability", "") or "",
        _ts(row.get("first_seen") or row.get("price_started_at")),
        _ts(row.get("updated_at")),
        _ts(row.get("price_started_at")),
        _fmt(row.get("prev_price")),
        _fmt(row.get("prev_price_was")),
        _ts(row.get("prev_updated_at")),
        row.get("product_url", "") or "",
        row.get("image_url", "") or "",
    ]
