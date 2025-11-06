from datetime import datetime, timezone

from app.storage import repo
from app.storage.models_sql import Observation


def _make_obs(
    *,
    clearance: bool | None,
    price: float | None = None,
    price_was: float | None = None,
) -> Observation:
    return Observation(
        ts_utc=datetime.now(timezone.utc),
        store_id="store-1",
        sku="sku-1",
        price=price,
        price_was=price_was,
        availability=None,
        clearance=clearance,
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


def test_fallback_price_logic_when_flag_missing() -> None:
    last_obs = _make_obs(clearance=None, price=100, price_was=None)
    new_obs = _make_obs(clearance=None, price=70, price_was=110)
    assert repo.should_alert_new_clearance(last_obs, new_obs) is True
