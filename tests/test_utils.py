from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.extractors import schemas
from app.extractors.dom_utils import price_to_float


def test_parse_price_various_inputs() -> None:
    assert schemas.parse_price("$1,234.56") == 1234.56
    assert schemas.parse_price("19.99") == 19.99
    assert schemas.parse_price("no price") is None


def test_compute_pct_off() -> None:
    assert schemas.compute_pct_off(price=75, was=100) == 0.25
    for price, was in [
        (None, 100),
        (75, None),
        (0, 100),
        (-5, 100),
        (75, 0),
        (75, -10),
        (120, 100),
    ]:
        assert schemas.compute_pct_off(price=price, was=was) is None


def test_price_to_float_parsing() -> None:
    assert price_to_float("$2,499.00") == 2499.0
    assert price_to_float(" - 99.50 ") == -99.5
    assert price_to_float(".") is None
