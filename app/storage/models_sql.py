"""SQLAlchemy ORM models for application storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base class for ORM models."""


class Store(Base):
    """Retail store representation."""

    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    zip: Mapped[str] = mapped_column(String, nullable=False)


class Item(Base):
    """Catalog item representation."""

    __tablename__ = "items"

    sku: Mapped[str] = mapped_column(String, primary_key=True)
    retailer: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)


class Observation(Base):
    """Observed price and availability for an item at a store."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retailer: Mapped[str] = mapped_column(String, nullable=False)
    store_id: Mapped[str] = mapped_column(String, nullable=False)
    store_name: Mapped[str | None] = mapped_column(String, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_was: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_off: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability: Mapped[str | None] = mapped_column(String, nullable=True)
    product_url: Mapped[str] = mapped_column(String, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    clearance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_observations_store_sku_ts", "store_id", "sku", "ts_utc"),
        Index("ix_observations_store_id", "store_id"),
    )


class Alert(Base):
    """Alert generated from observation changes."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    store_id: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    retailer: Mapped[str] = mapped_column(String, nullable=False)
    pct_off: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_was: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
