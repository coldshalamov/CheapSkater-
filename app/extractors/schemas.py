"""Data validation schemas for extracted records."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_PRICE_PATTERN = re.compile(r"(?P<number>-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d*\.\d+)")


def parse_price(text: str | None) -> float | None:
    """Parse a price-like string into a float.

    The function extracts the first decimal number found in the text, allowing for
    optional currency symbols, commas, and whitespace. Returns ``None`` when no
    number is present.
    """

    if not text:
        return None

    match = _PRICE_PATTERN.search(text)
    if not match:
        return None

    number = match.group("number").replace(",", "")
    try:
        return float(number)
    except (TypeError, ValueError):
        return None


def compute_pct_off(price: float | None, was: float | None) -> float | None:
    """Compute the percentage off between ``price`` and ``was`` values."""

    if price is None or was is None:
        return None

    if price <= 0 or was <= 0:
        return None

    if price >= was:
        return None

    return (was - price) / was


def _coerce_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime):  # pragma: no cover - defensive path
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value


class ProductIn(BaseModel):
    """Schema describing a product payload from extractors."""

    model_config = ConfigDict(extra="ignore")

    sku: str | None = None
    title: str
    category: str
    product_url: str
    image_url: str | None = None
    clearance: bool | None = None


class ObservationIn(BaseModel):
    """Schema describing a store observation payload from extractors."""

    model_config = ConfigDict(extra="ignore")

    store_id: str | None = None
    store_name: str | None = None
    zip: str
    price: float | None = Field(default=None)
    was_price: float | None = Field(default=None)
    availability: str | None = None
    observed_at: datetime

    @field_validator("observed_at", mode="before")
    @classmethod
    def _ensure_utc(cls, value: Any) -> datetime:
        return _coerce_datetime(value, "observed_at")


class FlattenedRow(BaseModel):
    """Combined data row suitable for CSV export."""

    model_config = ConfigDict(from_attributes=True)

    ts_utc: datetime
    retailer: str
    store_id: str | None = None
    store_name: str | None = None
    zip: str | None = None
    sku: str
    title: str
    category: str
    price: float | None = None
    price_was: float | None = None
    pct_off: float | None = None
    clearance: bool | None = None
    availability: str | None = None
    product_url: str
    image_url: str | None = None

    @field_validator("ts_utc", mode="before")
    @classmethod
    def _ensure_flat_ts_utc(cls, value: Any) -> datetime:
        return _coerce_datetime(value, "ts_utc")
