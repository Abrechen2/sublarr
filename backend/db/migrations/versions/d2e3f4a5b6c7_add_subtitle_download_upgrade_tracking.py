"""Add upgraded_from_id column to subtitle_downloads for upgrade chain tracking."""

from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subtitle_downloads ADD COLUMN upgraded_from_id INTEGER"
    )


def downgrade() -> None:
    # SQLite: recreate without the column
    op.execute(
        "CREATE TABLE subtitle_downloads_backup AS "
        "SELECT id, provider_name, subtitle_id, language, format, file_path, "
        "score, subtitle_type, source, downloaded_at FROM subtitle_downloads"
    )
    op.execute("DROP TABLE subtitle_downloads")
    op.execute("ALTER TABLE subtitle_downloads_backup RENAME TO subtitle_downloads")
