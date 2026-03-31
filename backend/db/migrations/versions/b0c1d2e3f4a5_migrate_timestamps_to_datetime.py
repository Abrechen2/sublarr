"""Migrate all timestamp columns from ISO string to SQLAlchemy DateTime format

Revision ID: b0c1d2e3f4a5
Revises: a1b2c3d4e5f6, a2b3c4d5e6f7, a9b8c7d6e5f4, b1c2d3e4f5a6, c3d4e5f6a7b8, d2e3f4a5b6c7, d4e5f6a7b8c9, e3f4a5b6c7d8
Create Date: 2026-03-31

BREAKING CHANGE: Converts "YYYY-MM-DDTHH:MM:SS+00:00" → "YYYY-MM-DD HH:MM:SS[.ffffff]".
Empty string timestamps become NULL. Required for SQLAlchemy DateTime(timezone=True) support.
"""

from alembic import op

revision = "b0c1d2e3f4a5"
down_revision = (
    "a1b2c3d4e5f6",
    "a2b3c4d5e6f7",
    "a9b8c7d6e5f4",
    "b1c2d3e4f5a6",
    "c3d4e5f6a7b8",
    "d2e3f4a5b6c7",
    "d4e5f6a7b8c9",
    "e3f4a5b6c7d8",
)
branch_labels = None
depends_on = None


def _reformat(table: str, col: str, nullable: bool = True) -> None:
    op.execute(
        f"UPDATE {table} SET {col} = REPLACE(REPLACE({col}, 'T', ' '), '+00:00', '') "
        f"WHERE {col} IS NOT NULL AND {col} != ''"
    )
    if nullable:
        op.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} = ''")


def upgrade() -> None:
    _reformat("jobs", "created_at", nullable=False)
    _reformat("jobs", "completed_at", nullable=True)
    _reformat("config_entries", "updated_at", nullable=False)
    _reformat("wanted_items", "last_search_at", nullable=True)
    _reformat("wanted_items", "added_at", nullable=False)
    _reformat("wanted_items", "updated_at", nullable=False)
    _reformat("wanted_items", "retry_after", nullable=True)
    _reformat("upgrade_history", "upgraded_at", nullable=False)
    _reformat("language_profiles", "created_at", nullable=False)
    _reformat("language_profiles", "updated_at", nullable=False)
    _reformat("ffprobe_cache", "cached_at", nullable=False)
    _reformat("chapter_cache", "cached_at", nullable=False)
    _reformat("blacklist_entries", "added_at", nullable=False)
    _reformat("filter_presets", "created_at", nullable=False)
    _reformat("filter_presets", "updated_at", nullable=False)
    _reformat("anidb_absolute_mappings", "updated_at", nullable=False)
    _reformat("series_settings", "updated_at", nullable=False)
    _reformat("fansub_preferences", "updated_at", nullable=False)
    _reformat("subtitle_hashes", "last_scanned", nullable=False)
    _reformat("cleanup_rules", "last_run_at", nullable=True)
    _reformat("cleanup_rules", "created_at", nullable=False)
    _reformat("cleanup_rules", "updated_at", nullable=False)
    _reformat("cleanup_history", "performed_at", nullable=False)
    _reformat("hook_configs", "last_triggered_at", nullable=True)
    _reformat("hook_configs", "created_at", nullable=False)
    _reformat("hook_configs", "updated_at", nullable=False)
    _reformat("webhook_configs", "last_triggered_at", nullable=True)
    _reformat("webhook_configs", "created_at", nullable=False)
    _reformat("webhook_configs", "updated_at", nullable=False)
    _reformat("hook_log", "triggered_at", nullable=False)
    _reformat("notification_templates", "created_at", nullable=False)
    _reformat("notification_templates", "updated_at", nullable=False)
    _reformat("notification_history", "sent_at", nullable=False)
    _reformat("quiet_hours_config", "created_at", nullable=False)
    _reformat("quiet_hours_config", "updated_at", nullable=False)
    _reformat("provider_cache", "cached_at", nullable=False)
    _reformat("provider_cache", "expires_at", nullable=False)
    _reformat("subtitle_downloads", "downloaded_at", nullable=False)
    _reformat("provider_stats", "last_success_at", nullable=True)
    _reformat("provider_stats", "last_failure_at", nullable=True)
    _reformat("provider_stats", "updated_at", nullable=False)
    _reformat("provider_stats", "disabled_until", nullable=True)
    _reformat("provider_score_modifiers", "updated_at", nullable=False)
    _reformat("scoring_weights", "updated_at", nullable=False)
    _reformat("watched_folders", "last_scan_at", nullable=True)
    _reformat("watched_folders", "created_at", nullable=False)
    _reformat("watched_folders", "updated_at", nullable=False)
    _reformat("standalone_series", "created_at", nullable=False)
    _reformat("standalone_series", "updated_at", nullable=False)
    _reformat("standalone_movies", "created_at", nullable=False)
    _reformat("standalone_movies", "updated_at", nullable=False)
    _reformat("metadata_cache", "cached_at", nullable=False)
    _reformat("metadata_cache", "expires_at", nullable=False)
    _reformat("anidb_mappings", "created_at", nullable=True)
    _reformat("anidb_mappings", "last_used", nullable=True)
    _reformat("translation_config_history", "first_used_at", nullable=False)
    _reformat("translation_config_history", "last_used_at", nullable=False)
    _reformat("glossary_entries", "created_at", nullable=False)
    _reformat("glossary_entries", "updated_at", nullable=False)
    _reformat("prompt_presets", "created_at", nullable=False)
    _reformat("prompt_presets", "updated_at", nullable=False)
    _reformat("translation_backend_stats", "last_success_at", nullable=True)
    _reformat("translation_backend_stats", "last_failure_at", nullable=True)
    _reformat("translation_backend_stats", "updated_at", nullable=False)
    _reformat("whisper_jobs", "created_at", nullable=False)
    _reformat("whisper_jobs", "started_at", nullable=True)
    _reformat("whisper_jobs", "completed_at", nullable=True)
    _reformat("translation_memory", "created_at", nullable=False)
    _reformat("installed_plugins", "installed_at", nullable=False)
    _reformat("marketplace_cache", "last_fetched", nullable=False)


def downgrade() -> None:
    raise NotImplementedError(
        "Timestamp migration downgrade is not supported. Restore from backup."
    )
