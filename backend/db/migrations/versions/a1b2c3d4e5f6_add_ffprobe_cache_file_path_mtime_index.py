"""Add composite index (file_path, mtime) on ffprobe_cache for lookup performance.

Revision ID: a1b2c3d4e5f6
Revises: c7d8e9f0a1b2
Create Date: 2026-02-21

get_ffprobe_cache() looks up by file_path and mtime; a composite index
speeds up these lookups compared to the existing mtime-only index.
"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_ffprobe_cache_file_path_mtime",
        "ffprobe_cache",
        ["file_path", "mtime"],
    )


def downgrade():
    op.drop_index(
        "idx_ffprobe_cache_file_path_mtime",
        table_name="ffprobe_cache",
    )
