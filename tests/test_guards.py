from datetime import datetime, timezone

from app.storage import repo


def test_write_csv_creates_directory_and_header(tmp_path):
    csv_path = tmp_path / "exports" / "items.csv"
    rows = [
        {
            "ts_utc": datetime(2024, 8, 1, tzinfo=timezone.utc),
            "retailer": "lowes",
            "store_id": "123",
            "store_name": "Test Store",
            "zip": "97204",
            "sku": "123456",
            "title": "Test Item",
            "category": "Drywall",
            "price": 10.0,
            "price_was": 20.0,
            "pct_off": 0.5,
            "availability": "In Stock",
            "product_url": "https://example.com/item",
            "image_url": None,
        }
    ]

    repo.write_csv(rows, str(csv_path))

    contents = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert contents[0].startswith("ts_utc,retailer,store_id")
    assert "123456" in contents[1]
