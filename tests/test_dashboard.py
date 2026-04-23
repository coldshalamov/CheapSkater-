from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from sqlalchemy import delete

import app.dashboard as dashboard
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

        now = datetime.now(timezone.utc) - timedelta(days=6)
        obs_rows = [
            Observation(
                ts_utc=now,
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
                ts_utc=now,
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


def test_api_clearance_discount_filter_handles_pct_off_units(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store = Store(id="store-discount", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        session.add(store)
        session.flush()

        now = datetime.now(timezone.utc) - timedelta(days=6)
        obs_rows = [
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-percent",
                retailer="lowes",
                title="Percent Deal",
                category="Tools",
                product_url="https://example.com/percent",
                image_url=None,
                price=10.0,
                price_was=None,
                pct_off=80.0,  # percent
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-percent-low",
                retailer="lowes",
                title="Low Percent Deal",
                category="Tools",
                product_url="https://example.com/percent-low",
                image_url=None,
                price=10.0,
                price_was=None,
                pct_off=5.0,  # percent
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-fraction",
                retailer="lowes",
                title="Fraction Deal",
                category="Tools",
                product_url="https://example.com/fraction",
                image_url=None,
                price=10.0,
                price_was=None,
                pct_off=0.60,  # fraction
                clearance=True,
                availability="In stock",
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
    response = client.get("/api/clearance", params={"discount_filter": "75"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["items"][0]["sku"] == "sku-percent"


def test_api_clearance_search_filters_results(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store = Store(id="store-search", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        session.add(store)
        session.flush()

        now = datetime.now(timezone.utc) - timedelta(days=6)
        obs_rows = [
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-roof",
                retailer="lowes",
                title="Roofing Bundle",
                category="Roofing",
                product_url="https://example.com/roof",
                image_url=None,
                price=25.0,
                price_was=50.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-drywall",
                retailer="lowes",
                title="Drywall Panel",
                category="Drywall",
                product_url="https://example.com/drywall",
                image_url=None,
                price=10.0,
                price_was=15.0,
                pct_off=0.33,
                clearance=True,
                availability="In stock",
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
    response = client.get("/api/clearance", params={"discount_filter": "all", "search": "roof"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["items"][0]["sku"] == "sku-roof"


def test_api_categories_returns_unique_sorted(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store = Store(id="store-cat", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        session.add(store)
        session.flush()

        now = datetime.now(timezone.utc) - timedelta(days=6)
        obs_rows = [
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-fans",
                retailer="lowes",
                title="Portable Fan",
                category="Portable Fans",
                product_url="https://example.com/fans",
                image_url=None,
                price=25.0,
                price_was=50.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-parts",
                retailer="lowes",
                title="Dishwasher Part",
                category="Dishwasher Parts",
                product_url="https://example.com/parts",
                image_url=None,
                price=10.0,
                price_was=20.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
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
    response = client.get("/api/categories")
    assert response.status_code == 200
    categories = response.json()
    assert categories == ["Dishwasher Parts", "Portable Fans"]


def test_api_deals_filters_by_category(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store = Store(id="store-deals", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        session.add(store)
        session.flush()

        now = datetime.now(timezone.utc) - timedelta(days=6)
        obs_rows = [
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-keep",
                retailer="lowes",
                title="Portable Fan",
                category="Portable Fans",
                product_url="https://example.com/fans",
                image_url=None,
                price=25.0,
                price_was=50.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=now,
                store_id=store.id,
                store_name=store.name,
                zip=store.zip,
                sku="sku-drop",
                retailer="lowes",
                title="Dishwasher Part",
                category="Dishwasher Parts",
                product_url="https://example.com/parts",
                image_url=None,
                price=10.0,
                price_was=20.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
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
    response = client.get("/api/deals", params={"category": "Portable Fans"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["category"] == "Portable Fans"
    assert payload["items"][0]["category"] == "Portable Fans"


def test_api_sort_orders(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        now = datetime.now(timezone.utc) - timedelta(days=6)
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
    newest = client.get("/api/clearance", params={"discount_filter": "all"})
    assert newest.status_code == 200
    newest_titles = [group["title"] for group in newest.json()["groups"]]
    assert newest_titles[0] == "Beta Ladder"

    alpha_desc = client.get(
        "/api/clearance", params={"sort_order": "alpha_desc", "discount_filter": "all"}
    )
    assert alpha_desc.status_code == 200
    alpha_titles = [group["title"] for group in alpha_desc.json()["groups"]]
    assert alpha_titles == sorted(alpha_titles, reverse=True)

    price_low = client.get(
        "/api/clearance", params={"sort_order": "price_low", "discount_filter": "all"}
    )
    assert price_low.status_code == 200
    low_prices = [group["min_price"] for group in price_low.json()["groups"]]
    assert low_prices == sorted(low_prices)


def test_grouped_cards_keep_best_price_actions_separate_from_primary_store() -> None:
    recent_seen = datetime(2026, 4, 9, 18, 57, tzinfo=timezone.utc)
    cheaper_seen = datetime(2026, 4, 7, 15, 30, tzinfo=timezone.utc)
    listings = [
        {
            "sku": "sku-best-price",
            "store_id": "recent-store",
            "store_name": "Recent Store",
            "store_city": "Recentville",
            "store_state": "FL",
            "title": "Pressure Washer",
            "category": "Tools",
            "price": 40.0,
            "price_was": 80.0,
            "pct_off": 0.5,
            "product_url": "https://example.com/recent",
            "store_product_url": "https://example.com/recent?store=recent-store",
            "updated_at": recent_seen,
            "first_seen": recent_seen - timedelta(days=2),
        },
        {
            "sku": "sku-best-price",
            "store_id": "cheap-store",
            "store_name": "Cheapest Store",
            "store_city": "Dealton",
            "store_state": "FL",
            "title": "Pressure Washer",
            "category": "Tools",
            "price": 18.0,
            "price_was": 60.0,
            "pct_off": 0.7,
            "product_url": "https://example.com/cheap",
            "store_product_url": "https://example.com/cheap?store=cheap-store",
            "updated_at": cheaper_seen,
            "first_seen": cheaper_seen - timedelta(days=4),
        },
    ]

    grouped = dashboard._group_listings(listings)
    payload = dashboard._serialize_group(grouped[0])

    assert payload["stores"][0]["store_id"] == "recent-store"
    assert payload["best_store_id"] == "cheap-store"
    assert payload["best_product_url"] == "https://example.com/cheap?store=cheap-store"
    assert payload["min_price"] == 18.0


def test_api_clearance_freshness_filters_items_and_groups_consistently(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store_fresh = Store(id="store-freshness-1", name="Fresh Store", city="Miami", state="FL", zip="33101", region="FL")
        store_stale = Store(id="store-freshness-2", name="Stale Store", city="Tampa", state="FL", zip="33602", region="FL")
        session.add_all([store_fresh, store_stale])
        session.flush()

        now = datetime.now(timezone.utc)
        observations = [
            Observation(
                ts_utc=now - timedelta(days=2),
                store_id=store_fresh.id,
                store_name=store_fresh.name,
                zip=store_fresh.zip,
                sku="sku-freshness-keep",
                retailer="lowes",
                title="Keep Me",
                category="Tools",
                product_url="https://example.com/keep",
                image_url=None,
                price=20.0,
                price_was=40.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
                region="FL",
            ),
            Observation(
                ts_utc=now - timedelta(days=5),
                store_id=store_stale.id,
                store_name=store_stale.name,
                zip=store_stale.zip,
                sku="sku-freshness-drop",
                retailer="lowes",
                title="Drop Me",
                category="Tools",
                product_url="https://example.com/drop",
                image_url=None,
                price=15.0,
                price_was=30.0,
                pct_off=0.5,
                clearance=True,
                availability="Limited stock",
                region="FL",
            ),
        ]
        session.add_all(observations)
        session.commit()

        for obs in observations:
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
                region=obs.region,
            )
        session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/clearance",
        params={"discount_filter": "all", "freshness": "3d"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 1
    assert [item["sku"] for item in payload["items"]] == ["sku-freshness-keep"]
    assert [group["sku"] for group in payload["groups"]] == ["sku-freshness-keep"]
    assert payload["filters"]["freshness_choice"] == "3d"


def test_homepage_shows_per_store_observed_times_for_grouped_deals(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store_primary = Store(
            id="1109",
            name="Stuart Lowe's",
            city="Stuart",
            state="FL",
            zip="34994",
            region="FL",
        )
        store_secondary = Store(
            id="1841",
            name="Hialeah Lowe's",
            city="Hialeah",
            state="FL",
            zip="33012",
            region="FL",
        )
        session.add_all([store_primary, store_secondary])
        session.flush()

        primary_seen = datetime(2026, 4, 9, 18, 57, tzinfo=timezone.utc)
        secondary_seen = datetime(2026, 4, 2, 14, 15, tzinfo=timezone.utc)
        observations = [
            Observation(
                ts_utc=primary_seen,
                store_id=store_primary.id,
                store_name=store_primary.name,
                zip=store_primary.zip,
                sku="sku-grouped",
                retailer="lowes",
                title="Grouped Deal",
                category="Tools",
                product_url="https://example.com/grouped?store=1109",
                image_url=None,
                price=12.0,
                price_was=24.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
            ),
            Observation(
                ts_utc=secondary_seen,
                store_id=store_secondary.id,
                store_name=store_secondary.name,
                zip=store_secondary.zip,
                sku="sku-grouped",
                retailer="lowes",
                title="Grouped Deal",
                category="Tools",
                product_url="https://example.com/grouped?store=1841",
                image_url=None,
                price=14.0,
                price_was=28.0,
                pct_off=0.5,
                clearance=True,
                availability="Limited stock",
            ),
        ]
        session.add_all(observations)
        session.commit()

        for obs in observations:
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
    response = client.get("/", params={"discount_filter": "all"})

    assert response.status_code == 200
    assert "Most recently seen at any store Apr 09, 2026 01:57 PM ET" in response.text
    assert "Seen at this store Apr 09, 2026 01:57 PM ET" in response.text
    assert "Seen at this store Apr 02, 2026 09:15 AM ET" in response.text


def test_homepage_store_pills_respect_freshness_filter(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        recent_store = Store(
            id="3010",
            name="Fresh Picks Store",
            city="Orlando",
            state="FL",
            zip="32801",
            region="FL",
        )
        stale_store = Store(
            id="3011",
            name="Old Sightings Store",
            city="Tallahassee",
            state="FL",
            zip="32301",
            region="FL",
        )
        session.add_all([recent_store, stale_store])
        session.flush()

        now = datetime.now(timezone.utc)
        observations = [
            Observation(
                ts_utc=now - timedelta(days=2),
                store_id=recent_store.id,
                store_name=recent_store.name,
                zip=recent_store.zip,
                sku="sku-store-pill-fresh",
                retailer="lowes",
                title="Fresh Deal",
                category="Lighting",
                product_url="https://example.com/fresh-pill",
                image_url=None,
                price=9.0,
                price_was=18.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
                region="FL",
            ),
            Observation(
                ts_utc=now - timedelta(days=5),
                store_id=stale_store.id,
                store_name=stale_store.name,
                zip=stale_store.zip,
                sku="sku-store-pill-stale",
                retailer="lowes",
                title="Stale Deal",
                category="Lighting",
                product_url="https://example.com/stale-pill",
                image_url=None,
                price=11.0,
                price_was=22.0,
                pct_off=0.5,
                clearance=True,
                availability="In stock",
                region="FL",
            ),
        ]
        session.add_all(observations)
        session.commit()

        for obs in observations:
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
                region=obs.region,
            )
        session.commit()

    client = TestClient(app)
    response = client.get("/", params={"discount_filter": "all", "freshness": "3d"})

    assert response.status_code == 200
    assert "Fresh Picks Store" in response.text
    assert "Old Sightings Store" not in response.text


def test_ingest_route_normalizes_suspicious_category_names(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

    client = TestClient(app)
    ingest_response = client.post(
        "/api/ingest/deals",
        json={
            "source": "test-suite",
            "deals": [
                {
                    "store_id": "1109",
                    "store_name": "Stuart, FL (#1109)",
                    "category_name": "0 1 Foot Long",
                    "category_url": "https://www.lowes.com/pl/air-conditioners-fans/portable-fans/4294856700",
                    "product_url": "https://www.lowes.com/pd/Portable-Fan/5001844889",
                    "title": "Portable Fan",
                    "image_url": None,
                    "price": 10.0,
                    "was_price": 20.0,
                    "pct_off": 50.0,
                    "found_at": "2026-04-09T18:57:00Z",
                }
            ],
        },
    )

    assert ingest_response.status_code == 200
    assert ingest_response.json()["accepted"] == 1

    categories = client.get("/api/categories")
    assert categories.status_code == 200
    assert "Portable Fans" in categories.json()
    assert "0 1 Foot Long" not in categories.json()

    clearance = client.get("/api/clearance", params={"discount_filter": "all"})
    assert clearance.status_code == 200
    assert clearance.json()["items"][0]["category"] == "Portable Fans"

    homepage = client.get("/", params={"discount_filter": "all"})
    assert homepage.status_code == 200
    assert "Portable Fans" in homepage.text
    assert "0 1 Foot Long" not in homepage.text


def test_ingest_route_preserves_good_new_worker_category_names(tmp_path) -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

    client = TestClient(app)
    ingest_response = client.post(
        "/api/ingest/deals",
        json={
            "source": "test-suite",
            "deals": [
                {
                    "store_id": "1109",
                    "store_name": "Stuart, FL (#1109)",
                    "category_name": "Ethernet Cables",
                    "category_url": "https://www.lowes.com/pl/electrical-cable-wire/networking-cable/4294418126",
                    "product_url": "https://www.lowes.com/pd/Ethernet-Cable/5001844999",
                    "title": "Ethernet Cable",
                    "image_url": None,
                    "price": 12.0,
                    "was_price": 24.0,
                    "pct_off": 50.0,
                    "found_at": "2026-04-09T18:57:00Z",
                }
            ],
        },
    )

    assert ingest_response.status_code == 200
    assert ingest_response.json()["accepted"] == 1

    categories = client.get("/api/categories")
    assert categories.status_code == 200
    assert "Ethernet Cables" in categories.json()

    clearance = client.get("/api/clearance", params={"discount_filter": "all"})
    assert clearance.status_code == 200
    assert clearance.json()["items"][0]["category"] == "Ethernet Cables"
