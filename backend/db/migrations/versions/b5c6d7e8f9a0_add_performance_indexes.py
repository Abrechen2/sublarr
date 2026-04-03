"""Add performance indexes for wanted_items and subtitle_downloads

Revision ID: b5c6d7e8f9a0
Revises: 9852305585cd, a1b2c3d4e5f6, a2b3c4d5e6f7, a9b8c7d6e5f4, b1c2d3e4f5a6,
         c3d4e5f6a7b8, d2e3f4a5b6c7, d4e5f6a7b8c9, d5e6f7a8b9c0, e3f4a5b6c7d8
Create Date: 2026-04-03

Merges all current branch heads and adds composite index on
wanted_items(status, retry_after) for the scan-loop candidate filter,
and language index on subtitle_downloads for provider history lookups.
"""

from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = (
    "9852305585cd",
    "a1b2c3d4e5f6",
    "a2b3c4d5e6f7",
    "a9b8c7d6e5f4",
    "b1c2d3e4f5a6",
    "c3d4e5f6a7b8",
    "d2e3f4a5b6c7",
    "d4e5f6a7b8c9",
    "d5e6f7a8b9c0",
    "e3f4a5b6c7d8",
)
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.create_index(
            "idx_wanted_status_retry_after",
            ["status", "retry_after"],
        )
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.create_index(
            "idx_subtitle_downloads_language",
            ["language"],
        )


def downgrade():
    with op.batch_alter_table("wanted_items") as batch_op:
        batch_op.drop_index("idx_wanted_status_retry_after")
    with op.batch_alter_table("subtitle_downloads") as batch_op:
        batch_op.drop_index("idx_subtitle_downloads_language")
