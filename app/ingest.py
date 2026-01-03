r"""
Cheapskater Ingest API - Receives deals from Gloorbot coordinator.

INSTALLATION:
1. Copy this file to: C:/Users/User/Documents/GitHub/Cheapskater_FULL_20251204_132158/app/ingest.py

2. Edit app/dashboard.py and add near the top imports:
   from app.ingest import router as ingest_router

3. After the line `app = FastAPI(...)`, add:
   app.include_router(ingest_router)

4. Set environment variable on Render:
   CHEAPSKATER_INGEST_API_KEY=your-secret-key-here
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.storage.db import get_engine, make_session
from app.storage.models_sql import Store
from app.storage import repo

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# API key for authentication (set via environment variable)
INGEST_API_KEY = os.getenv("CHEAPSKATER_INGEST_API_KEY", "")

# Database setup (same pattern as dashboard.py)
DATABASE_FILE = Path(__file__).resolve().parent.parent / "orwa_lowes.sqlite"
DB_BUSY_TIMEOUT = float(os.getenv("DB_BUSY_TIMEOUT", "30"))
_engine = get_engine(str(DATABASE_FILE), busy_timeout=DB_BUSY_TIMEOUT)
_session_factory = make_session(_engine)


def get_session():
    """Dependency to get a database session."""
    with _session_factory() as session:
        yield session


class GloorbotDeal(BaseModel):
    """Deal format from Gloorbot coordinator."""
    store_id: str
    store_name: str
    category_url: str
    product_url: str
    title: str
    price: float
    was_price: float
    pct_off: float
    found_at: str  # ISO8601 datetime


class IngestRequest(BaseModel):
    """Batch of deals from Gloorbot."""
    source: str = Field(default="gloorbot", description="Source system identifier")
    deals: list[GloorbotDeal]


class IngestResponse(BaseModel):
    ok: bool
    accepted: int
    errors: int = 0
    message: str = ""


def extract_sku_from_url(product_url: str) -> str | None:
    """Extract SKU from Lowe's product URL.

    Examples:
        https://www.lowes.com/pd/Product-Name/5001844889 -> 5001844889
        https://www.lowes.com/pd/DEWALT-Drill/1234567 -> 1234567
    """
    match = re.search(r'/pd/[^/]+/(\d+)', product_url)
    if match:
        return match.group(1)
    match = re.search(r'/(\d{6,})(?:\?|$)', product_url)
    if match:
        return match.group(1)
    return None


def extract_category_from_url(category_url: str) -> str:
    """Extract category name from Lowe's category URL.

    Examples:
        https://www.lowes.com/pl/Power-tools/4294857564 -> Power Tools
        https://www.lowes.com/pl/Drill-bits--Power-tool-accessories/4294857975 -> Drill Bits
    """
    match = re.search(r'/pl/([^/]+)/\d+', category_url)
    if match:
        raw = match.group(1)
        parts = raw.split('--')
        cleaned = parts[0].replace('-', ' ').strip()
        return cleaned.title()
    return "Clearance"


def parse_store_info(store_id: str, store_name: str) -> dict[str, str]:
    """Parse store_name to extract city and state.

    Examples:
        "Seattle, WA (#0001)" -> city="Seattle", state="WA"
        "Portland #1234" -> city="Portland", state=""
    """
    city = ""
    state = ""
    match = re.match(r'^([^,]+),\s*([A-Z]{2})', store_name)
    if match:
        city = match.group(1).strip()
        state = match.group(2).strip()
    else:
        city = re.sub(r'\s*[#(].*', '', store_name).strip()
    return {"city": city, "state": state}


@router.post("/deals", response_model=IngestResponse)
def ingest_deals(
    request: IngestRequest,
    session: Session = Depends(get_session),
    x_api_key: str = Header(default="", alias="X-API-Key"),
):
    """Receive deals from Gloorbot and insert into Cheapskater database."""

    # Validate API key if configured
    if INGEST_API_KEY and x_api_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    accepted = 0
    errors = 0

    for deal in request.deals:
        try:
            sku = extract_sku_from_url(deal.product_url)
            if not sku:
                errors += 1
                continue

            category = extract_category_from_url(deal.category_url)
            store_info = parse_store_info(deal.store_id, deal.store_name)

            # Parse timestamp
            try:
                ts = datetime.fromisoformat(deal.found_at.replace('Z', '+00:00'))
            except Exception:
                ts = datetime.now(timezone.utc)

            # Ensure store exists
            store = session.get(Store, deal.store_id)
            if store is None:
                store = Store(
                    id=deal.store_id,
                    name=deal.store_name,
                    city=store_info["city"],
                    state=store_info["state"],
                    zip="",  # Not available from Gloorbot
                )
                session.add(store)
                session.flush()

            # Update price history
            repo.update_price_history(
                session,
                retailer="lowes",
                store_id=deal.store_id,
                sku=sku,
                title=deal.title[:500],
                category=category,
                ts_utc=ts,
                price=deal.price,
                price_was=deal.was_price,
                pct_off=deal.pct_off,
                availability="In Stock",
                product_url=deal.product_url,
                image_url=None,
                clearance=True,
            )

            accepted += 1

        except Exception:
            errors += 1
            continue

    session.commit()

    return IngestResponse(
        ok=True,
        accepted=accepted,
        errors=errors,
        message=f"Processed {len(request.deals)} deals from {request.source}"
    )


@router.get("/health")
def ingest_health():
    """Health check for the ingest API."""
    return {"ok": True, "configured": bool(INGEST_API_KEY)}
