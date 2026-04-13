"""add performance indexes to subtitle_downloads

Revision ID: g1h2i3j4k5l6
Revises: f7a8b9c0d1e2
Create Date: 2026-04-13

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "g1h2i3j4k5l6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_subtitle_downloads_downloaded_at",
        "subtitle_downloads",
        ["downloaded_at"],
    )
    op.create_index(
        "idx_subtitle_downloads_file_path_dl",
        "subtitle_downloads",
        ["file_path"],
    )


def downgrade():
    op.drop_index("idx_subtitle_downloads_file_path_dl", table_name="subtitle_downloads")
    op.drop_index("idx_subtitle_downloads_downloaded_at", table_name="subtitle_downloads")
