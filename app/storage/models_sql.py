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

    store_id: Mapped[str] = mapped_column(String, primary_key=True)
    retailer: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    city: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
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
    store_id: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_was: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability: Mapped[str | None] = mapped_column(String, nullable=True)
    clearance: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        Index("ix_observations_store_id", "store_id"),
        Index("ix_observations_sku", "sku"),
        Index("ix_observations_ts_utc", "ts_utc"),
    )


class Alert(Base):
    """Alert generated from observation changes."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    store_id: Mapped[str] = mapped_column(String, nullable=False)
    sku: Mapped[str] = mapped_column(String, nullable=False)
    rule: Mapped[str] = mapped_column(String, nullable=False)
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
