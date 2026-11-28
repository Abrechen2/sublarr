"""Add the model columns an Alembic-untracked database is missing.

An install first built by ``create_all()`` never gets an ``alembic_version``
table, so it never replays a migration, and ``create_all()`` adds missing
tables but never missing columns. ``app._patch_pre_alembic_columns`` used to
list each migration-added column by hand; every column a release forgot
broke those installs (the beta outages of 2026-08-09 and 2026-08-28, and the
four columns from 1.19-1.21 that stopped every wanted scan). This module
derives the missing columns from the models instead.

Rules for one column:
- the type is the model type compiled for the database's dialect;
- a scalar model default (or a server default) becomes the SQL default, so
  existing rows get the value the ORM would have written;
- NOT NULL is kept only together with such a default. Without one, SQLite
  refuses the column and Postgres fails on existing rows, so the column is
  added nullable and the ORM fills it on write;
- primary-key columns are never added (a table without its key is beyond
  repair by ALTER TABLE).
"""

from __future__ import annotations

import sqlalchemy as sa


def _default_sql(column: sa.Column, dialect) -> str | None:
    server_default = column.server_default
    if server_default is not None and hasattr(server_default, "arg"):
        arg = server_default.arg
        if isinstance(arg, str):
            return (
                sa.literal(arg)
                .compile(dialect=dialect, compile_kwargs={"literal_binds": True})
                .string
            )
        return str(arg.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if not isinstance(value, (bool, int, float, str)):
        return None
    return str(
        sa.literal(value, type_=column.type).compile(
            dialect=dialect, compile_kwargs={"literal_binds": True}
        )
    )


def column_ddl(table_name: str, column: sa.Column, dialect) -> str:
    """``ALTER TABLE ... ADD COLUMN ...`` for one model column."""
    parts = [f"ALTER TABLE {table_name} ADD COLUMN {column.name}"]
    parts.append(column.type.compile(dialect=dialect))
    default = _default_sql(column, dialect)
    if default is not None:
        if not column.nullable:
            parts.append("NOT NULL")
        parts.append(f"DEFAULT {default}")
    return " ".join(parts)


def missing_column_ddl(inspector, metadata: sa.MetaData, dialect) -> list[str]:
    """Statements that add every model column an existing table lacks."""
    statements = []
    for table in metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # create_all() creates whole tables
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or column.primary_key:
                continue
            statements.append(column_ddl(table.name, column, dialect))
    return statements
