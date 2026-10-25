"""Automation queue series_key: the owner key an auto-sync row was queued for.

Lets the drain recheck a standalone sidecar against its series folder
(docs/specs/standalone-ids.md). Schema only, nullable, no data change; rows
queued before it keep the path-only check.

Revision ID: sa3_automation_queue_series_key
Revises: sa2_standalone_legacy_claims
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "sa3_automation_queue_series_key"
down_revision = "sa2_standalone_legacy_claims"
branch_labels = None
depends_on = None

_TABLE = "subtitle_automation_queue"
_COLUMN = "series_key"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return False
    return any(c["name"] == _COLUMN for c in inspector.get_columns(_TABLE))


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE) and not _has_column():
        with op.batch_alter_table(_TABLE) as batch:
            batch.add_column(sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column():
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(_COLUMN)
