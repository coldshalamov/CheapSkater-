from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.storage import repo
from app.storage.db import init_db
from app.storage.models_sql import Observation, Quarantine, Store


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

    wa_results = repo.get_clearance_items(db_session, state="WA")
    assert {row.store_id for row in wa_results} == {store_wa.id}

    or_results = repo.get_clearance_items(db_session, state="OR")
    assert {row.store_id for row in or_results} == {store_or.id}


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
