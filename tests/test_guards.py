import asyncio
from datetime import datetime, timezone

import app.selectors as selectors
import pytest

from app.errors import SelectorChangedError
from app.main import _ensure_category_urls_configured
from app.retailers.lowes import scrape_category
from app.storage import repo
from app.extractors import schemas


def test_config_category_urls_required():
    config = {
        "retailers": {
            "lowes": {
                "categories": [
                    {"name": "Flooring", "url": "PASTE_REAL_CATEGORY_URL_AFTER_SETTING_STORE"}
                ]
            }
        }
    }

    with pytest.raises(RuntimeError) as exc:
        _ensure_category_urls_configured(config)

    assert "CONFIG_CATEGORY_URLS_REQUIRED" in str(exc.value)


def test_selectors_not_configured(monkeypatch):
    monkeypatch.setattr(selectors, "CARD", "TODO_CARD")
    monkeypatch.setattr(selectors, "TITLE", "div.product-title")
    monkeypatch.setattr(selectors, "PRICE", "span.price")
    monkeypatch.setattr(selectors, "LINK", "a.product-link")
    monkeypatch.setattr(selectors, "STORE_BADGE", "div.store-badge")

    async def _invoke() -> None:
        await scrape_category(object(), "https://example.com", "Flooring", "97204")

    with pytest.raises(SelectorChangedError) as exc:
        asyncio.run(_invoke())

    assert "SELECTORS_NOT_CONFIGURED" in str(exc.value)


def test_write_csv_creates_parent_dir(tmp_path):
    csv_path = tmp_path / "exports" / "items.csv"

    row = schemas.FlattenedRow(
        ts_utc=datetime.now(timezone.utc),
        retailer="lowes",
        store_id="123",
        store_name="Test Store",
        zip="97204",
        sku="123456",
        title="Test Item",
        category="Flooring",
        price=10.0,
        price_was=20.0,
        pct_off=0.5,
        clearance=None,
        availability="In Stock",
        product_url="https://example.com/item",
        image_url=None,
    )

    repo.write_csv([row], str(csv_path))

    assert csv_path.exists()
