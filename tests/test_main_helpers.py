import pytest

pytest.importorskip("uvicorn")

from app.main import (
    _configure_material_keywords,
    _derive_city_from_store_name,
    _infer_state_from_zip,
    _is_building_material_category,
    parse_args,
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
    _configure_material_keywords({})
    assert _is_building_material_category("Roofing & Gutters") is True
    assert _is_building_material_category("Premium Drywall Sheets") is True
    assert _is_building_material_category("Kitchen Appliances") is False


def test_parse_args_probe_flag() -> None:
    args = parse_args(["--probe", "--zip", "98101"])
    assert args.probe is True
    assert args.zips == ["98101"]


def test_material_keywords_from_config() -> None:
    try:
        _configure_material_keywords({"material_keywords": ["widgets"]})
        assert _is_building_material_category("Widgets and gadgets") is True
        assert _is_building_material_category("Roofing & Gutters") is False
    finally:
        _configure_material_keywords({})
    assert _is_building_material_category("Roofing & Gutters") is True
    assert _is_building_material_category("Kitchen Appliances") is False
