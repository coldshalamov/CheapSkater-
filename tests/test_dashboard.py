from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.dashboard import _normalize_state, _state_from_zip, app, session_factory
from app.storage import repo
from app.storage.models_sql import Observation, Store, StorePriceHistory


def test_normalize_state() -> None:
    assert _normalize_state("wa") == "WA"
    assert _normalize_state("OR") == "OR"
    assert _normalize_state("xx") is None


def test_state_from_zip() -> None:
    assert _state_from_zip("97205") == "OR"
    assert _state_from_zip("98101") == "WA"
    assert _state_from_zip("12345") is None


def test_api_clearance_filters_state(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store_wa = Store(id="store-wa", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        store_or = Store(id="store-or", name="Salem Lowe's", city="Salem", state="OR", zip="97301")
        session.add_all([store_wa, store_or])
        session.flush()

        obs_rows = [
            Observation(
                ts_utc=datetime.now(timezone.utc),
                store_id=store_wa.id,
                store_name=store_wa.name,
                zip=store_wa.zip,
                sku="sku-wa",
                retailer="lowes",
                title="Roofing Bundle",
                category="Roofing",
                product_url="https://example.com/wa",
                image_url=None,
                price=25.0,
                price_was=50.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=datetime.now(timezone.utc),
                store_id=store_or.id,
                store_name=store_or.name,
                zip=store_or.zip,
                sku="sku-or",
                retailer="lowes",
                title="Drywall Panel",
                category="Drywall",
                product_url="https://example.com/or",
                image_url=None,
                price=10.0,
                price_was=15.0,
                pct_off=0.33,
                clearance=True,
                availability="Limited",
            ),
        ]
        session.add_all(obs_rows)
        session.commit()

        for obs in obs_rows:
            repo.update_price_history(
                session,
                retailer="lowes",
                store_id=obs.store_id,
                sku=obs.sku,
                title=obs.title,
                category=obs.category,
                ts_utc=obs.ts_utc,
                price=obs.price,
                price_was=obs.price_was,
                pct_off=obs.pct_off,
                availability=obs.availability,
                product_url=obs.product_url,
                image_url=obs.image_url,
                clearance=obs.clearance,
            )
        session.commit()

    client = TestClient(app)
    response = client.get("/api/clearance", params={"scope": "all", "state": "WA"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["state"] == "WA"
    assert payload["items"][0]["store_id"] == "store-wa"


def test_api_sort_orders(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        now = datetime.now(timezone.utc)
        stores = []
        for idx in range(3):
            store = Store(
                id=f"store-sort-{idx}",
                name=f"Sort Store {idx}",
                city="Seattle",
                state="WA",
                zip=f"9810{idx}",
            )
            stores.append(store)
        session.add_all(stores)
        session.flush()

        titles_prices = [
            ("Alpha Shingles", 25.0, now - timedelta(hours=1), "sku-alpha"),
            ("Gamma Drill", 15.0, now - timedelta(hours=3), "sku-gamma"),
            ("Beta Ladder", 35.0, now - timedelta(minutes=30), "sku-beta"),
        ]
        obs_rows = []
        for idx, (title, price, ts_utc, sku) in enumerate(titles_prices):
            obs = Observation(
                ts_utc=ts_utc,
                store_id=stores[idx].id,
                store_name=stores[idx].name,
                zip=stores[idx].zip,
                sku=sku,
                retailer="lowes",
                title=title,
                category="Tools",
                product_url=f"https://example.com/{sku}",
                image_url=None,
                price=price,
                price_was=price * 1.5,
                pct_off=0.25,
                clearance=True,
                availability="In stock",
            )
            obs_rows.append(obs)
        session.add_all(obs_rows)
        session.commit()

        for obs in obs_rows:
            repo.update_price_history(
                session,
                retailer="lowes",
                store_id=obs.store_id,
                sku=obs.sku,
                title=obs.title,
                category=obs.category,
                ts_utc=obs.ts_utc,
                price=obs.price,
                price_was=obs.price_was,
                pct_off=obs.pct_off,
                availability=obs.availability,
                product_url=obs.product_url,
                image_url=obs.image_url,
                clearance=obs.clearance,
            )
        session.commit()

    client = TestClient(app)
    newest = client.get("/api/clearance")
    assert newest.status_code == 200
    newest_titles = [group["title"] for group in newest.json()["groups"]]
    assert newest_titles[0] == "Beta Ladder"

    alpha_desc = client.get("/api/clearance", params={"sort_order": "alpha_desc"})
    assert alpha_desc.status_code == 200
    alpha_titles = [group["title"] for group in alpha_desc.json()["groups"]]
    assert alpha_titles == sorted(alpha_titles, reverse=True)

    price_low = client.get("/api/clearance", params={"sort_order": "price_low"})
    assert price_low.status_code == 200
    low_prices = [group["min_price"] for group in price_low.json()["groups"]]
    assert low_prices == sorted(low_prices)
