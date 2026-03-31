"""Fix DateTime column types for PostgreSQL

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a5
Create Date: 2026-03-31

b0c1d2e3f4a5 reformatted ISO strings in all timestamp columns but only changed
column types on SQLite (which uses dynamic typing). On PostgreSQL the columns
remained as TEXT, causing "operator does not exist: text > timestamptz" errors
at runtime.

This migration runs ALTER COLUMN … TYPE TIMESTAMP WITH TIME ZONE on PostgreSQL
for every timestamp column.  It is a no-op on SQLite.
"""

from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b0c1d2e3f4a5"
branch_labels = None
depends_on = None

# (table, column, nullable) — must match b0c1d2e3f4a5 exactly
_COLUMNS: list[tuple[str, str, bool]] = [
    ("jobs", "created_at", False),
    ("jobs", "completed_at", True),
    ("config_entries", "updated_at", False),
    ("wanted_items", "last_search_at", True),
    ("wanted_items", "added_at", False),
    ("wanted_items", "updated_at", False),
    ("wanted_items", "retry_after", True),
    ("upgrade_history", "upgraded_at", False),
    ("language_profiles", "created_at", False),
    ("language_profiles", "updated_at", False),
    ("ffprobe_cache", "cached_at", False),
    ("chapter_cache", "cached_at", False),
    ("blacklist_entries", "added_at", False),
    ("filter_presets", "created_at", False),
    ("filter_presets", "updated_at", False),
    ("anidb_absolute_mappings", "updated_at", False),
    ("series_settings", "updated_at", False),
    ("fansub_preferences", "updated_at", False),
    ("subtitle_hashes", "last_scanned", False),
    ("cleanup_rules", "last_run_at", True),
    ("cleanup_rules", "created_at", False),
    ("cleanup_rules", "updated_at", False),
    ("cleanup_history", "performed_at", False),
    ("hook_configs", "last_triggered_at", True),
    ("hook_configs", "created_at", False),
    ("hook_configs", "updated_at", False),
    ("webhook_configs", "last_triggered_at", True),
    ("webhook_configs", "created_at", False),
    ("webhook_configs", "updated_at", False),
    ("hook_log", "triggered_at", False),
    ("notification_templates", "created_at", False),
    ("notification_templates", "updated_at", False),
    ("notification_history", "sent_at", False),
    ("quiet_hours_config", "created_at", False),
    ("quiet_hours_config", "updated_at", False),
    ("provider_cache", "cached_at", False),
    ("provider_cache", "expires_at", False),
    ("subtitle_downloads", "downloaded_at", False),
    ("provider_stats", "last_success_at", True),
    ("provider_stats", "last_failure_at", True),
    ("provider_stats", "updated_at", False),
    ("provider_stats", "disabled_until", True),
    ("provider_score_modifiers", "updated_at", False),
    ("scoring_weights", "updated_at", False),
    ("watched_folders", "last_scan_at", True),
    ("watched_folders", "created_at", False),
    ("watched_folders", "updated_at", False),
    ("standalone_series", "created_at", False),
    ("standalone_series", "updated_at", False),
    ("standalone_movies", "created_at", False),
    ("standalone_movies", "updated_at", False),
    ("metadata_cache", "cached_at", False),
    ("metadata_cache", "expires_at", False),
    ("anidb_mappings", "created_at", True),
    ("anidb_mappings", "last_used", True),
    ("translation_config_history", "first_used_at", False),
    ("translation_config_history", "last_used_at", False),
    ("glossary_entries", "created_at", False),
    ("glossary_entries", "updated_at", False),
    ("prompt_presets", "created_at", False),
    ("prompt_presets", "updated_at", False),
    ("translation_backend_stats", "last_success_at", True),
    ("translation_backend_stats", "last_failure_at", True),
    ("translation_backend_stats", "updated_at", False),
    ("whisper_jobs", "created_at", False),
    ("whisper_jobs", "started_at", True),
    ("whisper_jobs", "completed_at", True),
    ("translation_memory", "created_at", False),
    ("installed_plugins", "installed_at", False),
    ("marketplace_cache", "last_fetched", False),
]

_EPOCH = "1970-01-01 00:00:00"


def _pg_alter(table: str, col: str, nullable: bool) -> None:
    # For NOT NULL columns replace any remaining empty string with epoch so the
    # cast succeeds.  (b0c1d2e3f4a5 skipped the NULL-out step for nullable=False.)
    if not nullable:
        op.execute(
            f"UPDATE {table} SET {col} = '{_EPOCH}' WHERE {col} IS NOT NULL AND TRIM({col}) = ''"
        )
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE "
            f"USING {col}::timestamp AT TIME ZONE 'UTC'"
        )
    else:
        # Nullable columns: convert empty strings to NULL, then cast.
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} IS NOT NULL AND TRIM({col}) = ''")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMP WITH TIME ZONE "
            f"USING CASE WHEN {col} IS NULL THEN NULL "
            f"ELSE {col}::timestamp AT TIME ZONE 'UTC' END"
        )


def upgrade() -> None:
    dialect = op.get_context().dialect.name
    if dialect != "postgresql":
        return  # SQLite uses dynamic typing — no ALTER needed

    for table, col, nullable in _COLUMNS:
        _pg_alter(table, col, nullable)


def downgrade() -> None:
    raise NotImplementedError(
        "DateTime type migration downgrade is not supported. Restore from backup."
    )
