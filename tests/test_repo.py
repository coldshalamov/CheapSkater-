from datetime import datetime, timezone

from app.storage import repo
from app.storage.models_sql import Observation


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
        category="Category",
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
