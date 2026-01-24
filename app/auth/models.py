"""SQLAlchemy models for user authentication and subscriptions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.models_sql import Base


class SubscriptionPlan(PyEnum):
    """Available subscription tiers."""
    FREE = "free"
    BASIC = "basic"  # Legacy - keeping for backwards compatibility
    PRO = "pro"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"  # Legacy alias for PREMIUM


class SubscriptionStatus(PyEnum):
    """Subscription lifecycle states."""
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    UNPAID = "unpaid"
    TRIALING = "trialing"
    INCOMPLETE = "incomplete"


class User(Base):
    """Registered user account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Username/handle
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    
    # Profile
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Stripe integration
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Password reset
    reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Email verification
    verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Relationship to subscription
    subscription: Mapped["Subscription | None"] = relationship("Subscription", back_populates="user", uselist=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class Subscription(Base):
    """User subscription record linked to Stripe."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Stripe IDs
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Plan details
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan), 
        default=SubscriptionPlan.FREE, 
        nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus),
        default=SubscriptionStatus.ACTIVE,
        nullable=False
    )
    
    # Billing period
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Trial info
    trial_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to user
    user: Mapped["User"] = relationship("User", back_populates="subscription")

    def is_active_subscription(self) -> bool:
        """Check if subscription grants access."""
        if self.plan == SubscriptionPlan.FREE:
            return True
        return self.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING)

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, user_id={self.user_id}, plan={self.plan.value})>"


class PaymentHistory(Base):
    """Record of payment events from Stripe webhooks."""

    __tablename__ = "payment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd", nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # succeeded, failed, pending
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PaymentHistory(id={self.id}, amount={self.amount}, status={self.status})>"
