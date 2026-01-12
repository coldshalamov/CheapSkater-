"""FastAPI routes for deal notifications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, _get_db_session
from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus
from app.auth.stripe_integration import is_stripe_configured, get_stripe_service, PLAN_CONFIG
from app.notifications.models import DealAlert, NotificationLog, NotificationType, NotificationFrequency
from app.logging_config import get_logger
from pathlib import Path

LOGGER = get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


# Pydantic models
class CreateAlertRequest(BaseModel):
    """Request to create a new deal alert."""
    name: str = Field(..., min_length=1, max_length=100)
    alert_type: str = Field(..., description="'category' or 'keyword'")
    category: str | None = None
    keywords: str | None = None
    min_discount: float | None = Field(None, ge=0, le=1)
    max_price: float | None = Field(None, ge=0)
    states: str | None = None
    frequency: str = "instant"


class UpdateAlertRequest(BaseModel):
    """Request to update an existing alert."""
    name: str | None = None
    min_discount: float | None = None
    max_price: float | None = None
    states: str | None = None
    frequency: str | None = None
    is_active: bool | None = None


def _check_subscription(user: User, session: Session) -> bool:
    """Check if user has an active paid subscription."""
    sub = session.query(Subscription).filter(Subscription.user_id == user.id).first()
    if not sub:
        return False
    if sub.plan == SubscriptionPlan.FREE:
        return False
    return sub.is_active_subscription()


def _count_user_alerts(user: User, session: Session) -> int:
    """Count active alerts for a user."""
    return session.query(DealAlert).filter(
        DealAlert.user_id == user.id,
        DealAlert.is_active == True,
    ).count()


@router.get("/", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
):
    """Render the notifications management page."""
    alerts = session.query(DealAlert).filter(DealAlert.user_id == user.id).all()
    subscription = session.query(Subscription).filter(Subscription.user_id == user.id).first()
    
    return templates.TemplateResponse(
        "notifications/manage.html",
        {
            "request": request,
            "user": user,
            "alerts": alerts,
            "subscription": subscription,
            "has_subscription": _check_subscription(user, session),
            "stripe_configured": is_stripe_configured(),
            "active_scope": "notifications",
        },
    )


@router.get("/create", response_class=HTMLResponse)
async def create_alert_page(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
):
    """Render the create alert page."""
    # Get available categories from database
    from app.storage import repo
    categories = repo.list_distinct_categories(session)
    
    return templates.TemplateResponse(
        "notifications/create.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
            "has_subscription": _check_subscription(user, session),
            "alert_price": 10.0,
            "active_scope": "notifications",
        },
    )


@router.post("/create")
async def create_alert(
    request: Request,
    name: str = Form(...),
    alert_type: str = Form(...),
    category: str = Form(None),
    keywords: str = Form(None),
    min_discount: float = Form(None),
    max_price: float = Form(None),
    states: str = Form(None),
    frequency: str = Form("instant"),
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
):
    """Create a new deal alert."""
    # Validate subscription
    if not _check_subscription(user, session):
        raise HTTPException(
            status_code=402,
            detail="Active subscription required to create alerts"
        )
    
    # Validate alert type
    try:
        notification_type = NotificationType(alert_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert type")
    
    # Validate type-specific fields
    if notification_type == NotificationType.CATEGORY and not category:
        raise HTTPException(status_code=400, detail="Category is required for category alerts")
    if notification_type == NotificationType.KEYWORD and not keywords:
        raise HTTPException(status_code=400, detail="Keywords are required for keyword alerts")
    
    # Parse frequency
    try:
        freq = NotificationFrequency(frequency)
    except ValueError:
        freq = NotificationFrequency.INSTANT
    
    # Convert discount to decimal if percentage given
    disc = None
    if min_discount is not None:
        disc = min_discount / 100 if min_discount > 1 else min_discount
    
    # Create alert
    alert = DealAlert(
        user_id=user.id,
        name=name,
        alert_type=notification_type,
        category=category if notification_type == NotificationType.CATEGORY else None,
        keywords=keywords if notification_type == NotificationType.KEYWORD else None,
        min_discount=disc,
        max_price=max_price,
        states=states,
        frequency=freq,
        email_enabled=True,
        is_active=True,
        monthly_price=10.0,
    )
    
    session.add(alert)
    session.commit()
    
    LOGGER.info("Created alert %s for user %s", alert.id, user.id)
    
    return RedirectResponse(url="/notifications", status_code=303)


@router.post("/{alert_id}/toggle")
async def toggle_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
) -> JSONResponse:
    """Toggle an alert's active status."""
    alert = session.query(DealAlert).filter(
        DealAlert.id == alert_id,
        DealAlert.user_id == user.id,
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_active = not alert.is_active
    alert.updated_at = datetime.now(timezone.utc)
    session.commit()
    
    return JSONResponse({
        "ok": True,
        "alert_id": alert_id,
        "is_active": alert.is_active,
    })


@router.delete("/{alert_id}")
async def delete_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
) -> JSONResponse:
    """Delete an alert."""
    alert = session.query(DealAlert).filter(
        DealAlert.id == alert_id,
        DealAlert.user_id == user.id,
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    session.delete(alert)
    session.commit()
    
    return JSONResponse({"ok": True, "deleted": alert_id})


@router.get("/api/alerts")
async def list_alerts_api(
    user: User = Depends(get_current_user),
    session: Session = Depends(_get_db_session),
) -> JSONResponse:
    """API endpoint to list all user alerts."""
    alerts = session.query(DealAlert).filter(DealAlert.user_id == user.id).all()
    
    return JSONResponse({
        "alerts": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.alert_type.value,
                "category": a.category,
                "keywords": a.keywords,
                "min_discount": a.min_discount,
                "max_price": a.max_price,
                "states": a.states,
                "frequency": a.frequency.value,
                "is_active": a.is_active,
                "monthly_price": a.monthly_price,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
            }
            for a in alerts
        ]
    })
