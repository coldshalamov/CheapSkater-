from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.dashboard import SESSION_SECRET, app, session_factory
from app.middleware.simple_session import SimpleSessionMiddleware
from app.storage import repo
from app.storage.models_sql import Store, StorePriceHistory
from app.auth.models import Subscription, SubscriptionPlan, SubscriptionStatus, User


def _make_session_cookie(payload: dict[str, object]) -> str:
    middleware = SimpleSessionMiddleware(app, secret_key=SESSION_SECRET, max_age=None)
    return middleware._encode(payload)  # type: ignore[attr-defined]


def test_free_user_cannot_see_recently_seen_deal() -> None:
    with session_factory() as session:
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.commit()

        store = Store(
            id="s1",
            name="Test Store",
            city="X",
            state="WA",
            zip="98101",
            region="WA_OR",
        )
        session.add(store)
        session.commit()

        started = datetime.now(timezone.utc) - timedelta(days=10)
        recently_seen = datetime.now(timezone.utc) - timedelta(hours=1)

        # First observation creates the history row (started_at=updated_at=started)
        repo.update_price_history(
            session,
            retailer="lowes",
            store_id=store.id,
            sku="sku1",
            title="Test Item",
            category="Tools",
            ts_utc=started,
            price=10.0,
            price_was=20.0,
            pct_off=0.5,
            availability="In stock",
            product_url="https://example.com/sku1",
            image_url=None,
            clearance=True,
            region="WA_OR",
        )
        session.commit()

        # Subsequent observation updates `updated_at` but keeps `started_at` stable.
        repo.update_price_history(
            session,
            retailer="lowes",
            store_id=store.id,
            sku="sku1",
            title="Test Item",
            category="Tools",
            ts_utc=recently_seen,
            price=10.0,
            price_was=20.0,
            pct_off=0.5,
            availability="In stock",
            product_url="https://example.com/sku1",
            image_url=None,
            clearance=True,
            region="WA_OR",
        )
        session.commit()

        # Sanity check: listing is old (started) but has been seen recently.
        listing = repo.get_clearance_items(session, state="WA", region="WA_OR", limit=1)[0]
        price_started_at = listing["price_started_at"]
        updated_at = listing["updated_at"]
        assert isinstance(price_started_at, datetime)
        assert isinstance(updated_at, datetime)
        if price_started_at.tzinfo is None:
            price_started_at = price_started_at.replace(tzinfo=timezone.utc)
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)

        assert price_started_at <= started + timedelta(seconds=1)
        assert updated_at >= recently_seen - timedelta(seconds=1)

        free_view = repo.get_older_clearance_items(
            session, state="WA", region="WA_OR", min_days_old=3
        )
        assert free_view == []


def test_pro_user_can_see_recently_seen_deal_via_api() -> None:
    with session_factory() as session:
        session.execute(delete(StorePriceHistory))
        session.execute(delete(Store))
        session.execute(delete(Subscription))
        session.execute(delete(User))
        session.commit()

        store = Store(
            id="s1",
            name="Test Store",
            city="X",
            state="WA",
            zip="98101",
            region="WA_OR",
        )
        session.add(store)
        session.commit()

        started = datetime.now(timezone.utc) - timedelta(days=10)
        recently_seen = datetime.now(timezone.utc) - timedelta(hours=1)

        repo.update_price_history(
            session,
            retailer="lowes",
            store_id=store.id,
            sku="sku1",
            title="Test Item",
            category="Tools",
            ts_utc=started,
            price=10.0,
            price_was=20.0,
            pct_off=0.5,
            availability="In stock",
            product_url="https://example.com/sku1",
            image_url=None,
            clearance=True,
            region="WA_OR",
        )
        session.commit()

        repo.update_price_history(
            session,
            retailer="lowes",
            store_id=store.id,
            sku="sku1",
            title="Test Item",
            category="Tools",
            ts_utc=recently_seen,
            price=10.0,
            price_was=20.0,
            pct_off=0.5,
            availability="In stock",
            product_url="https://example.com/sku1",
            image_url=None,
            clearance=True,
            region="WA_OR",
        )
        session.commit()

        user = User(
            email="pro@example.com",
            password_hash="x",
            display_name="Pro User",
            is_active=True,
            is_verified=True,
            is_admin=False,
        )
        session.add(user)
        session.flush()

        subscription = Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.PRO,
            status=SubscriptionStatus.ACTIVE,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add(subscription)
        session.commit()

        client = TestClient(app)
        client.cookies.set("session", _make_session_cookie({"user_id": user.id}))

        response = client.get("/api/clearance", params={"discount_filter": "all"})
        assert response.status_code == 200
        assert response.json()["count"] >= 1
