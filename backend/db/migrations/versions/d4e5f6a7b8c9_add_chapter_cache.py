"""Add chapter_cache table for per-video chapter list caching.

Revision ID: d4e5f6a7b8c9
Revises: e4f5a6b7c8d9
Create Date: 2026-03-13
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chapter_cache",
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("mtime", sa.Float(), nullable=False),
        sa.Column("chapters_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("cached_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("file_path"),
    )


def downgrade():
    op.drop_table("chapter_cache")
