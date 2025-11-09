"""FastAPI dashboard for exploring Lowe's clearance items."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.storage import repo
from app.storage.db import get_engine, make_session
from app.storage.models_sql import Observation


LOGGER = get_logger(__name__)
BASE_PATH = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_PATH / "templates"
STATIC_DIR = BASE_PATH / "static"
DATABASE_FILE = Path(__file__).resolve().parent.parent / "orwa_lowes.sqlite"

engine = get_engine(str(DATABASE_FILE))
session_factory = make_session(engine)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app = FastAPI(title="CheapSkater Clearance Dashboard")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def get_session() -> Iterable[Session]:
    """Dependency that yields a SQLAlchemy session."""

    with session_factory() as session:
        yield session


def _serialize_observation(obs: Observation) -> dict[str, Any]:
    """Convert an Observation ORM object into a JSON-serialisable mapping."""

    return {
        "id": obs.id,
        "ts_utc": obs.ts_utc.isoformat() if obs.ts_utc else None,
        "retailer": obs.retailer,
        "store_id": obs.store_id,
        "store_name": obs.store_name,
        "zip": obs.zip,
        "sku": obs.sku,
        "title": obs.title,
        "category": obs.category,
        "price": obs.price,
        "price_was": obs.price_was,
        "pct_off": obs.pct_off,
        "availability": obs.availability,
        "product_url": obs.product_url,
        "image_url": obs.image_url,
        "clearance": obs.clearance,
    }


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """Return application health information."""

    return {"status": "ok"}


@app.get("/")
def list_clearance(
    request: Request,
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
):
    """Render a page listing clearance items with optional category filtering."""

    if category:
        LOGGER.info("Fetching clearance items for category: %s", category)
        items = repo.get_clearance_by_category(session, category)
    else:
        items = repo.get_clearance_items(session)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "items": items,
            "category": category,
        },
    )


@app.get("/new-today")
def list_new_clearance_today(
    request: Request,
    session: Session = Depends(get_session),
):
    """Render a page listing items that became clearance deals today."""

    items = repo.get_new_clearance_today(session)
    return templates.TemplateResponse(
        "new_today.html",
        {
            "request": request,
            "items": items,
        },
    )


@app.get("/api/clearance")
def api_clearance(
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Return clearance items as JSON data."""

    if category:
        LOGGER.info("Fetching API clearance items for category: %s", category)
        items = repo.get_clearance_by_category(session, category)
    else:
        items = repo.get_clearance_items(session)
    payload = [_serialize_observation(item) for item in items]
    return JSONResponse(content={"items": payload, "count": len(payload)})


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.dashboard:app", host="0.0.0.0", port=port, reload=False)
