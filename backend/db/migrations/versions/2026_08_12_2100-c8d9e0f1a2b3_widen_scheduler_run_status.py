"""widen scheduler_job_runs.status so timeout_abandoned fits

The column is VARCHAR(16). `timeout_abandoned` is 17 characters, so on
PostgreSQL every attempt to record one raised
`StringDataRightTruncation` and the row was dropped — the run vanished
from history entirely, which is the opposite of what that status exists
to do: it marks a job that overran its budget and kept running, the one
outcome an operator most needs to see.

SQLite does not enforce VARCHAR lengths, so dev, CI and the SQLite beta
box wrote the value happily and nothing failed until it reached a
Postgres instance. Observed on production 2026-08-12: four events, four
lost rows.

32 rather than 17 — the next status name should not need a migration.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op

revision = "c8d9e0f1a2b3"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None

_TABLE = "scheduler_job_runs"
_COLUMN = "status"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    # SQLite ignores the length entirely and its ALTER support is limited;
    # a batch rebuild would be churn for a constraint it never applied.
    if _is_sqlite():
        return

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return

    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    if _is_sqlite():
        return

    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return

    # Rows written since the upgrade can be longer than the old limit, so
    # narrowing blind would fail. Truncate to the old width first.
    op.execute(
        sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = LEFT({_COLUMN}, 16) WHERE LENGTH({_COLUMN}) > 16")
    )
    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
