"""Database connectivity helpers."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models_sql import Base


def get_engine(sqlite_path: str) -> Engine:
    """Create a SQLAlchemy engine for the SQLite database."""

    return create_engine(
        f"sqlite:///{sqlite_path}?timeout=30",
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30},
    )


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
