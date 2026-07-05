"""add_wanted_mt_pin_pending

Revision ID: 3c4b1a2d5e6f
Revises: b7e2f4a1c8d3
Create Date: 2026-07-05 14:00:00.000000+00:00

Adds the provisional-MT re-seek pinning + pending-original signals
(feature #8b Phase 2 Task 2) to ``wanted_items``:

- ``mt_pinned`` — user-edited/confirmed MT that must never be auto-replaced
  or re-searched by the ``mt_reseek`` job.
- ``mt_pending_original`` — JSON payload recording a qualifying original
  found during a ``mt_on_original_found="notify"`` pass, for Task 3's
  approve/reject API.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3c4b1a2d5e6f"
down_revision = "b7e2f4a1c8d3"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent: skip columns that already exist so this migration is safe to
    # re-run and coexists with a create_all()-seeded schema (test fixtures do
    # create_all() then upgrade head).
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("wanted_items")}
    with op.batch_alter_table("wanted_items") as batch_op:
        if "mt_pinned" not in existing:
            # Nullable (matches the model — see db/models/core.py comment):
            # the raw-SQL upsert path does not enumerate this column, so a
            # NOT NULL constraint would break every plain upsert insert.
            batch_op.add_column(sa.Column("mt_pinned", sa.Integer(), nullable=True))
        if "mt_pending_original" not in existing:
            batch_op.add_column(sa.Column("mt_pending_original", sa.Text(), nullable=True))


def downgrade():
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("wanted_items")}
    with op.batch_alter_table("wanted_items") as batch_op:
        if "mt_pending_original" in existing:
            batch_op.drop_column("mt_pending_original")
        if "mt_pinned" in existing:
            batch_op.drop_column("mt_pinned")
