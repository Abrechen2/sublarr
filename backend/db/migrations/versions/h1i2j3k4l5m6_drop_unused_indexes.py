"""drop unused indexes identified by pg_stat_user_indexes

Revision ID: h1i2j3k4l5m6
Revises: merge_downloads_idx
Create Date: 2026-04-14

After ~2 weeks of prod runtime, pg_stat_user_indexes flagged the
following indexes as 0-scan on hot tables:

  - activity_log.idx_activity_log_event_type      (no reader queries)
  - activity_log.idx_activity_log_created_at      (no reader queries)
  - wanted_items.idx_wanted_sonarr_series         (only IS NOT NULL queries)
  - wanted_items.idx_wanted_radarr_movie          (no reader queries)
  - subtitle_downloads.idx_subtitle_downloads_path (planner prefers seq
                                                   scan at current row
                                                   count)
  - subtitle_downloads.idx_subtitle_downloads_file_path_dl
                                                  (same — second file_path
                                                   index was created by
                                                   g1h2i3j4k5l6; audit
                                                   found no query that
                                                   benefits)
  - subtitle_hashes.idx_subtitle_hashes_file_path  (100% duplicate of the
                                                   UNIQUE constraint
                                                   subtitle_hashes_file_path_key)

Indexes with 0 scans that are kept: trigram GIN indexes on search_*
tables (reserved for the global search feature), and
idx_wanted_sonarr_episode (consumed by an IN-list query in
routes/library/series.py).

Implementation note: we use plain `DROP INDEX IF EXISTS` inside the
default Alembic transaction. All dropped indexes are under 1 MB, so the
brief AccessExclusiveLock is measured in milliseconds. The earlier
design used `DROP INDEX CONCURRENTLY` inside an `autocommit_block`, but
that escape-hatch collides with Postgres's transactional DDL assumption
that Alembic normally uses and caused the migration to roll back
silently. `IF EXISTS` keeps it idempotent.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "h1i2j3k4l5m6"
down_revision = "merge_downloads_idx"
branch_labels = None
depends_on = None


INDEXES_TO_DROP = [
    "idx_activity_log_event_type",
    "idx_activity_log_created_at",
    "idx_wanted_sonarr_series",
    "idx_wanted_radarr_movie",
    "idx_subtitle_downloads_path",
    "idx_subtitle_downloads_file_path_dl",
    "idx_subtitle_hashes_file_path",
]


# (table, index, cols) triples used only for downgrade() when an operator
# deliberately rolls back this revision.
INDEXES_TO_RECREATE = [
    ("activity_log", "idx_activity_log_event_type", ["event_type"]),
    ("activity_log", "idx_activity_log_created_at", ["created_at"]),
    ("wanted_items", "idx_wanted_sonarr_series", ["sonarr_series_id"]),
    ("wanted_items", "idx_wanted_radarr_movie", ["radarr_movie_id"]),
    ("subtitle_downloads", "idx_subtitle_downloads_path", ["file_path"]),
    ("subtitle_downloads", "idx_subtitle_downloads_file_path_dl", ["file_path"]),
    ("subtitle_hashes", "idx_subtitle_hashes_file_path", ["file_path"]),
]


def upgrade() -> None:
    for index in INDEXES_TO_DROP:
        op.execute(f"DROP INDEX IF EXISTS {index}")


def downgrade() -> None:
    for table, index, cols in INDEXES_TO_RECREATE:
        col_list = ", ".join(cols)
        op.execute(f"CREATE INDEX IF NOT EXISTS {index} ON {table} ({col_list})")
