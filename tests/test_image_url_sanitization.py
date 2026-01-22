from app.dashboard import _serialize_listing


def test_serialize_listing_filters_badge_image_urls() -> None:
    payload = _serialize_listing(
        {
            "retailer": "lowes",
            "store_id": "0001",
            "store_name": "Test Store, FL (#0001)",
            "sku": "5016210305",
            "title": "Test Item",
            "category": "Test Category",
            "price": 9.11,
            "price_was": 16.37,
            "pct_off": 44.4,
            "product_url": "https://www.lowes.com/pd/Test/5016210305",
            "image_url": "https://www.lowescdn.com/images/badges/clearance.svg",
        }
    )
    assert payload["image_url"] is None

