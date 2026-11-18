"""Alembic environment: tables of ``darijacare.api.models``, URL from the API settings.

``config.attributes`` lets callers (tests, the CLI) pass a ``connection`` or a
``database_url`` and keep their own logging (``configure_logger=False``).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from darijacare.api import models  # noqa: F401  (registers the tables on Base.metadata)
from darijacare.api.db import Base
from darijacare.api.settings import Settings

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def database_url() -> str:
    url = config.attributes.get("database_url")
    return str(url) if url else Settings().sqlalchemy_url()


def run_offline() -> None:
    """Emit the SQL without connecting (``alembic upgrade head --sql``)."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    """Apply the migrations on a live connection."""
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
