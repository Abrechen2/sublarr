"""add subtitle_format_requirement column to series_settings

Per-series subtitle format requirement. NULL means inherit the global
behavior (ASS preferred with SRT fallback); "require_ass" means the wanted
pipeline never falls back to SRT provider results for this series.

Guarded with a column check: the schema is also created straight from the
models via create_all() (fresh installs, the test harness), so the migration
must be a no-op when the column is already there.

Revision ID: a4b5c6d7e8f9
Revises: f8c9d0e1a2b3
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "a4b5c6d7e8f9"
down_revision = "f8c9d0e1a2b3"
branch_labels = None
depends_on = None

_COLUMN = "subtitle_format_requirement"


def _has_column(bind) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table("series_settings"):
        return False
    return _COLUMN in {c["name"] for c in insp.get_columns("series_settings")}


def upgrade() -> None:
    if _has_column(op.get_bind()):
        return
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_column(op.get_bind()):
        return
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.drop_column(_COLUMN)
