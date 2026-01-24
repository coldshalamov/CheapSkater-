"""FastAPI router for authentication endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus
from app.notifications.models import DealAlert
from app.notifications.email_service import send_password_reset_email
from app.auth.service import AuthService, InvalidCredentials, UserExists, TokenExpired, UserNotFound
from app.auth.dependencies import get_current_user, get_optional_user, _get_db_session
from app.auth.stripe_integration import (
    StripeService,
    StripeError,
    get_stripe_service,
    is_stripe_configured,
    get_plan_config,
    price_id_to_plan,
    STRIPE_PUBLISHABLE_KEY,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Templates
BASE_PATH = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_PATH / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    ok: bool
    message: str
    user_id: int | None = None
    email: str | None = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    is_active: bool
    current_period_end: datetime | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Auth Pages (HTML)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None, next: str | None = None):
    """Render the login page."""
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": error,
            "next_url": next or "/",
            "active_scope": "login",
        },
    )


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str | None = None):
    """Render the registration page."""
    user = await get_optional_user(request)
    if user:
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "error": error,
            "active_scope": "register",
        },
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Render the forgot password page."""
    if await get_optional_user(request):
        return RedirectResponse(url="/", status_code=303)
        
    return templates.TemplateResponse(
        "auth/forgot_password.html",
        {"request": request, "active_scope": "login"}
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str):
    """Render the reset password page."""
    if not token:
        return RedirectResponse(url="/auth/login", status_code=303)

    return templates.TemplateResponse(
        "auth/reset_password.html",
        {"request": request, "token": token, "active_scope": "login"}
    )


@router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    """Render the account settings page."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/auth/login?next=/auth/account", status_code=303)
    
    # Get subscription
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        subscription = auth_service.get_subscription(user.id)
        
        return templates.TemplateResponse(
            "auth/account.html",
            {
                "request": request,
                "user": user,
                "subscription": subscription,
                "plan_config": get_plan_config(),
                "stripe_configured": is_stripe_configured(),
                "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
                "active_scope": "account",
            },
        )
    finally:
        db_session.close()


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request):
    """Render the pricing page."""
    user = await get_optional_user(request)
    
    subscription = None
    if user:
        db_session = next(_get_db_session())
        try:
            auth_service = AuthService(db_session)
            subscription = auth_service.get_subscription(user.id)
        finally:
            db_session.close()
    
    return templates.TemplateResponse(
        "auth/pricing.html",
        {
            "request": request,
            "user": user,
            "subscription": subscription,
            "plan_config": get_plan_config(),
            "stripe_configured": is_stripe_configured(),
            "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
            "active_scope": "pricing",
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Auth API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next_url: Annotated[str, Form()] = "/",
):
    """Process login form."""
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)

        try:
            user = auth_service.authenticate(email, password)
        except InvalidCredentials:
            return RedirectResponse(
                url=f"/auth/login?error=Invalid+email+or+password&next={next_url}",
                status_code=303,
            )

        # Update last_login_at
        user.last_login_at = datetime.now(timezone.utc)
        db_session.commit()

        # Store user in session
        request.scope["session"]["user_id"] = user.id
        request.scope["session"]["email"] = user.email

        return RedirectResponse(url=next_url, status_code=303)
    finally:
        db_session.close()


@router.post("/register")
async def register(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str | None, Form()] = None,
):
    """Process registration form."""
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        
        # Validate password
        if len(password) < 8:
            return RedirectResponse(
                url="/auth/register?error=Password+must+be+at+least+8+characters",
                status_code=303,
            )
        
        try:
            user = auth_service.register_user(email, password, display_name)
        except UserExists:
            return RedirectResponse(
                url="/auth/register?error=An+account+with+this+email+already+exists",
                status_code=303,
            )
        
        # Log the user in
        request.scope["session"]["user_id"] = user.id
        request.scope["session"]["email"] = user.email
        
        return RedirectResponse(url="/auth/account", status_code=303)
    finally:
        db_session.close()

@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password(request: Request, email: Annotated[str, Form()]):
    """Process forgot password request."""
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        token = auth_service.create_reset_token(email)
        
        if token:
            # Generate link
            base_url = str(request.base_url).rstrip("/")
            reset_link = f"{base_url}/auth/reset-password?token={token}"
            
            # Send email
            send_password_reset_email(email, reset_link)
        
        # Always return success to prevent email enumeration
        return templates.TemplateResponse(
            "auth/forgot_password.html",
            {
                "request": request,
                "success": "If an account exists with that email, we have sent password reset instructions.",
                "active_scope": "login"
            },
        )
    finally:
        db_session.close()


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password(
    request: Request,
    token: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()]
):
    """Process password reset."""
    if password != confirm_password:
        return templates.TemplateResponse(
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "Passwords do not match",
                "active_scope": "login"
            },
        )
        
    if len(password) < 8:
         return templates.TemplateResponse(
            "auth/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "Password must be at least 8 characters",
                "active_scope": "login"
            },
        )

    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        try:
            user = auth_service.reset_password(token, password)
            
            # Log the user in automatically
            request.scope["session"]["user_id"] = user.id
            request.scope["session"]["email"] = user.email
            
            return RedirectResponse(url="/auth/account?message=Password+reset+successful", status_code=303)
            
        except (UserNotFound, TokenExpired) as e:
            return templates.TemplateResponse(
                "auth/reset_password.html",
                {
                    "request": request,
                    "token": token,
                    "error": str(e),
                    "active_scope": "login"
                },
            )
    finally:
        db_session.close()


@router.get("/logout")
async def logout(request: Request):
    """Log out and clear session."""
    request.scope["session"].clear()
    return RedirectResponse(url="/", status_code=303)


@router.post("/api/register", response_model=AuthResponse)
async def api_register(request: Request, data: RegisterRequest):
    """API endpoint for registration."""
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        
        try:
            user = auth_service.register_user(data.email, data.password, data.display_name)
        except UserExists:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )
        
        request.scope["session"]["user_id"] = user.id
        request.scope["session"]["email"] = user.email
        
        return AuthResponse(ok=True, message="Registration successful", user_id=user.id, email=user.email)
    finally:
        db_session.close()


@router.post("/api/login", response_model=AuthResponse)
async def api_login(request: Request, data: LoginRequest):
    """API endpoint for login."""
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        
        try:
            user = auth_service.authenticate(data.email, data.password)
        except InvalidCredentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        request.scope["session"]["user_id"] = user.id
        request.scope["session"]["email"] = user.email
        
        return AuthResponse(ok=True, message="Login successful", user_id=user.id, email=user.email)
    finally:
        db_session.close()


# ──────────────────────────────────────────────────────────────────────────────
# Subscription Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(request: Request):
    """Get current user's subscription status."""
    user = await get_current_user(request)
    
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        subscription = auth_service.get_subscription(user.id)
        
        if not subscription:
            return SubscriptionResponse(
                plan="free",
                status="active",
                is_active=True,
            )
        
        return SubscriptionResponse(
            plan=subscription.plan.value,
            status=subscription.status.value,
            is_active=subscription.is_active_subscription(),
            current_period_end=subscription.current_period_end,
        )
    finally:
        db_session.close()


@router.post("/checkout")
async def create_checkout(request: Request, plan: Annotated[str, Form()]):
    """Create a Stripe checkout session."""
    user = await get_optional_user(request)
    if not user:
        return RedirectResponse(url="/auth/login?next=/auth/pricing", status_code=303)
    
    stripe_service = get_stripe_service()
    if not stripe_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not available",
        )
    
    plan_config = get_plan_config()
    if plan not in plan_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid plan",
        )
    
    price_id = plan_config[plan].get("stripe_price_id")
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plan not configured for payments",
        )
    
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        
        # Ensure user has a Stripe customer ID
        if not user.stripe_customer_id:
            customer_id = stripe_service.create_customer(user.email, user.display_name)
            user.stripe_customer_id = customer_id
            db_session.commit()
        else:
            customer_id = user.stripe_customer_id
        
        # Get base URL
        base_url = str(request.base_url).rstrip("/")
        
        session_id, checkout_url = stripe_service.create_checkout_session(
            customer_id=customer_id,
            price_id=price_id,
            success_url=f"{base_url}/auth/account?checkout=success",
            cancel_url=f"{base_url}/auth/pricing?checkout=canceled",
        )
        
        return RedirectResponse(url=checkout_url, status_code=303)
    except StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        db_session.close()


@router.get("/portal")
async def customer_portal(request: Request):
    """Redirect to Stripe Customer Portal for subscription management."""
    user = await get_current_user(request)
    
    if not user.stripe_customer_id:
        return RedirectResponse(url="/auth/pricing", status_code=303)
    
    stripe_service = get_stripe_service()
    if not stripe_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not available",
        )
    
    try:
        base_url = str(request.base_url).rstrip("/")
        portal_url = stripe_service.create_portal_session(
            customer_id=user.stripe_customer_id,
            return_url=f"{base_url}/auth/account",
        )
        return RedirectResponse(url=portal_url, status_code=303)
    except StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Stripe Webhooks
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    stripe_service = get_stripe_service()
    if not stripe_service:
        return {"received": False, "error": "Stripe not configured"}
    
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    
    event = stripe_service.verify_webhook(payload, signature)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
    
    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    
    db_session = next(_get_db_session())
    try:
        auth_service = AuthService(db_session)
        
        if event_type == "checkout.session.completed":
            # Payment successful
            customer_id = data.get("customer")
            subscription_id = data.get("subscription")
            
            if customer_id and subscription_id:
                user = auth_service.get_user_by_stripe_customer(customer_id)
                if user:
                    # Get subscription details
                    sub_details = stripe_service.get_subscription(subscription_id)
                    if sub_details:
                        plan_name = price_id_to_plan(sub_details.get("price_id", ""))
                        # Map plan name to enum, handling premium/enterprise
                        if plan_name == "premium":
                            plan = SubscriptionPlan.PREMIUM
                        elif plan_name == "enterprise":
                            plan = SubscriptionPlan.PREMIUM  # Enterprise is legacy for Premium
                        elif plan_name == "pro":
                            plan = SubscriptionPlan.PRO
                        elif plan_name != "free":
                            plan = SubscriptionPlan.PRO  # Default paid tier
                        else:
                            plan = SubscriptionPlan.FREE
                        
                        auth_service.update_subscription(
                            user_id=user.id,
                            stripe_subscription_id=subscription_id,
                            stripe_price_id=sub_details.get("price_id"),
                            plan=plan,
                            status=SubscriptionStatus.ACTIVE,
                            current_period_start=sub_details.get("current_period_start"),
                            current_period_end=sub_details.get("current_period_end"),
                        )
            
            # Handle Deal Alert subscriptions
            metadata = data.get("metadata", {})
            if metadata.get("type") == "alert_subscription":
                alert_id = metadata.get("alert_id")
                subscription_id = data.get("subscription")
                if alert_id and subscription_id:
                    alert = db_session.query(DealAlert).filter(DealAlert.id == int(alert_id)).first()
                    if alert:
                        alert.is_active = True
                        alert.stripe_subscription_item_id = subscription_id  # Storing subscription ID here
                        alert.updated_at = datetime.now(timezone.utc)
                        db_session.commit()
        
        elif event_type == "customer.subscription.updated":
            subscription_id = data.get("id")
            customer_id = data.get("customer")
            
            if customer_id:
                user = auth_service.get_user_by_stripe_customer(customer_id)
                if user:
                    status_map = {
                        "active": SubscriptionStatus.ACTIVE,
                        "past_due": SubscriptionStatus.PAST_DUE,
                        "canceled": SubscriptionStatus.CANCELED,
                        "unpaid": SubscriptionStatus.UNPAID,
                        "trialing": SubscriptionStatus.TRIALING,
                        "incomplete": SubscriptionStatus.INCOMPLETE,
                    }
                    status_str = data.get("status", "active")
                    sub_status = status_map.get(status_str, SubscriptionStatus.ACTIVE)
                    
                    auth_service.update_subscription(
                        user_id=user.id,
                        status=sub_status,
                        cancel_at_period_end=data.get("cancel_at_period_end", False),
                    )
        
        elif event_type == "customer.subscription.deleted":
            customer_id = data.get("customer")
            
            if customer_id:
                user = auth_service.get_user_by_stripe_customer(customer_id)
                if user:
                    auth_service.update_subscription(
                        plan=SubscriptionPlan.FREE,
                        status=SubscriptionStatus.CANCELED,
                    )
            
            # Handle Deal Alert cancellations
            # We don't have metadata here usually, so search by subscription ID
            subscription_id = data.get("id")
            if subscription_id:
                alert = db_session.query(DealAlert).filter(DealAlert.stripe_subscription_item_id == subscription_id).first()
                if alert:
                    alert.is_active = False
                    alert.updated_at = datetime.now(timezone.utc)
                    db_session.commit()
        
        return {"received": True}
    finally:
        db_session.close()
