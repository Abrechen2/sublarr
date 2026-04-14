"""drop unused indexes identified by pg_stat_user_indexes

Revision ID: h1i2j3k4l5m6
Revises: merge_downloads_idx
Create Date: 2026-04-14

After ~2 weeks of prod runtime, pg_stat_user_indexes flagged the following
indexes as 0-scan on hot tables:

  - activity_log.idx_activity_log_event_type      (no reader queries)
  - activity_log.idx_activity_log_created_at      (no reader queries)
  - wanted_items.idx_wanted_sonarr_series         (only IS NOT NULL queries)
  - wanted_items.idx_wanted_radarr_movie          (no reader queries)
  - subtitle_downloads.idx_subtitle_downloads_path (planner prefers seq scan
                                                   at current row count)
  - subtitle_hashes.idx_subtitle_hashes_file_path  (100% duplicate of the
                                                   UNIQUE constraint
                                                   subtitle_hashes_file_path_key)

Indexes that had 0 scans but are kept are documented in the audit —
trigram GIN indexes on search_* tables are kept for the global search
feature, and idx_wanted_sonarr_episode is kept because routes/library/
series.py does an IN-list query on that column.

Uses DROP INDEX CONCURRENTLY on PostgreSQL so live writes are not blocked
by an AccessExclusiveLock. Falls back to plain DROP INDEX on SQLite.
"""

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "h1i2j3k4l5m6"
down_revision = "merge_downloads_idx"
branch_labels = None
depends_on = None


INDEXES_TO_DROP = [
    ("activity_log", "idx_activity_log_event_type"),
    ("activity_log", "idx_activity_log_created_at"),
    ("wanted_items", "idx_wanted_sonarr_series"),
    ("wanted_items", "idx_wanted_radarr_movie"),
    ("subtitle_downloads", "idx_subtitle_downloads_path"),
    # The companion migration g1h2i3j4k5l6 also creates a second file_path
    # index under a different name (idx_subtitle_downloads_file_path_dl). The
    # audit found no query that benefits from it, so drop that one too to
    # keep the table index-light.
    ("subtitle_downloads", "idx_subtitle_downloads_file_path_dl"),
    ("subtitle_hashes", "idx_subtitle_hashes_file_path"),
]


def _is_postgresql(bind) -> bool:
    return bind.dialect.name == "postgresql"


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    """Return True when the named index exists on the given table."""
    inspector = inspect(bind)
    try:
        indexes = inspector.get_indexes(table_name)
    except Exception:
        return False
    if any(ix.get("name") == index_name for ix in indexes):
        return True
    # UNIQUE constraints are reported separately on some dialects.
    try:
        uniques = inspector.get_unique_constraints(table_name)
    except Exception:
        uniques = []
    return any(u.get("name") == index_name for u in uniques)


def upgrade() -> None:
    bind = op.get_bind()
    postgres = _is_postgresql(bind)

    # CONCURRENTLY cannot run inside a transaction — commit the migration
    # transaction first on Postgres, execute each drop outside the tx, then
    # resume the migration bookkeeping.
    if postgres:
        with op.get_context().autocommit_block():
            for table, index in INDEXES_TO_DROP:
                if _index_exists(bind, table, index):
                    op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index}")
    else:
        for table, index in INDEXES_TO_DROP:
            if _index_exists(bind, table, index):
                op.drop_index(index, table_name=table)


def downgrade() -> None:
    """Recreate the dropped indexes. Only runs if an operator explicitly rolls back.

    Recreation mirrors the SQLAlchemy model definitions that existed before
    this migration — plain btree indexes on the respective columns.
    """
    bind = op.get_bind()
    postgres = _is_postgresql(bind)

    recreate = [
        ("activity_log", "idx_activity_log_event_type", ["event_type"]),
        ("activity_log", "idx_activity_log_created_at", ["created_at"]),
        ("wanted_items", "idx_wanted_sonarr_series", ["sonarr_series_id"]),
        ("wanted_items", "idx_wanted_radarr_movie", ["radarr_movie_id"]),
        ("subtitle_downloads", "idx_subtitle_downloads_path", ["file_path"]),
        ("subtitle_hashes", "idx_subtitle_hashes_file_path", ["file_path"]),
    ]

    if postgres:
        with op.get_context().autocommit_block():
            for table, index, cols in recreate:
                col_list = ", ".join(cols)
                op.execute(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} ON {table} ({col_list})"
                )
    else:
        for table, index, cols in recreate:
            op.create_index(index, table, cols)
