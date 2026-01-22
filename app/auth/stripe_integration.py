"""Stripe integration for subscription payments."""

from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# Stripe SDK - will be imported dynamically if available
stripe = None

# Configuration from environment
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC", "")  # Stripe Price ID for basic plan (legacy)
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")  # Stripe Price ID for pro plan
STRIPE_PRICE_PREMIUM = os.getenv("STRIPE_PRICE_PREMIUM", "")  # Stripe Price ID for premium plan ($200/mo)
STRIPE_PRICE_ENTERPRISE = os.getenv("STRIPE_PRICE_ENTERPRISE", "")  # Legacy alias for premium

# Plan configuration
PLAN_CONFIG = {
    "pro": {
        "name": "Pro Access",
        "price_monthly": 50.0,
        "stripe_price_id": STRIPE_PRICE_PRO,
        "features": [
            "Real-time deal access",
            "Advanced filters & search",
            "Unlimited saved deals",
            "Export to Excel",
            "Don't see your store? Email us!",
        ],
        "cta_text": "Get Pro",
        "description": "Perfect for serious deal hunters",
    },
    "premium": {
        "name": "Premium",
        "price_monthly": 200.0,
        "stripe_price_id": STRIPE_PRICE_PREMIUM or STRIPE_PRICE_ENTERPRISE,
        "features": [
            "Everything in Pro",
            "Unlimited deal alerts included",
            "Priority email support (24hr response)",
            "Request new stores anytime",
            "Early access to new features",
        ],
        "cta_text": "Go Premium",
        "description": "For power users who want it all",
        "support_email": "support@gloorbot.com",
    },
    # Legacy plans kept for backwards compatibility
    "basic": {
        "name": "Basic",
        "price_monthly": 25.0,
        "stripe_price_id": STRIPE_PRICE_BASIC,
        "features": [
            "Browse all deals",
            "Basic filters",
            "5 saved deals",
        ],
        "legacy": True,
    },
    "enterprise": {
        "name": "Enterprise",
        "price_monthly": 200.0,
        "stripe_price_id": STRIPE_PRICE_ENTERPRISE,
        "features": [
            "Everything in Pro",
            "Unlimited deal alerts included",
            "Priority support",
            "API access",
        ],
        "legacy": True,  # Use 'premium' instead
    },
}

# Deal alert pricing
DEAL_ALERT_MONTHLY_PRICE = 10.0


def _init_stripe() -> bool:
    """Initialize Stripe SDK."""
    global stripe
    if stripe is not None:
        return True
    
    if not STRIPE_SECRET_KEY:
        return False
    
    try:
        import stripe as stripe_module
        stripe = stripe_module
        stripe.api_key = STRIPE_SECRET_KEY
        return True
    except ImportError:
        return False


class StripeError(Exception):
    """Stripe operation error."""
    pass


class CreateCheckoutSessionRequest(BaseModel):
    """Request to create a Stripe checkout session."""
    price_id: str = Field(..., description="Stripe Price ID")
    success_url: str = Field(..., description="Redirect URL after successful payment")
    cancel_url: str = Field(..., description="Redirect URL if payment is canceled")


class CreateCheckoutSessionResponse(BaseModel):
    """Response from creating a checkout session."""
    session_id: str
    checkout_url: str


class StripeService:
    """Service for Stripe payment operations."""

    def __init__(self):
        if not _init_stripe():
            raise StripeError("Stripe is not configured. Set STRIPE_SECRET_KEY environment variable.")

    def create_customer(self, email: str, name: str | None = None) -> str:
        """Create a Stripe customer and return their ID."""
        try:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={"source": "gloorbot"},
            )
            return customer.id
        except stripe.error.StripeError as e:
            raise StripeError(f"Failed to create customer: {e}")

    def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> tuple[str, str]:
        """
        Create a Stripe Checkout session for subscription.
        Returns (session_id, checkout_url).
        """
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                mode="subscription",
                success_url=success_url,
                cancel_url=cancel_url,
                allow_promotion_codes=True,
                billing_address_collection="required",
            )
            return session.id, session.url
        except stripe.error.StripeError as e:
            raise StripeError(f"Failed to create checkout session: {e}")

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        """
        Create a Stripe Customer Portal session.
        Returns the portal URL.
        """
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return session.url
        except stripe.error.StripeError as e:
            raise StripeError(f"Failed to create portal session: {e}")

    def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> dict:
        """Cancel a subscription."""
        try:
            if at_period_end:
                subscription = stripe.Subscription.modify(
                    subscription_id,
                    cancel_at_period_end=True,
                )
            else:
                subscription = stripe.Subscription.delete(subscription_id)
            return {"status": "canceled", "cancel_at_period_end": at_period_end}
        except stripe.error.StripeError as e:
            raise StripeError(f"Failed to cancel subscription: {e}")

    def get_subscription(self, subscription_id: str) -> dict | None:
        """Get subscription details from Stripe."""
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            return {
                "id": subscription.id,
                "status": subscription.status,
                "current_period_start": datetime.fromtimestamp(
                    subscription.current_period_start, tz=timezone.utc
                ),
                "current_period_end": datetime.fromtimestamp(
                    subscription.current_period_end, tz=timezone.utc
                ),
                "cancel_at_period_end": subscription.cancel_at_period_end,
                "price_id": subscription.items.data[0].price.id if subscription.items.data else None,
            }
        except stripe.error.StripeError:
            return None

    def verify_webhook(self, payload: bytes, signature: str) -> dict | None:
        """
        Verify and parse a Stripe webhook event.
        Returns the event data or None if verification fails.
        """
        if not STRIPE_WEBHOOK_SECRET:
            # In development, parse without verification
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return None

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
            return event
        except (stripe.error.SignatureVerificationError, ValueError):
            return None


def get_stripe_service() -> StripeService | None:
    """Get a StripeService instance if Stripe is configured."""
    try:
        return StripeService()
    except StripeError:
        return None


def is_stripe_configured() -> bool:
    """Check if Stripe is properly configured."""
    return bool(STRIPE_SECRET_KEY and STRIPE_PUBLISHABLE_KEY)


def get_plan_config() -> dict:
    """Get the plan configuration with prices."""
    return PLAN_CONFIG


def price_id_to_plan(price_id: str) -> str:
    """Convert a Stripe price ID to a plan name."""
    for plan_name, config in PLAN_CONFIG.items():
        if config.get("stripe_price_id") == price_id:
            # Return canonical plan name (premium instead of enterprise)
            if plan_name == "enterprise":
                return "premium"
            return plan_name
    # Also check direct env var matches
    if price_id == STRIPE_PRICE_PREMIUM or price_id == STRIPE_PRICE_ENTERPRISE:
        return "premium"
    if price_id == STRIPE_PRICE_PRO:
        return "pro"
    return "free"
