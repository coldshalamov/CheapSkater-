"""FastAPI router for admin endpoints."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.admin.models import ScraperHeartbeat, SystemMessage
from app.admin.service import AdminService
from app.auth.dependencies import get_current_user, _get_db_session
from app.auth.models import User
from app.logging_config import get_logger

router = APIRouter(prefix="/admin", tags=["admin"])

LOGGER = get_logger(__name__)

# Templates
BASE_PATH = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_PATH / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# API key for scraper heartbeats (same as ingest API key)
ADMIN_API_KEY = os.getenv("CHEAPSKATER_INGEST_API_KEY", "")


# ──────────────────────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────────────────────


async def require_admin(request: Request) -> User:
    """Dependency to require admin privileges."""
    user = await get_current_user(request)
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required"
        )
    return user


# ──────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ──────────────────────────────────────────────────────────────────────────────


class HeartbeatRequest(BaseModel):
    """Scraper heartbeat data."""

    scraper_id: str
    scraper_name: str | None = None
    deals_count: int = 0
    errors_count: int = 0
    status_message: str | None = None
    version: str | None = None
    hostname: str | None = None


class SystemMessageRequest(BaseModel):
    """System message creation/update."""

    message: str
    message_type: str = "info"  # info, warning, error, success
    priority: int = 0
    expires_hours: int | None = None


class DealDeleteRequest(BaseModel):
    """Request to delete a deal."""

    deal_id: int | None = None
    sku: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Admin Dashboard UI
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, user: User = Depends(require_admin)):
    """Render the admin dashboard."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        metrics = admin_service.get_dashboard_metrics()
        system_messages = admin_service.get_active_system_messages()
        q = request.query_params.get("q")
        recent_deals = admin_service.get_recent_deals(
            limit=200, q=q, clearance_only=True
        )

        return templates.TemplateResponse(
            "admin/dashboard.html",
            {
                "request": request,
                "user": user,
                "metrics": metrics,
                "system_messages": system_messages,
                "recent_deals": recent_deals,
                "q": q or "",
                "active_scope": "admin",
            },
        )
    finally:
        db_session.close()


@router.get("/users", response_class=HTMLResponse)
async def admin_users(request: Request, user: User = Depends(require_admin)):
    """Render the user management page."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        users_with_stats = admin_service.get_all_users_with_stats()

        return templates.TemplateResponse(
            "admin/users.html",
            {
                "request": request,
                "user": user,
                "users": users_with_stats,
                "active_scope": "admin",
            },
        )
    finally:
        db_session.close()


@router.get("/user/{user_id}", response_class=HTMLResponse)
async def admin_user_detail(
    request: Request, user_id: int, user: User = Depends(require_admin)
):
    """Render detailed user information page."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)

        # Get user
        target_user = db_session.get(User, user_id)
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get activities
        activities = admin_service.get_user_activities(user_id, limit=50)
        unique_ips = admin_service.get_unique_ips_for_user(user_id)
        active_sessions = admin_service.get_active_sessions_for_user(user_id)

        return templates.TemplateResponse(
            "admin/user_detail.html",
            {
                "request": request,
                "user": user,
                "target_user": target_user,
                "activities": activities,
                "unique_ips": unique_ips,
                "active_sessions": active_sessions,
                "active_scope": "admin",
            },
        )
    finally:
        db_session.close()


# ──────────────────────────────────────────────────────────────────────────────
# Scraper Heartbeat API
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/api/heartbeat")
async def scraper_heartbeat(
    request: Request,
    data: HeartbeatRequest,
    x_api_key: str = Depends(lambda r: r.headers.get("X-API-Key", "")),
):
    """Receive heartbeat from scraper."""
    # Validate API key
    if ADMIN_API_KEY and x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        heartbeat = admin_service.update_heartbeat(
            scraper_id=data.scraper_id,
            scraper_name=data.scraper_name,
            deals_count=data.deals_count,
            errors_count=data.errors_count,
            status_message=data.status_message,
            version=data.version,
            hostname=data.hostname,
        )

        return {
            "ok": True,
            "scraper_id": heartbeat.scraper_id,
            "last_heartbeat": heartbeat.last_heartbeat.isoformat(),
        }
    finally:
        db_session.close()


@router.get("/api/scrapers")
async def get_scrapers(user: User = Depends(require_admin)):
    """Get all scraper status information."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        active_scrapers = admin_service.get_active_scrapers(timeout_minutes=5)
        all_scrapers = admin_service.get_all_scrapers()

        return {
            "ok": True,
            "active_count": len(active_scrapers),
            "total_count": len(all_scrapers),
            "scrapers": [
                {
                    "id": s.scraper_id,
                    "name": s.scraper_name,
                    "is_active": s.is_active,
                    "last_heartbeat": s.last_heartbeat.isoformat(),
                    "deals_total": s.deals_ingested_total,
                    "deals_session": s.deals_ingested_session,
                    "errors": s.errors_count,
                    "version": s.version,
                    "hostname": s.hostname,
                    "status_message": s.status_message,
                }
                for s in all_scrapers
            ],
        }
    finally:
        db_session.close()


# ──────────────────────────────────────────────────────────────────────────────
# System Messages API
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/api/system-message")
async def create_system_message(
    data: SystemMessageRequest, user: User = Depends(require_admin)
):
    """Create a new system message."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)

        # Calculate expiration if specified
        expires_at = None
        if data.expires_hours:
            from datetime import timedelta

            expires_at = datetime.now(timezone.utc) + timedelta(
                hours=data.expires_hours
            )

        message = admin_service.create_system_message(
            message=data.message,
            message_type=data.message_type,
            priority=data.priority,
            created_by_user_id=user.id,
            expires_at=expires_at,
        )

        LOGGER.info(
            "[ADMIN] User %s created system message: %s", user.email, data.message[:50]
        )

        return {
            "ok": True,
            "message_id": message.id,
        }
    finally:
        db_session.close()


@router.get("/api/system-messages")
async def get_system_messages():
    """Get all active system messages (public endpoint)."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        messages = admin_service.get_active_system_messages()

        return {
            "ok": True,
            "messages": [
                {
                    "id": m.id,
                    "message": m.message,
                    "type": m.message_type,
                    "priority": m.priority,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }
    finally:
        db_session.close()


@router.delete("/api/system-message/{message_id}")
async def delete_system_message(message_id: int, user: User = Depends(require_admin)):
    """Delete a system message."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        success = admin_service.delete_system_message(message_id)

        if success:
            LOGGER.info(
                "[ADMIN] User %s deleted system message %d", user.email, message_id
            )
            return {"ok": True}
        else:
            raise HTTPException(status_code=404, detail="Message not found")
    finally:
        db_session.close()


# ──────────────────────────────────────────────────────────────────────────────
# Deal Management API
# ──────────────────────────────────────────────────────────────────────────────


@router.delete("/api/deal/{deal_id}")
async def delete_deal(deal_id: int, user: User = Depends(require_admin)):
    """Delete a deal from the database."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        success = admin_service.delete_deal_by_id(deal_id)

        if success:
            LOGGER.info("[ADMIN] User %s deleted deal %d", user.email, deal_id)
            return {"ok": True}
        else:
            raise HTTPException(status_code=404, detail="Deal not found")
    finally:
        db_session.close()


@router.delete("/api/deal/sku/{sku}")
async def delete_deals_by_sku(sku: str, user: User = Depends(require_admin)):
    """Delete all deals for a specific SKU."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        count = admin_service.delete_deals_by_sku(sku)

        LOGGER.info(
            "[ADMIN] User %s deleted %d deals for SKU %s", user.email, count, sku
        )
        return {"ok": True, "deleted_count": count}
    finally:
        db_session.close()


# ──────────────────────────────────────────────────────────────────────────────
# Metrics API
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/api/metrics")
async def get_admin_metrics(user: User = Depends(require_admin)):
    """Get comprehensive admin dashboard metrics."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        metrics = admin_service.get_dashboard_metrics()
        return {"ok": True, **metrics}
    finally:
        db_session.close()


@router.get("/api/stores/discounts")
async def get_store_discounts(hours: int = 24, user: User = Depends(require_admin)):
    """Get average discount percentages by store."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        store_averages = admin_service.get_store_discount_averages(hours=hours)
        return {"ok": True, "stores": store_averages}
    finally:
        db_session.close()


@router.get("/api/ingestion-rate")
async def get_ingestion_rate(hours: int = 1):
    """Get current deal ingestion rate (public endpoint for status page)."""
    db_session = next(_get_db_session())
    try:
        admin_service = AdminService(db_session)
        rate = admin_service.get_ingestion_rate(hours=hours)
        return {"ok": True, **rate}
    finally:
        db_session.close()
