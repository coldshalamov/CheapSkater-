import pytest

pytest.importorskip("uvicorn")

from app.main import (
    _derive_city_from_store_name,
    _infer_state_from_zip,
    _is_building_material_category,
)


def test_derive_city_handles_common_patterns() -> None:
    assert _derive_city_from_store_name("Lowe's of Portland, OR") == "Portland"
    assert _derive_city_from_store_name("Lowe's Home Improvement of Yakima WA") == "Yakima"
    assert _derive_city_from_store_name("Lowe's of Bend-OR #1234") == "Bend"
    assert _derive_city_from_store_name(None) == "Unknown"


def test_infer_state_from_zip_ranges() -> None:
    assert _infer_state_from_zip("97223") == "OR"
    assert _infer_state_from_zip("98101") == "WA"
    assert _infer_state_from_zip("12345") == "UNKNOWN"


def test_is_building_material_category_keywords() -> None:
    assert _is_building_material_category("Roofing & Gutters") is True
    assert _is_building_material_category("Premium Drywall Sheets") is True
    assert _is_building_material_category("Kitchen Appliances") is False
