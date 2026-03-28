"""Add index on subtitle_downloads.downloaded_at."""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b4c5d6e7f8a9"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_subtitle_downloads_downloaded_at "
        "ON subtitle_downloads (downloaded_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_subtitle_downloads_downloaded_at")
