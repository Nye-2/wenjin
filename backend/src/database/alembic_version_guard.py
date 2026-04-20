"""Helpers to keep Alembic version table compatible with long revision IDs."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import Column, MetaData, String, Table, inspect, text
from sqlalchemy.engine import Connection

ALEMBIC_VERSION_TABLE = "alembic_version"
ALEMBIC_VERSION_COLUMN = "version_num"
ALEMBIC_VERSION_MIN_LENGTH = 191

AlembicVersionGuardAction = Literal["created", "altered", "noop", "missing_column"]


def ensure_alembic_version_column_width(
    connection: Connection,
    *,
    min_length: int = ALEMBIC_VERSION_MIN_LENGTH,
) -> AlembicVersionGuardAction:
    """Ensure ``alembic_version.version_num`` can store long revision identifiers."""
    if min_length < 32:
        raise ValueError("min_length must be >= 32 for Alembic compatibility")

    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())

    if ALEMBIC_VERSION_TABLE not in table_names:
        metadata = MetaData()
        version_table = Table(
            ALEMBIC_VERSION_TABLE,
            metadata,
            Column(ALEMBIC_VERSION_COLUMN, String(min_length), nullable=False, primary_key=True),
        )
        metadata.create_all(connection, tables=[version_table], checkfirst=True)
        return "created"

    version_columns = inspector.get_columns(ALEMBIC_VERSION_TABLE)
    version_column = next(
        (column for column in version_columns if column.get("name") == ALEMBIC_VERSION_COLUMN),
        None,
    )
    if version_column is None:
        return "missing_column"

    current_length = getattr(version_column.get("type"), "length", None)
    if isinstance(current_length, int) and current_length >= min_length:
        return "noop"

    connection.execute(
        text(
            f"ALTER TABLE {ALEMBIC_VERSION_TABLE} "
            f"ALTER COLUMN {ALEMBIC_VERSION_COLUMN} TYPE VARCHAR({min_length})"
        )
    )
    return "altered"
