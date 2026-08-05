"""add foreign_track_scan

Per-file scan state for the batched foreign-track sweep: verdict cache plus
worklist, so a sweep can be bounded per tick and resumed after a restart.

Revision ID: c1f2a3b4d5e6
Revises: a7d3c9e1f5b2
Create Date: 2026-08-05

"""

import sqlalchemy as sa
from alembic import op

revision = "c1f2a3b4d5e6"
down_revision = "a7d3c9e1f5b2"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    """Fresh installs build the schema from the models via create_all(), so
    the table can already exist when this runs."""
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade():
    if _has_table("foreign_track_scan"):
        return
    op.create_table(
        "foreign_track_scan",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("mtime", sa.Float(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("foreign_langs", sa.Text(), nullable=True),
        sa.Column("track_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("probed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_class", sa.String(16), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "idx_foreign_track_scan_state_generation", "foreign_track_scan", ["state", "generation"]
    )
    op.create_index(
        "idx_foreign_track_scan_state_attempts", "foreign_track_scan", ["state", "attempts"]
    )


def downgrade():
    if not _has_table("foreign_track_scan"):
        return
    op.drop_index("idx_foreign_track_scan_state_attempts", table_name="foreign_track_scan")
    op.drop_index("idx_foreign_track_scan_state_generation", table_name="foreign_track_scan")
    op.drop_table("foreign_track_scan")
