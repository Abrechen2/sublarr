"""add subtitle_repairs — record of subtitles restored after the HI-removal data loss

Repair rewrites a damaged sidecar back to its provider original, so afterwards it
no longer matches the pristine hash in subtitle_hashes — which is the very signal
the scanner uses to detect damage. Without this table every repaired file would
look damaged again on the next scan and be re-downloaded forever, burning the
provider's daily quota. Storing the post-repair hash also lets a hand edit made
*after* a repair be told apart from damage.

Revision ID: e7a1b2c3d4f5
Revises: 3c4b1a2d5e6f
Create Date: 2026-07-11
"""

import sqlalchemy as sa
from alembic import op

revision = "e7a1b2c3d4f5"
down_revision = "3c4b1a2d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subtitle_repairs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("original_hash", sa.String(length=64), nullable=False),
        sa.Column("repaired_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=50), nullable=True),
        sa.Column("subtitle_id", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="repaired"),
        sa.Column("repaired_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index(
        "idx_subtitle_repairs_status", "subtitle_repairs", ["status"], if_not_exists=True
    )


def downgrade() -> None:
    op.drop_index("idx_subtitle_repairs_status", table_name="subtitle_repairs")
    op.drop_table("subtitle_repairs")
