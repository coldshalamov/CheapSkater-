"""SQLAlchemy models for admin features."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models_sql import Base


class ScraperHeartbeat(Base):
    """Tracks active scrapers and their health status."""

    __tablename__ = "scraper_heartbeats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    scraper_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Heartbeat tracking
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metrics
    deals_ingested_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deals_ingested_session: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Scraper info
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_scraper_heartbeats_last_heartbeat", "last_heartbeat"),
        Index("ix_scraper_heartbeats_active", "is_active"),
    )


class SystemMessage(Base):
    """Global system messages displayed at the top of the dashboard."""

    __tablename__ = "system_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Message content
    message: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="info", nullable=False)  # info, warning, error, success

    # Display control
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Higher = shown first

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_system_messages_active_priority", "is_active", "priority"),
    )


class UserActivity(Base):
    """Tracks user login activity and unique IP addresses."""

    __tablename__ = "user_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Activity type
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # login, logout, view_deal, etc.

    # Session info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max length
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamp
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Optional additional data
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob for additional context

    __table_args__ = (
        Index("ix_user_activity_user_occurred", "user_id", "occurred_at"),
        Index("ix_user_activity_type", "activity_type"),
        Index("ix_user_activity_ip", "ip_address"),
    )


class ActiveSession(Base):
    """Tracks currently active user sessions."""

    __tablename__ = "active_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Session identification
    session_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)

    # Session info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_active_sessions_user_active", "user_id", "last_activity"),
    )


class IngestionMetrics(Base):
    """Aggregated metrics for deal ingestion rate tracking."""

    __tablename__ = "ingestion_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Time window
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_size_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # 5-minute windows

    # Metrics
    deals_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_stores: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unique_skus: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Error tracking
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_ingestion_metrics_window", "window_start", "window_end"),
    )
