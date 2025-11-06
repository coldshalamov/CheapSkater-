"""Database connectivity helpers."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .models_sql import Base


def get_engine(sqlite_path: str) -> Engine:
    """Create a SQLAlchemy engine for the SQLite database."""

    return create_engine(
        f"sqlite:///{sqlite_path}",
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )


def make_session(engine: Engine) -> sessionmaker[Session]:
    """Create a configured session factory bound to *engine*."""

    return sessionmaker(engine, expire_on_commit=False, future=True)


def init_db(engine: Engine) -> None:
    """Initialise database schema for the configured engine."""

    Base.metadata.create_all(engine)
