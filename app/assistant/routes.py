"""FastAPI routes for the AI deal assistant."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path

from app.logging_config import get_logger
from app.storage import repo
from app.assistant.zai_service import generate_deal_summary, is_zai_configured

LOGGER = get_logger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _get_db_session():
    """Get database session - import from dashboard to share connection."""
    from app.dashboard import session_factory
    with session_factory() as session:
        yield session


def _get_user_from_request(request: Request, session: Session):
    """Get user from session if logged in."""
    session_data = request.scope.get("session", {})
    if session_data.get("user_id"):
        from app.auth.service import AuthService
        try:
            return AuthService(session).get_user_by_id(session_data["user_id"])
        except Exception:
            pass
    return None


def _format_deals_for_display(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format deals for template display."""
    formatted = []
    for deal in deals[:50]:  # Limit to 50 deals
        pct_off = deal.get("pct_off", 0)
        if pct_off and pct_off < 1:
            pct_off = pct_off * 100

        formatted.append({
            "sku": deal.get("sku", ""),
            "title": deal.get("title", "Unknown Product"),
            "price": deal.get("price", 0),
            "price_was": deal.get("price_was", 0),
            "pct_off": pct_off,
            "category": deal.get("category", "Other"),
            "store_label": deal.get("store_name", deal.get("store_label", "Store")),
            "store_state": deal.get("store_state", ""),
            "product_url": deal.get("product_url", "#"),
            "image_url": deal.get("image_url", ""),
        })
    return formatted


@router.get("/", response_class=HTMLResponse)
async def assistant_page(
    request: Request,
    region: str = "all",
    session: Session = Depends(_get_db_session),
):
    """Render the AI deal assistant page with today's deal summary."""
    user = _get_user_from_request(request, session)

    # Fetch today's best deals
    try:
        if region == "FL":
            deals = repo.get_new_clearance_today(session, region="FL")
        elif region == "WA_OR":
            deals = repo.get_new_clearance_today(session, region="WA_OR")
        else:
            # Get from all regions
            deals = repo.get_new_clearance_today(session)
    except Exception as e:
        LOGGER.error("Error fetching deals: %s", e)
        deals = []

    # Convert to dicts if needed
    deal_dicts = []
    for deal in deals:
        if hasattr(deal, "__dict__"):
            deal_dicts.append({k: v for k, v in deal.__dict__.items() if not k.startswith("_")})
        elif isinstance(deal, dict):
            deal_dicts.append(deal)

    # Sort by discount percentage
    deal_dicts.sort(key=lambda d: d.get("pct_off", 0) or 0, reverse=True)

    # Generate AI summary
    summary = generate_deal_summary(deal_dicts[:30], region=region)

    # Format for display
    display_deals = _format_deals_for_display(deal_dicts)

    last_updated = datetime.now(timezone.utc)

    return templates.TemplateResponse(
        "assistant.html",
        {
            "request": request,
            "user": user,
            "summary": summary,
            "deals": display_deals,
            "deal_count": len(deal_dicts),
            "region": region,
            "last_updated": last_updated,
            "ai_configured": is_zai_configured(),
            "active_scope": "assistant",
        },
    )


@router.get("/api/summary", response_class=JSONResponse)
async def api_summary(
    region: str = "all",
    session: Session = Depends(_get_db_session),
):
    """API endpoint to get just the AI summary."""
    try:
        if region == "FL":
            deals = repo.get_new_clearance_today(session, region="FL")
        elif region == "WA_OR":
            deals = repo.get_new_clearance_today(session, region="WA_OR")
        else:
            deals = repo.get_new_clearance_today(session)
    except Exception as e:
        LOGGER.error("Error fetching deals: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    # Convert to dicts if needed
    deal_dicts = []
    for deal in deals:
        if hasattr(deal, "__dict__"):
            deal_dicts.append({k: v for k, v in deal.__dict__.items() if not k.startswith("_")})
        elif isinstance(deal, dict):
            deal_dicts.append(deal)

    deal_dicts.sort(key=lambda d: d.get("pct_off", 0) or 0, reverse=True)

    summary = generate_deal_summary(deal_dicts[:30], region=region)

    return JSONResponse({
        "summary": summary,
        "deal_count": len(deal_dicts),
        "region": region,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_configured": is_zai_configured(),
    })
