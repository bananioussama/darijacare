"""Database engine and sessions (SQLAlchemy 2.0).

PostgreSQL in normal use (docker-compose); SQLite is accepted for unit tests only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Declarative base of every table."""


def make_engine(url: str) -> Engine:
    """Engine for ``url``; SQLite gets foreign keys on and a shared in-memory pool."""
    if not url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True)
    kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory; objects stay readable after commit (responses are built from them)."""
    return sessionmaker(bind=engine, expire_on_commit=False)
