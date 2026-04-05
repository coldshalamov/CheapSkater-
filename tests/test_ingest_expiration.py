from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from sqlalchemy import delete

import app.ingest as ingest_module
from app.dashboard import app, session_factory
from app.storage import repo
from app.storage.models_sql import Observation, Store, StorePriceHistory
from app.timezone_utils import format_regional_full_timestamp


def _clear_tables() -> None:
    with session_factory() as session:
        session.execute(delete(Observation))
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()


def _seed_listing(
    *,
    store_id: str,
    store_name: str,
    sku: str,
    product_url: str,
    updated_at: datetime,
    category_url: str | None = None,
) -> None:
    with session_factory() as session:
        store = Store(
            id=store_id,
            name=store_name,
            city="Seattle",
            state="WA",
            zip="98101",
            region="WA_OR",
        )
        session.merge(store)
        session.add(
            Observation(
                ts_utc=updated_at,
                retailer="lowes",
                store_id=store_id,
                store_name=store_name,
                zip="98101",
                region="WA_OR",
                sku=sku,
                title=f"Item {sku}",
                category="Tools",
                category_url=category_url,
                price=25.0,
                price_was=50.0,
                pct_off=50.0,
                availability="In stock",
                product_url=product_url,
                image_url=None,
                clearance=True,
            )
        )
        repo.update_price_history(
            session,
            retailer="lowes",
            store_id=store_id,
            sku=sku,
            title=f"Item {sku}",
            category="Tools",
            ts_utc=updated_at,
            price=25.0,
            price_was=50.0,
            pct_off=50.0,
            availability="In stock",
            product_url=product_url,
            image_url=None,
            clearance=True,
            region="WA_OR",
            category_url=category_url,
        )
        session.commit()


def test_expire_endpoint_requires_api_key_and_removes_matching_store_listing(
    monkeypatch,
) -> None:
    _clear_tables()
    now = datetime.now(timezone.utc) - timedelta(days=4)
    shared_sku = "5001234567"
    target_url = f"https://www.lowes.com/pd/Test-Target/{shared_sku}"
    _seed_listing(
        store_id="0001",
        store_name="Seattle Lowe's",
        sku=shared_sku,
        product_url=target_url,
        updated_at=now,
    )
    _seed_listing(
        store_id="0002",
        store_name="Tacoma Lowe's",
        sku=shared_sku,
        product_url=target_url,
        updated_at=now,
    )

    monkeypatch.setattr(ingest_module, "INGEST_API_KEY", "secret-key")
    client = TestClient(app)

    unauthorized = client.post(
        "/api/ingest/expire",
        json={"expired_deals": [{"store_id": "0001", "product_url": target_url}]},
    )
    assert unauthorized.status_code == 401

    response = client.post(
        "/api/ingest/expire",
        headers={"X-API-Key": "secret-key"},
        json={"expired_deals": [{"store_id": "0001", "product_url": target_url}]},
    )
    assert response.status_code == 200
    assert response.json()["removed"] == 1

    with session_factory() as session:
        remaining_history = session.query(StorePriceHistory).all()
        remaining_observations = session.query(Observation).all()

    assert {(row.store_id, row.product_url) for row in remaining_history} == {
        ("0002", target_url)
    }
    assert {(row.store_id, row.product_url) for row in remaining_observations} == {
        ("0002", target_url)
    }


def test_clearance_queries_hide_rows_older_than_30_days(monkeypatch) -> None:
    _clear_tables()
    fresh_seen = datetime.now(timezone.utc) - timedelta(days=5)
    stale_seen = datetime.now(timezone.utc) - timedelta(days=31)
    _seed_listing(
        store_id="0003",
        store_name="Bellevue Lowe's",
        sku="5000000001",
        product_url="https://www.lowes.com/pd/Fresh-Deal/5000000001",
        updated_at=fresh_seen,
    )
    _seed_listing(
        store_id="0004",
        store_name="Everett Lowe's",
        sku="5000000002",
        product_url="https://www.lowes.com/pd/Stale-Deal/5000000002",
        updated_at=stale_seen,
    )

    monkeypatch.setenv("CHEAPSKATER_MAX_LISTING_AGE_DAYS", "30")

    with session_factory() as session:
        listings = repo.get_clearance_items(session, state="WA", region="WA_OR")

    assert {(row["store_id"], row["sku"]) for row in listings} == {("0003", "5000000001")}


def test_expire_endpoint_preserves_listing_when_category_scope_does_not_match(
    monkeypatch,
) -> None:
    _clear_tables()
    seen_at = datetime.now(timezone.utc) - timedelta(days=2)
    target_url = "https://www.lowes.com/pd/Scoped-Deal/5003333333"
    _seed_listing(
        store_id="0201",
        store_name="Seattle Lowe's",
        sku="5003333333",
        product_url=target_url,
        updated_at=seen_at,
        category_url="https://www.lowes.com/pl/Still-Live/111",
    )

    monkeypatch.setattr(ingest_module, "INGEST_API_KEY", "secret-key")
    client = TestClient(app)
    response = client.post(
        "/api/ingest/expire",
        headers={"X-API-Key": "secret-key"},
        json={
            "category_url": "https://www.lowes.com/pl/Went-Stale/222",
            "expired_deals": [{"store_id": "0201", "product_url": target_url}],
        },
    )

    assert response.status_code == 200
    assert response.json()["removed"] == 0

    with session_factory() as session:
        remaining_history = session.query(StorePriceHistory).all()
        remaining_observations = session.query(Observation).all()

    assert [(row.store_id, row.product_url) for row in remaining_history] == [
        ("0201", target_url)
    ]
    assert [(row.store_id, row.product_url) for row in remaining_observations] == [
        ("0201", target_url)
    ]


def test_dashboard_renders_per_store_observed_timestamps() -> None:
    _clear_tables()
    first_seen = datetime.now(timezone.utc) - timedelta(days=6, hours=2, minutes=15)
    second_seen = datetime.now(timezone.utc) - timedelta(days=4, hours=5, minutes=40)
    shared_sku = "5002222222"
    shared_url = "https://www.lowes.com/pd/Multi-Store-Deal/5002222222"
    _seed_listing(
        store_id="0101",
        store_name="Seattle Lowe's",
        sku=shared_sku,
        product_url=shared_url,
        updated_at=first_seen,
    )
    _seed_listing(
        store_id="0102",
        store_name="Tacoma Lowe's",
        sku=shared_sku,
        product_url=shared_url,
        updated_at=second_seen,
    )

    client = TestClient(app)
    response = client.get("/pnw", params={"discount_filter": "all"})

    assert response.status_code == 200
    assert "Most recently seen at any store" in response.text
    assert format_regional_full_timestamp(first_seen, "WA_OR") in response.text
    assert format_regional_full_timestamp(second_seen, "WA_OR") in response.text
