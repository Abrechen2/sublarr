"""Add DateTime type to subtitle_health_results.checked_at

BREAKING CHANGE: subtitle_health_results.checked_at changes from TEXT to
DateTime(timezone=True).

Revision ID: 9852305585cd
Revises: make_glossary_series_id_nullable
Create Date: 2026-04-02
"""

from alembic import op

revision = "9852305585cd"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

_TABLE = "subtitle_health_results"
_COL = "checked_at"
_EPOCH = "1970-01-01 00:00:00"


def upgrade() -> None:
    op.execute(
        f"UPDATE {_TABLE} SET {_COL} = "
        f"REPLACE(REPLACE({_COL}, 'T', ' '), '+00:00', '') "
        f"WHERE {_COL} IS NOT NULL AND {_COL} != ''"
    )
    op.execute(
        f"UPDATE {_TABLE} SET {_COL} = REPLACE({_COL}, 'Z', '') "
        f"WHERE {_COL} IS NOT NULL AND {_COL} LIKE '%Z'"
    )
    dialect = op.get_context().dialect.name
    if dialect == "postgresql":
        op.execute(
            f"UPDATE {_TABLE} SET {_COL} = '{_EPOCH}' "
            f"WHERE {_COL} IS NOT NULL AND TRIM({_COL}) = ''"
        )
        op.execute(
            f"ALTER TABLE {_TABLE} ALTER COLUMN {_COL} "
            f"TYPE TIMESTAMP WITH TIME ZONE "
            f"USING {_COL}::timestamp AT TIME ZONE 'UTC'"
        )


def downgrade() -> None:
    raise NotImplementedError(
        "DateTime migration for subtitle_health_results.checked_at downgrade "
        "is not supported. Restore from backup."
    )
