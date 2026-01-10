from __future__ import annotations

import pytest

from app.normalizers import extract_category_name


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

