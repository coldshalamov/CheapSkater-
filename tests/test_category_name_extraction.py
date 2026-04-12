from __future__ import annotations

import pytest

from app.normalizers import (
    extract_category_name,
    is_suspicious_category_name,
    normalize_display_category_name,
    resolve_category_name,
)


@pytest.mark.parametrize(
    ("category_url", "expected"),
    [
        (
            "https://www.lowes.com/pl/air-conditioners-fans/portable-fans/4294856700",
            "Portable Fans",
        ),
        (
            "https://www.lowes.com/pl/appliance-parts-accessories/dishwasher-parts/554129471",
            "Dishwasher Parts",
        ),
        (
            "https://www.lowes.com/pl/fencing-gates/rolled-fencing/barbed-wire/4294402516-4294401734",
            "Barbed Wire",
        ),
        (
            "https://www.lowes.com/pl/air-filters-accessories/air-filters/4294761659-4294760493-4294760441",
            "Air Filters",
        ),
        ("https://www.lowes.com/pl/4294856700", "Uncategorized"),
        ("", "Uncategorized"),
        (None, "Uncategorized"),
        ("not a url", "Uncategorized"),
        ("https://www.lowes.com/pl/bathtubs-whirlpool-tubs/bathtubs/4294737274/", "Bathtubs"),
        ("https://www.lowes.com/pl/air-conditioners-fans/portable-fans/4294856700?foo=bar", "Portable Fans"),
    ],
)
def test_extract_category_name(category_url: str | None, expected: str) -> None:
    assert extract_category_name(category_url) == expected


@pytest.mark.parametrize(
    ("raw_category", "expected"),
    [
        ("Portable Fans", False),
        ("0 1 Foot Long", True),
        ("0 276 In", True),
        ("100 Made In Usa 21 Ft Sectional Flagpole With Swivels And", True),
    ],
)
def test_is_suspicious_category_name(raw_category: str, expected: bool) -> None:
    assert is_suspicious_category_name(raw_category) is expected


def test_resolve_category_name_prefers_url_when_scraped_label_is_spec_text() -> None:
    assert (
        resolve_category_name(
            "0 1 Foot Long",
            "https://www.lowes.com/pl/air-conditioners-fans/portable-fans/4294856700",
        )
        == "Portable Fans"
    )


def test_resolve_category_name_preserves_good_new_worker_category() -> None:
    assert (
        resolve_category_name(
            "Ethernet Cables",
            "https://www.lowes.com/pl/electrical-cable-wire/networking-cable/4294418126",
        )
        == "Ethernet Cables"
    )


def test_resolve_category_name_falls_back_to_clearance_when_old_worker_data_is_ambiguous() -> None:
    assert resolve_category_name("1080P", None) == "Clearance"


def test_normalize_display_category_name_hides_spec_fragments() -> None:
    assert normalize_display_category_name("0 276 In") is None
    assert normalize_display_category_name("Portable Fans") == "Portable Fans"

