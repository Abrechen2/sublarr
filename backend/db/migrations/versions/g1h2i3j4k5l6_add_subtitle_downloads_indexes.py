"""add performance indexes to subtitle_downloads

Revision ID: g1h2i3j4k5l6
Revises: f7a8b9c0d1e2
Create Date: 2026-04-13

Note: made idempotent after the initial ship. SQLAlchemy `create_all()`
on a fresh DB already creates `idx_subtitle_downloads_downloaded_at`
from the model definition, which made the plain `op.create_index` raise
DuplicateTable on every startup in environments where the schema came
from `create_all()` instead of a clean Alembic upgrade. The non-fatal
wrapper in app.py swallowed the error but left Alembic stuck one revision
behind the real head, blocking every later migration indefinitely in
prod (observed: merge_hi_pref_forced_scoring was current for weeks).

Raw `CREATE INDEX IF NOT EXISTS` is supported by both PostgreSQL and
SQLite and keeps the logical intent (ensure these indexes exist) while
tolerating a pre-existing state.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "g1h2i3j4k5l6"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_subtitle_downloads_downloaded_at "
        "ON subtitle_downloads (downloaded_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_subtitle_downloads_file_path_dl "
        "ON subtitle_downloads (file_path)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_subtitle_downloads_file_path_dl")
    op.execute("DROP INDEX IF EXISTS idx_subtitle_downloads_downloaded_at")
