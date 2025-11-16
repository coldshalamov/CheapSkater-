"""Database connectivity helpers."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models_sql import Base


LOGGER = logging.getLogger(__name__)


def _apply_sqlite_pragmas(engine: Engine, timeout_value: float) -> None:
    """Enable WAL mode so dashboard reads do not block while the scraper writes."""

    try:
        with engine.connect() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL"))
            connection.execute(text("PRAGMA synchronous=NORMAL"))
            busy_ms = int(timeout_value * 1000)
            connection.execute(text(f"PRAGMA busy_timeout = {busy_ms}"))
    except Exception as exc:  # pragma: no cover - defensive; best-effort tuning
        LOGGER.warning("Unable to configure SQLite pragmas: %s", exc)


def get_engine(sqlite_path: str, *, busy_timeout: int | float | None = None) -> Engine:
    """Create a SQLAlchemy engine for the SQLite database."""

    timeout_value = float(busy_timeout) if busy_timeout is not None else 30.0

    engine = create_engine(
        f"sqlite:///{sqlite_path}?timeout={timeout_value}",
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": timeout_value},
    )
    _apply_sqlite_pragmas(engine, timeout_value)
    return engine


def make_session(engine: Engine) -> sessionmaker[Session]:
    """Create a configured session factory bound to *engine*."""

    return sessionmaker(engine, expire_on_commit=False, future=True)


def init_db_safe(engine: Engine) -> None:
    """Initialise database schema, creating only missing tables."""

    Base.metadata.create_all(engine, checkfirst=True)


def check_quarantine_table(engine: Engine) -> bool:
    """Return True if the quarantine table exists for *engine*."""

    inspector = inspect(engine)
    return inspector.has_table("quarantine")


# Backwards compatibility for existing imports
init_db = init_db_safe
