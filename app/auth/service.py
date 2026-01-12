"""Authentication service - handles user registration, login, and password management."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus

if TYPE_CHECKING:
    pass


class AuthError(Exception):
    """Base authentication error."""
    pass


class InvalidCredentials(AuthError):
    """Invalid email or password."""
    pass


class UserExists(AuthError):
    """User with this email already exists."""
    pass


class UserNotFound(AuthError):
    """User not found."""
    pass


class TokenExpired(AuthError):
    """Password reset token has expired."""
    pass


class AuthService:
    """Service layer for authentication operations."""

    # Password hashing parameters
    HASH_ITERATIONS = 100_000
    HASH_ALGORITHM = "sha256"
    SALT_LENGTH = 32
    
    # Token settings
    RESET_TOKEN_EXPIRY_HOURS = 24
    SESSION_COOKIE_NAME = "gloorbot_session"

    def __init__(self, session: Session):
        self.session = session

    # ──────────────────────────────────────────────────────────────────────────
    # Password Hashing
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using PBKDF2-HMAC-SHA256."""
        salt = secrets.token_bytes(AuthService.SALT_LENGTH)
        key = hashlib.pbkdf2_hmac(
            AuthService.HASH_ALGORITHM,
            password.encode("utf-8"),
            salt,
            AuthService.HASH_ITERATIONS,
        )
        # Store as salt:key in hex
        return f"{salt.hex()}:{key.hex()}"

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            salt_hex, key_hex = password_hash.split(":")
            salt = bytes.fromhex(salt_hex)
            stored_key = bytes.fromhex(key_hex)
        except (ValueError, AttributeError):
            return False

        computed_key = hashlib.pbkdf2_hmac(
            AuthService.HASH_ALGORITHM,
            password.encode("utf-8"),
            salt,
            AuthService.HASH_ITERATIONS,
        )
        return hmac.compare_digest(stored_key, computed_key)

    # ──────────────────────────────────────────────────────────────────────────
    # User Management
    # ──────────────────────────────────────────────────────────────────────────

    def get_user_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        email_lower = email.lower().strip()
        stmt = select(User).where(User.email == email_lower)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_user_by_id(self, user_id: int) -> User | None:
        """Fetch a user by ID."""
        stmt = select(User).where(User.id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_user_by_stripe_customer(self, stripe_customer_id: str) -> User | None:
        """Fetch a user by Stripe customer ID."""
        stmt = select(User).where(User.stripe_customer_id == stripe_customer_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def register_user(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        """Register a new user account."""
        email_lower = email.lower().strip()

        # Check if user exists
        existing = self.get_user_by_email(email_lower)
        if existing:
            raise UserExists(f"User with email {email_lower} already exists")

        # Create user
        user = User(
            email=email_lower,
            password_hash=self.hash_password(password),
            display_name=display_name,
            is_active=True,
            is_verified=False,  # Require email verification in production
            verification_token=secrets.token_urlsafe(32),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(user)
        self.session.flush()  # Get the user ID

        # Create free subscription
        subscription = Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(subscription)
        self.session.commit()

        return user

    def authenticate(self, email: str, password: str) -> User:
        """Authenticate a user with email and password."""
        user = self.get_user_by_email(email)
        if not user:
            raise InvalidCredentials("Invalid email or password")

        if not self.verify_password(password, user.password_hash):
            raise InvalidCredentials("Invalid email or password")

        if not user.is_active:
            raise InvalidCredentials("Account is disabled")

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        self.session.commit()

        return user

    def update_password(self, user: User, new_password: str) -> None:
        """Change a user's password."""
        user.password_hash = self.hash_password(new_password)
        user.updated_at = datetime.now(timezone.utc)
        user.reset_token = None
        user.reset_token_expires = None
        self.session.commit()

    # ──────────────────────────────────────────────────────────────────────────
    # Password Reset
    # ──────────────────────────────────────────────────────────────────────────

    def create_reset_token(self, email: str) -> str | None:
        """Generate a password reset token. Returns None if user not found."""
        user = self.get_user_by_email(email)
        if not user:
            return None

        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(
            hours=self.RESET_TOKEN_EXPIRY_HOURS
        )
        self.session.commit()
        return token

    def verify_reset_token(self, token: str) -> User:
        """Verify a password reset token and return the user."""
        stmt = select(User).where(User.reset_token == token)
        user = self.session.execute(stmt).scalar_one_or_none()

        if not user:
            raise UserNotFound("Invalid reset token")

        if not user.reset_token_expires:
            raise TokenExpired("Reset token has expired")

        if datetime.now(timezone.utc) > user.reset_token_expires:
            raise TokenExpired("Reset token has expired")

        return user

    def reset_password(self, token: str, new_password: str) -> User:
        """Reset password using a valid token."""
        user = self.verify_reset_token(token)
        self.update_password(user, new_password)
        return user

    # ──────────────────────────────────────────────────────────────────────────
    # Email Verification
    # ──────────────────────────────────────────────────────────────────────────

    def verify_email(self, token: str) -> User | None:
        """Verify a user's email address."""
        stmt = select(User).where(User.verification_token == token)
        user = self.session.execute(stmt).scalar_one_or_none()

        if user:
            user.is_verified = True
            user.verification_token = None
            user.updated_at = datetime.now(timezone.utc)
            self.session.commit()

        return user

    # ──────────────────────────────────────────────────────────────────────────
    # Subscription Management
    # ──────────────────────────────────────────────────────────────────────────

    def get_subscription(self, user_id: int) -> Subscription | None:
        """Get a user's subscription."""
        stmt = select(Subscription).where(Subscription.user_id == user_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def update_subscription(
        self,
        user_id: int,
        *,
        stripe_subscription_id: str | None = None,
        stripe_price_id: str | None = None,
        plan: SubscriptionPlan | None = None,
        status: SubscriptionStatus | None = None,
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool | None = None,
    ) -> Subscription:
        """Update or create a subscription record."""
        subscription = self.get_subscription(user_id)

        if not subscription:
            subscription = Subscription(
                user_id=user_id,
                plan=plan or SubscriptionPlan.FREE,
                status=status or SubscriptionStatus.ACTIVE,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.session.add(subscription)

        if stripe_subscription_id is not None:
            subscription.stripe_subscription_id = stripe_subscription_id
        if stripe_price_id is not None:
            subscription.stripe_price_id = stripe_price_id
        if plan is not None:
            subscription.plan = plan
        if status is not None:
            subscription.status = status
        if current_period_start is not None:
            subscription.current_period_start = current_period_start
        if current_period_end is not None:
            subscription.current_period_end = current_period_end
        if cancel_at_period_end is not None:
            subscription.cancel_at_period_end = cancel_at_period_end

        subscription.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        return subscription

    def has_active_subscription(self, user_id: int) -> bool:
        """Check if user has an active paid subscription."""
        subscription = self.get_subscription(user_id)
        if not subscription:
            return False
        return subscription.is_active_subscription()
