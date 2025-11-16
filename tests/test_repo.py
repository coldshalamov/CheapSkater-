from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.storage import repo
from app.storage.db import init_db
from app.storage.models_sql import Observation, Quarantine, Store, StorePriceHistory


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    Session = sessionmaker(engine, future=True)
    try:
        with Session() as session:
            yield session
    finally:
        engine.dispose()


def _make_obs(
    *,
    clearance: bool | None,
    price: float | None = None,
    price_was: float | None = None,
    pct_off: float | None = None,
) -> Observation:
    return Observation(
        ts_utc=datetime.now(timezone.utc),
        store_id="store-1",
        store_name="Store 1",
        zip="97204",
        sku="sku-1",
        retailer="lowes",
        title="Item One",
        category="Roofing",
        product_url="https://example.com/pd/sku-1",
        image_url=None,
        price=price,
        price_was=price_was,
        pct_off=pct_off,
        clearance=clearance,
        availability=None,
    )


def test_should_alert_new_clearance_flagged_initial() -> None:
    new_obs = _make_obs(clearance=True, price=80, price_was=100)
    assert repo.should_alert_new_clearance(None, new_obs) is True


def test_should_not_alert_when_clearance_already_seen() -> None:
    last_obs = _make_obs(clearance=True, price=80, price_was=100)
    new_obs = _make_obs(clearance=True, price=75, price_was=100)
    assert repo.should_alert_new_clearance(last_obs, new_obs) is False


def test_should_not_alert_when_clearance_false() -> None:
    last_obs = _make_obs(clearance=False, price=80, price_was=100)
    new_obs = _make_obs(clearance=False, price=60, price_was=100)
    assert repo.should_alert_new_clearance(last_obs, new_obs) is False


def test_should_alert_price_drop_threshold() -> None:
    last_obs = _make_obs(clearance=False, price=100)
    new_obs = _make_obs(clearance=False, price=70)
    assert repo.should_alert_price_drop(last_obs, new_obs, 0.25) is True


def test_should_not_alert_price_drop_when_threshold_not_met() -> None:
    last_obs = _make_obs(clearance=False, price=100)
    new_obs = _make_obs(clearance=False, price=90)
    assert repo.should_alert_price_drop(last_obs, new_obs, 0.25) is False


def test_get_clearance_items_filters_by_state(db_session) -> None:
    store_wa = Store(id="wa", name="Tacoma Lowe's", city="Tacoma", state="WA", zip="98402")
    store_or = Store(id="or", name="Portland Lowe's", city="Portland", state="OR", zip="97204")
    db_session.add_all([store_wa, store_or])
    db_session.flush()

    obs_wa = Observation(
        ts_utc=datetime.now(timezone.utc),
        store_id=store_wa.id,
        store_name=store_wa.name,
        zip=store_wa.zip,
        sku="sku-wa",
        retailer="lowes",
        title="Roof Shingle",
        category="Roofing",
        product_url="https://example.com/wa",
        image_url=None,
        price=49.0,
        price_was=89.0,
        pct_off=0.45,
        clearance=True,
        availability="In stock",
    )
    obs_or = Observation(
        ts_utc=datetime.now(timezone.utc),
        store_id=store_or.id,
        store_name=store_or.name,
        zip=store_or.zip,
        sku="sku-or",
        retailer="lowes",
        title="Drywall Sheet",
        category="Drywall",
        product_url="https://example.com/or",
        image_url=None,
        price=12.0,
        price_was=20.0,
        pct_off=0.4,
        clearance=True,
        availability="Limited",
    )
    db_session.add_all([obs_wa, obs_or])
    db_session.commit()

    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id=store_wa.id,
        sku=obs_wa.sku,
        title=obs_wa.title,
        category=obs_wa.category,
        ts_utc=obs_wa.ts_utc,
        price=obs_wa.price,
        price_was=obs_wa.price_was,
        pct_off=obs_wa.pct_off,
        availability=obs_wa.availability,
        product_url=obs_wa.product_url,
        image_url=obs_wa.image_url,
        clearance=True,
    )
    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id=store_or.id,
        sku=obs_or.sku,
        title=obs_or.title,
        category=obs_or.category,
        ts_utc=obs_or.ts_utc,
        price=obs_or.price,
        price_was=obs_or.price_was,
        pct_off=obs_or.pct_off,
        availability=obs_or.availability,
        product_url=obs_or.product_url,
        image_url=obs_or.image_url,
        clearance=True,
    )
    db_session.commit()

    wa_results = repo.get_clearance_items(db_session, state="WA")
    assert {row["store_id"] for row in wa_results} == {store_wa.id}

    or_results = repo.get_clearance_items(db_session, state="OR")
    assert {row["store_id"] for row in or_results} == {store_or.id}


def test_list_distinct_categories_sorted(db_session) -> None:
    store = Store(id="store", name="Everett Lowe's", city="Everett", state="WA", zip="98201")
    db_session.add(store)
    db_session.flush()

    categories = ["Drywall", "Roofing", "Roofing", "Insulation"]
    for idx, name in enumerate(categories, start=1):
        db_session.add(
            Observation(
                ts_utc=datetime.now(timezone.utc),
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku=f"sku-{idx}",
                retailer="lowes",
                title=f"Item {idx}",
                category=name,
                product_url=f"https://example.com/{idx}",
                image_url=None,
                price=10.0,
                price_was=15.0,
                pct_off=0.33,
                clearance=True,
                availability=None,
            )
        )
    db_session.commit()

    results = repo.list_distinct_categories(db_session)
    assert results == sorted(set(categories))


def test_insert_quarantine_records_payload(db_session) -> None:
    repo.insert_quarantine(
        db_session,
        retailer="lowes",
        store_id="store-x",
        sku="sku-x",
        zip_code="97201",
        state="OR",
        category="Roofing",
        reason="invalid_price",
        payload={"price": "bad"},
    )
    db_session.commit()

    record = db_session.execute(select(Quarantine)).scalar_one()
    assert record.reason == "invalid_price"
    assert "bad" in record.payload
    assert record.state == "OR"


def test_update_price_history_creates_and_updates(db_session) -> None:
    now = datetime.now(timezone.utc)
    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id="store-1",
        sku="sku-1",
        title="Item One",
        category="Roofing",
        ts_utc=now,
        price=10.0,
        price_was=15.0,
        pct_off=0.33,
        availability="https://schema.org/InStock",
        product_url="https://example.com/p1",
        image_url=None,
        clearance=True,
    )
    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id="store-1",
        sku="sku-1",
        title="Item One",
        category="Roofing",
        ts_utc=now + timedelta(hours=2),
        price=10.0,
        price_was=15.0,
        pct_off=0.33,
        availability="In Stock",
        product_url="https://example.com/p1",
        image_url=None,
        clearance=True,
    )
    records = db_session.execute(select(StorePriceHistory)).scalars().all()
    assert len(records) == 1
    assert records[0].availability == "In Stock"
    assert records[0].updated_at > records[0].started_at


def test_update_price_history_adds_new_row_on_price_change(db_session) -> None:
    now = datetime.now(timezone.utc)
    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id="store-1",
        sku="sku-1",
        title="Item One",
        category="Roofing",
        ts_utc=now,
        price=10.0,
        price_was=15.0,
        pct_off=0.33,
        availability="In Stock",
        product_url="https://example.com/p1",
        image_url=None,
        clearance=True,
    )
    repo.update_price_history(
        db_session,
        retailer="lowes",
        store_id="store-1",
        sku="sku-1",
        title="Item One",
        category="Roofing",
        ts_utc=now + timedelta(hours=5),
        price=7.5,
        price_was=15.0,
        pct_off=0.5,
        availability="In Stock",
        product_url="https://example.com/p1",
        image_url=None,
        clearance=True,
    )
    rows = db_session.execute(
        select(StorePriceHistory).order_by(StorePriceHistory.started_at.asc())
    ).scalars().all()
    assert len(rows) == 2
    assert rows[-1].price == 7.5
    assert rows[0].price == 10.0


def test_normalize_availability_records_updates_schema_entries(db_session) -> None:
    obs = Observation(
        ts_utc=datetime.now(timezone.utc),
        store_id="store-1",
        store_name="Store 1",
        zip="97204",
        sku="sku-1",
        retailer="lowes",
        title="Item One",
        category="Roofing",
        product_url="https://example.com/pd/sku-1",
        image_url=None,
        price=10.0,
        price_was=15.0,
        pct_off=0.33,
        clearance=True,
        availability="https://schema.org/InStock",
    )
    db_session.add(obs)
    db_session.add(
        StorePriceHistory(
            retailer="lowes",
            store_id="store-1",
            sku="sku-1",
            title="Item One",
            category="Roofing",
            started_at=datetime.now(timezone.utc) - timedelta(days=1),
            updated_at=datetime.now(timezone.utc),
            price=10.0,
            price_was=15.0,
            pct_off=0.33,
            availability="https://schema.org/OutOfStock",
            product_url="https://example.com/pd/sku-1",
            image_url=None,
            clearance=True,
        )
    )
    db_session.commit()
    updated = repo.normalize_availability_records(db_session)
    assert updated == 2
    db_session.commit()

    assert db_session.scalar(select(Observation.availability)) == "In Stock"
    history_avail = db_session.scalar(select(StorePriceHistory.availability))
    assert history_avail == "Out of Stock"
