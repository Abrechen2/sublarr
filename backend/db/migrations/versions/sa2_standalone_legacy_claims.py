"""Standalone legacy claims: titles whose pre-1.18 rows are no longer read.

Pre-1.18 standalone rows stay under their positive key and are read from
there until the title's first write (docs/specs/standalone-ids.md). This
table records the titles that have taken over their rows under the owner key.
Schema only, no data change; untracked databases get it from ``create_all()``.

Revision ID: sa2_standalone_legacy_claims
Revises: sa1_standalone_episodes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "sa2_standalone_legacy_claims"
down_revision = "sa1_standalone_episodes"
branch_labels = None
depends_on = None

_TABLE = "standalone_legacy_claims"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("kind", sa.String(10), primary_key=True),
        sa.Column("standalone_id", sa.Integer(), primary_key=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        op.drop_table(_TABLE)
