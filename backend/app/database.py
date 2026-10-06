"""SQLAlchemy engine/session setup (SQLite by default)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()
logger = logging.getLogger("voice_crm.db")

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Forward-only mini migration: add new nullable columns (and their indexes) to existing tables.

    create_all() creates missing tables but never alters existing ones, so without this an
    existing voice_crm.db would have to be deleted whenever a model gains a column.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            added = False
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable:
                    logger.warning("Cannot add NOT NULL column %s.%s automatically; recreate the database.", table.name, column.name)
                    continue
                ddl = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))
                logger.info("Added column %s.%s", table.name, column.name)
                added = True
            if added:
                for index in table.indexes:
                    index.create(conn, checkfirst=True)


def init_db() -> None:
    """Create all tables and add any columns introduced since the database was created."""
    from . import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
