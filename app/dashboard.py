"""FastAPI dashboard for exploring Lowe's clearance items."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.storage import repo
from app.storage.db import get_engine, init_db, make_session
from app.storage.models_sql import Observation


LOGGER = get_logger(__name__)
BASE_PATH = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_PATH / "templates"
STATIC_DIR = BASE_PATH / "static"
DATABASE_FILE = Path(__file__).resolve().parent.parent / "orwa_lowes.sqlite"

engine = get_engine(str(DATABASE_FILE))
init_db(engine)
session_factory = make_session(engine)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app = FastAPI(title="CheapSkater Clearance Dashboard")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

Scope = Literal["all", "new"]
STATE_OPTIONS = ["ALL", "WA", "OR"]
DEFAULT_CATEGORY_OPTIONS = [
    "Roofing",
    "Drywall",
    "Insulation",
    "Lumber",
    "Flooring",
    "Plumbing",
    "Electrical",
    "Tools",
    "Paint",
    "Hardware",
]


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


def _normalize_state(value: str | None) -> str | None:
    if not value:
        return None
    upper = value.upper()
    return upper if upper in {"WA", "OR"} else None


def _state_from_zip(zip_code: str | None) -> str | None:
    if not zip_code:
        return None
    digits = "".join(ch for ch in zip_code if ch.isdigit())
    if len(digits) < 3:
        return None
    prefix = int(digits[:3])
    if 970 <= prefix <= 979:
        return "OR"
    if 980 <= prefix <= 994:
        return "WA"
    return None


def _select_items(
    session: Session,
    *,
    scope: Scope,
    state: str | None,
    category: str | None,
) -> list[Observation]:
    if scope == "new":
        return repo.get_new_clearance_today(session, state=state, category=category)
    return repo.get_clearance_items(session, state=state, category=category)


def _collect_categories(session: Session) -> list[str]:
    discovered = repo.list_distinct_categories(session)
    merged = sorted({*DEFAULT_CATEGORY_OPTIONS, *discovered})
    return merged


def _render_dashboard(
    request: Request,
    *,
    scope: Scope,
    state: str | None,
    category: str | None,
    session: Session,
):
    LOGGER.debug(
        "Rendering dashboard", extra={"scope": scope, "state": state, "category": category}
    )
    items = _select_items(session, scope=scope, state=state, category=category)
    categories = _collect_categories(session)
    last_updated = repo.get_latest_timestamp(session)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "items": items,
            "active_scope": scope,
            "state": state or "ALL",
            "category": category,
            "categories": categories,
            "state_options": STATE_OPTIONS,
            "last_updated": last_updated,
            "state_from_zip": _state_from_zip,
        },
    )


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """Return application health information."""

    return {"status": "ok"}


@app.get("/")
def list_clearance(
    request: Request,
    state: str | None = Query(None, description="State filter (WA or OR)."),
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
):
    """Render the full clearance dashboard."""

    normalized_state = _normalize_state(state)
    normalized_category = category or None
    return _render_dashboard(
        request,
        scope="all",
        state=normalized_state,
        category=normalized_category,
        session=session,
    )


@app.get("/new-today")
def list_new_clearance_today(
    request: Request,
    state: str | None = Query(None, description="State filter (WA or OR)."),
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
):
    """Render a page listing items that became clearance deals today."""

    normalized_state = _normalize_state(state)
    normalized_category = category or None
    return _render_dashboard(
        request,
        scope="new",
        state=normalized_state,
        category=normalized_category,
        session=session,
    )


@app.get("/export.xlsx")
def export_excel(
    scope: Scope = Query("all", description="Dataset to export (all or new)."),
    state: str | None = Query(None, description="State filter (WA or OR)."),
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Return an Excel workbook for the current filter selection."""

    normalized_state = _normalize_state(state)
    normalized_category = category or None
    items = _select_items(
        session, scope=scope, state=normalized_state, category=normalized_category
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Clearance"
    headers = [
        "Timestamp (UTC)",
        "State",
        "ZIP",
        "Store",
        "SKU",
        "Title",
        "Category",
        "Price",
        "Was",
        "% Off",
        "Availability",
        "URL",
    ]
    sheet.append(headers)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="004990", end_color="004990", fill_type="solid")
    for cell in sheet[1]:
        cell.font = header_font
        cell.fill = header_fill

    sheet.freeze_panes = "A2"

    for item in items:
        pct_off = item.pct_off * 100 if item.pct_off is not None else None
        sheet.append(
            [
                item.ts_utc.isoformat() if item.ts_utc else None,
                _state_from_zip(item.zip),
                item.zip,
                item.store_name,
                item.sku,
                item.title,
                item.category,
                item.price,
                item.price_was,
                pct_off,
                item.availability,
                item.product_url,
            ]
        )

    for column_cells in sheet.iter_cols(
        min_row=1, max_row=sheet.max_row, max_col=sheet.max_column
    ):
        max_length = 0
        for cell in column_cells:
            if cell.value is None:
                continue
            max_length = max(max_length, len(str(cell.value)))
        if max_length <= 0:
            continue
        column_letter = column_cells[0].column_letter
        sheet.column_dimensions[column_letter].width = min(max_length + 2, 50)

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    state_label = normalized_state or "ALL"
    category_label = (normalized_category or "all").replace(" ", "-")
    filename = f"lowes-{scope}-{state_label.lower()}-{category_label.lower()}.xlsx"
    headers = {
        "Content-Disposition": f"attachment; filename={filename}",
    }
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/clearance")
def api_clearance(
    scope: Scope = Query("all", description="Dataset to export (all or new)."),
    state: str | None = Query(None, description="State filter (WA or OR)."),
    category: str | None = Query(None, description="Optional category filter."),
    session: Session = Depends(get_session),
) -> JSONResponse:
    """Return clearance items as JSON data."""

    normalized_state = _normalize_state(state)
    normalized_category = category or None
    items = _select_items(
        session,
        scope=scope,
        state=normalized_state,
        category=normalized_category,
    )
    payload = [_serialize_observation(item) for item in items]
    return JSONResponse(
        content={
            "items": payload,
            "count": len(payload),
            "scope": scope,
            "state": normalized_state or "ALL",
            "category": normalized_category,
        }
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.dashboard:app", host="0.0.0.0", port=port, reload=False)

