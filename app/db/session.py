from __future__ import annotations

import logging
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def create_engine_from_url(database_url: str):
    kwargs = {"future": True, "pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **kwargs)


def patch_missing_columns(engine) -> None:
    """Best-effort schema patch for columns added to models after a database
    already exists.

    ``Base.metadata.create_all()`` only creates missing *tables* — it never
    alters an existing table to add a newly-declared column. This walks every
    mapped model, compares its declared columns against what's actually in
    the database, and issues ``ALTER TABLE ... ADD COLUMN`` for anything
    missing.

    This is not a substitute for real migrations (see README/handoff notes):
    it only handles simple additive, nullable columns. NOT NULL columns with
    no default are skipped and logged, since blindly adding them to a table
    with existing rows would either fail or silently corrupt data.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for mapper in Base.registry.mappers:
        table = mapper.local_table
        if table is None or table.name not in existing_tables:
            # Brand new table: create_all() already handles this case.
            continue

        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}

        for column in table.columns:
            if column.name in existing_columns:
                continue

            if not column.nullable and column.default is None and column.server_default is None:
                logger.warning(
                    "patch_missing_columns: skipping NOT NULL column '%s.%s' with "
                    "no default — cannot be safely auto-added to an existing table. "
                    "A real migration (with a backfill) is needed.",
                    table.name,
                    column.name,
                )
                continue

            col_type = column.type.compile(dialect=engine.dialect)
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"
            logger.info("patch_missing_columns: applying: %s", ddl)
            with engine.begin() as conn:
                conn.execute(text(ddl))


engine = create_engine_from_url(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.db_sessionmaker
    db = session_factory()
    try:
        yield db
    finally:
        db.close()

