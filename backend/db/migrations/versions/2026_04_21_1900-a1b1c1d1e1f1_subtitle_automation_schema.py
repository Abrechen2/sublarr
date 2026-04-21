"""0.71.0 subtitle automation — SeriesSettings column + queue table

Revision ID: a1b1c1d1e1f1
Revises: 230eaa9647a8
Create Date: 2026-04-21

Adds:
- `series_settings.cleanup_foreign_tracks` — nullable Boolean. NULL = inherit
  global `cleanup_foreign_tracks_default`. True/False = explicit override.
- `subtitle_automation_queue` — persistent drain queue for auto-extract of
  embedded subtitles. One row per wanted_item (unique constraint); state
  machine pending → running → done | failed; composite index on
  (state, next_retry_at) for drain lookups.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1b1c1d1e1f1"
down_revision = "230eaa9647a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Per-series override for foreign-track cleanup.
    with op.batch_alter_table("series_settings") as batch_op:
        # Defensive: some deployments may already carry the column (e.g. created
        # by create_all() prior to the migration running). IF NOT EXISTS via
        # raw DDL is preferred on PG.
        bind = op.get_bind()
        dialect = bind.dialect.name if bind is not None else ""
        if dialect == "postgresql":
            op.execute(
                "ALTER TABLE series_settings "
                "ADD COLUMN IF NOT EXISTS cleanup_foreign_tracks BOOLEAN"
            )
        else:
            batch_op.add_column(
                sa.Column("cleanup_foreign_tracks", sa.Boolean(), nullable=True)
            )

    # 2) Persistent drain queue for auto-extract.
    op.create_table(
        "subtitle_automation_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wanted_item_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("target_language", sa.String(length=8), nullable=False),
        sa.Column(
            "state",
            sa.String(length=10),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_subtitle_automation_queue_drain",
        "subtitle_automation_queue",
        ["state", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_subtitle_automation_queue_drain",
        table_name="subtitle_automation_queue",
    )
    op.drop_table("subtitle_automation_queue")
    with op.batch_alter_table("series_settings") as batch_op:
        batch_op.drop_column("cleanup_foreign_tracks")
