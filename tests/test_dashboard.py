from __future__ import annotations

from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.dashboard import _normalize_state, _state_from_zip, app, session_factory
from app.storage.models_sql import Observation, Store


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
        session.execute(delete(Store))
        session.commit()

        store_wa = Store(id="store-wa", name="Seattle Lowe's", city="Seattle", state="WA", zip="98101")
        store_or = Store(id="store-or", name="Salem Lowe's", city="Salem", state="OR", zip="97301")
        session.add_all([store_wa, store_or])
        session.flush()

        session.add_all(
            [
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
        )
        session.commit()

    client = TestClient(app)
    response = client.get("/api/clearance", params={"scope": "all", "state": "WA"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["count"] == 1
    assert payload["state"] == "WA"
    assert payload["items"][0]["store_id"] == "store-wa"
