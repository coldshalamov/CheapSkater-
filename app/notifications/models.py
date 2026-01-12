"""SQLAlchemy models for deal notifications."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, ForeignKey, Enum, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.models_sql import Base


class NotificationType(PyEnum):
    """Types of notification triggers."""
    CATEGORY = "category"
    KEYWORD = "keyword"


class NotificationFrequency(PyEnum):
    """How often to send digest emails."""
    INSTANT = "instant"  # Send immediately when match found
    DAILY = "daily"      # Daily digest
    WEEKLY = "weekly"    # Weekly digest


class DealAlert(Base):
    """User-configured deal alert (paid notification)."""

    __tablename__ = "deal_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Alert configuration
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    alert_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), 
        nullable=False
    )
    
    # For category alerts
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # For keyword alerts
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)  # Comma-separated
    
    # Filters
    min_discount: Mapped[float | None] = mapped_column(Float, nullable=True)  # e.g., 0.5 for 50%
    max_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    states: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "WA", "OR", or "WA,OR"
    
    # Notification settings
    frequency: Mapped[NotificationFrequency] = mapped_column(
        Enum(NotificationFrequency),
        default=NotificationFrequency.INSTANT,
        nullable=False
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Billing
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monthly_price: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    user: Mapped["User"] = relationship("User", backref="deal_alerts")
    
    def matches_deal(self, deal: dict) -> bool:
        """Check if a deal matches this alert's criteria."""
        # Check discount threshold
        if self.min_discount is not None:
            deal_pct = deal.get("pct_off", 0) or 0
            if deal_pct < 1:
                deal_pct = deal_pct * 100  # Normalize to percentage
            if deal_pct < (self.min_discount * 100):
                return False
        
        # Check max price
        if self.max_price is not None:
            deal_price = deal.get("price", 0) or 0
            if deal_price > self.max_price:
                return False
        
        # Check state
        if self.states:
            deal_state = deal.get("store_state", "").upper()
            allowed_states = [s.strip().upper() for s in self.states.split(",")]
            if deal_state and deal_state not in allowed_states:
                return False
        
        # Check alert type specific criteria
        if self.alert_type == NotificationType.CATEGORY:
            deal_category = (deal.get("category") or "").lower()
            if self.category and self.category.lower() not in deal_category:
                return False
        
        elif self.alert_type == NotificationType.KEYWORD:
            if self.keywords:
                keywords_list = [k.strip().lower() for k in self.keywords.split(",")]
                searchable = f"{deal.get('title', '')} {deal.get('category', '')}".lower()
                if not any(kw in searchable for kw in keywords_list):
                    return False
        
        return True

    def __repr__(self) -> str:
        return f"<DealAlert(id={self.id}, user_id={self.user_id}, type={self.alert_type.value})>"


class NotificationLog(Base):
    """Log of sent notifications for deduplication and history."""

    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, ForeignKey("deal_alerts.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # What was sent
    deal_sku: Mapped[str] = mapped_column(String(50), nullable=False)
    deal_store_id: Mapped[str] = mapped_column(String(20), nullable=False)
    deal_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot
    
    # Delivery status
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NotificationLog(id={self.id}, alert_id={self.alert_id}, sku={self.deal_sku})>"


# Import User for relationship (avoid circular import)
from app.auth.models import User
