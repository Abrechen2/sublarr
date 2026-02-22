"""Repository pattern for Sublarr database operations using SQLAlchemy ORM.

Each repository class provides methods that mirror the existing db/ module
functions but use SQLAlchemy ORM sessions instead of raw sqlite3 queries.

Module-level convenience functions delegate to repository instances, providing
a drop-in replacement API for the existing db/ modules.
"""

from db.repositories.base import BaseRepository
from db.repositories.config import ConfigRepository
from db.repositories.blacklist import BlacklistRepository
from db.repositories.cache import CacheRepository
from db.repositories.plugins import PluginRepository
from db.repositories.jobs import JobRepository
from db.repositories.wanted import WantedRepository
from db.repositories.profiles import ProfileRepository
from db.repositories.scoring import ScoringRepository
from db.repositories.library import LibraryRepository
from db.repositories.providers import ProviderRepository
from db.repositories.hooks import HookRepository
from db.repositories.standalone import StandaloneRepository
from db.repositories.whisper import WhisperRepository
from db.repositories.translation import TranslationRepository
from db.repositories.quality import QualityRepository
from db.repositories.search import SearchRepository
from db.repositories.presets import FilterPresetsRepository
from db.repositories.notifications import NotificationRepository
from db.repositories.cleanup import CleanupRepository
from db.repositories.anidb import AnidbRepository

__all__ = [
    # Base
    "BaseRepository",
    # Repositories (Plan 10-02: simple repos)
    "ConfigRepository",
    "BlacklistRepository",
    "CacheRepository",
    "PluginRepository",
    # Repositories (Plan 10-03: complex repos)
    "JobRepository",
    "WantedRepository",
    "ProfileRepository",
    "ProviderRepository",
    "HookRepository",
    "StandaloneRepository",
    # Repositories (Plan 10-02: additional domain repos)
    "ScoringRepository",
    "LibraryRepository",
    "WhisperRepository",
    "TranslationRepository",
    "QualityRepository",
    "SearchRepository",
    "FilterPresetsRepository",
    "NotificationRepository",
    "AnidbRepository",
    # AniDB convenience functions
    "get_anidb_absolute",
    "upsert_anidb_mapping",
    "list_anidb_mappings",
    "clear_anidb_mappings_for_tvdb",
    "get_series_absolute_order",
    "set_series_absolute_order",
    # Notification convenience functions
    "create_notification_template",
    "get_notification_template",
    "get_notification_templates",
    "update_notification_template",
    "delete_notification_template",
    "find_template_for_event",
    "log_notification",
    "get_notification_history",
    "get_notification",
    "clear_notification_history",
    "create_quiet_hours",
    "get_quiet_hours_configs",
    "update_quiet_hours",
    "delete_quiet_hours",
    "is_quiet_hours",
    # Config convenience functions
    "save_config_entry",
    "get_config_entry",
    "get_all_config_entries",
    # Blacklist convenience functions
    "add_blacklist_entry",
    "remove_blacklist_entry",
    "clear_blacklist",
    "is_blacklisted",
    "get_blacklist_entries",
    "get_blacklist_count",
    # Cache convenience functions
    "get_ffprobe_cache",
    "set_ffprobe_cache",
    "clear_ffprobe_cache",
    "get_episode_history",
    "get_anidb_mapping",
    "save_anidb_mapping",
    "cleanup_old_anidb_mappings",
    "get_anidb_mapping_stats",
    # Plugin convenience functions
    "get_plugin_config",
    "set_plugin_config",
    "get_all_plugin_configs",
    "delete_plugin_config",
    # Scoring convenience functions
    "get_scoring_weights",
    "set_scoring_weights",
    "get_all_scoring_weights",
    "reset_scoring_weights",
    "get_provider_modifier",
    "get_all_provider_modifiers",
    "set_provider_modifier",
    "delete_provider_modifier",
    # Library convenience functions
    "get_download_history",
    "get_download_stats",
    "record_upgrade",
    "get_upgrade_history",
    "get_upgrade_stats",
    # Whisper convenience functions
    "create_whisper_job",
    "update_whisper_job",
    "get_whisper_job",
    "get_whisper_jobs",
    "delete_whisper_job",
    "get_whisper_stats",
    # Translation convenience functions
    "record_translation_config",
    "get_translation_config_history",
    "add_glossary_entry",
    "get_glossary_entries",
    "get_glossary_for_series",
    "get_glossary_entry",
    "update_glossary_entry",
    "delete_glossary_entry",
    "delete_glossary_entries_for_series",
    "search_glossary_terms",
    "add_prompt_preset",
    "get_prompt_presets",
    "get_prompt_preset",
    "get_default_prompt_preset",
    "update_prompt_preset",
    "delete_prompt_preset",
    "record_backend_success",
    "record_backend_failure",
    "get_backend_stats",
    "get_backend_stat",
    "reset_backend_stats",
    # Quality convenience functions
    "save_health_result",
    "get_health_result",
    "get_health_results_for_series",
    "get_quality_trends",
    "delete_health_results",
    # Cleanup
    "CleanupRepository",
]


# ---- Config convenience functions ------------------------------------------------

def save_config_entry(key: str, value: str):
    """Save a config entry to the database."""
    return ConfigRepository().save_config_entry(key, value)


def get_config_entry(key: str):
    """Get a config entry from the database."""
    return ConfigRepository().get_config_entry(key)


def get_all_config_entries() -> dict:
    """Get all config entries."""
    return ConfigRepository().get_all_config_entries()


# ---- Blacklist convenience functions ---------------------------------------------

def add_blacklist_entry(provider_name: str, subtitle_id: str,
                        language: str = "", file_path: str = "",
                        title: str = "", reason: str = "") -> int:
    """Add a subtitle to the blacklist. Returns the entry ID."""
    return BlacklistRepository().add_blacklist_entry(
        provider_name, subtitle_id, language, file_path, title, reason
    )


def remove_blacklist_entry(entry_id: int) -> bool:
    """Remove a blacklist entry by ID. Returns True if deleted."""
    return BlacklistRepository().remove_blacklist_entry(entry_id)


def clear_blacklist() -> int:
    """Remove all blacklist entries. Returns count deleted."""
    return BlacklistRepository().clear_blacklist()


def is_blacklisted(provider_name: str, subtitle_id: str) -> bool:
    """Check if a subtitle is blacklisted."""
    return BlacklistRepository().is_blacklisted(provider_name, subtitle_id)


def get_blacklist_entries(page: int = 1, per_page: int = 50) -> dict:
    """Get paginated blacklist entries."""
    return BlacklistRepository().get_blacklist_entries(page, per_page)


def get_blacklist_count() -> int:
    """Get total number of blacklisted subtitles."""
    return BlacklistRepository().get_blacklist_count()


# ---- Cache convenience functions -------------------------------------------------

def get_ffprobe_cache(file_path: str, mtime: float):
    """Get cached ffprobe data if file hasn't changed."""
    return CacheRepository().get_ffprobe_cache(file_path, mtime)


def set_ffprobe_cache(file_path: str, mtime: float, probe_data: dict):
    """Cache ffprobe data for a file."""
    return CacheRepository().set_ffprobe_cache(file_path, mtime, probe_data)


def clear_ffprobe_cache(file_path: str = None):
    """Clear ffprobe cache."""
    return CacheRepository().clear_ffprobe_cache(file_path)


def get_episode_history(file_path: str) -> list:
    """Get combined download + job history for a file path."""
    return CacheRepository().get_episode_history(file_path)


def get_anidb_mapping(tvdb_id: int):
    """Get cached AniDB ID for a TVDB ID."""
    return CacheRepository().get_anidb_mapping(tvdb_id)


def save_anidb_mapping(tvdb_id: int, anidb_id: int, series_title: str = ""):
    """Save or update an AniDB mapping in the cache."""
    return CacheRepository().save_anidb_mapping(tvdb_id, anidb_id, series_title)


def cleanup_old_anidb_mappings(days: int = 90) -> int:
    """Remove AniDB mappings older than specified days."""
    return CacheRepository().cleanup_old_anidb_mappings(days)


def get_anidb_mapping_stats() -> dict:
    """Get statistics about AniDB mappings cache."""
    return CacheRepository().get_anidb_mapping_stats()


# ---- Plugin convenience functions ------------------------------------------------

def get_plugin_config(provider_name: str) -> dict:
    """Read all config entries for a plugin provider."""
    return PluginRepository().get_plugin_config(provider_name)


def set_plugin_config(provider_name: str, key: str, value: str) -> None:
    """Write a single config entry for a plugin provider."""
    return PluginRepository().set_plugin_config(provider_name, key, value)


def get_all_plugin_configs() -> dict:
    """Get all plugin config entries grouped by provider name."""
    return PluginRepository().get_all_plugin_configs()


def delete_plugin_config(provider_name: str) -> int:
    """Delete all config entries for a plugin provider."""
    return PluginRepository().delete_plugin_config(provider_name)


# ---- Scoring convenience functions ----------------------------------------------

def get_scoring_weights(score_type: str) -> dict:
    """Get scoring weight overrides for a given type."""
    return ScoringRepository().get_scoring_weights(score_type)


def set_scoring_weights(score_type: str, weights_dict: dict) -> None:
    """Set scoring weight overrides for a given type."""
    return ScoringRepository().set_scoring_weights(score_type, weights_dict)


def get_all_scoring_weights() -> dict:
    """Get all scoring weights with defaults filled in."""
    return ScoringRepository().get_all_scoring_weights()


def reset_scoring_weights(score_type: str = None) -> None:
    """Delete scoring weight overrides."""
    return ScoringRepository().reset_scoring_weights(score_type)


def get_provider_modifier(provider_name: str) -> int:
    """Get the score modifier for a provider."""
    return ScoringRepository().get_provider_modifier(provider_name)


def get_all_provider_modifiers() -> dict:
    """Get all provider score modifiers."""
    return ScoringRepository().get_all_provider_modifiers()


def set_provider_modifier(provider_name: str, modifier: int) -> None:
    """Set or update the score modifier for a provider."""
    return ScoringRepository().set_provider_modifier(provider_name, modifier)


def delete_provider_modifier(provider_name: str) -> None:
    """Delete the score modifier for a provider."""
    return ScoringRepository().delete_provider_modifier(provider_name)


# ---- Library convenience functions ----------------------------------------------

def get_download_history(page: int = 1, per_page: int = 50,
                         provider: str = None, language: str = None,
                         format: str = None,
                         score_min: int = None,
                         score_max: int = None,
                         search: str = None,
                         sort_by: str = "downloaded_at",
                         sort_dir: str = "desc") -> dict:
    """Get paginated download history with optional filters."""
    return LibraryRepository().get_download_history(
        page, per_page, provider, language,
        format=format, score_min=score_min, score_max=score_max,
        search=search, sort_by=sort_by, sort_dir=sort_dir,
    )


def get_download_stats() -> dict:
    """Get aggregated download statistics."""
    return LibraryRepository().get_download_stats()


def record_upgrade(file_path: str, old_format: str, old_score: int,
                   new_format: str, new_score: int,
                   provider_name: str = "", upgrade_reason: str = ""):
    """Record a subtitle upgrade in history."""
    return LibraryRepository().record_upgrade(
        file_path, old_format, old_score, new_format, new_score,
        provider_name, upgrade_reason
    )


def get_upgrade_history(limit: int = 50) -> list:
    """Get recent upgrade history entries."""
    return LibraryRepository().get_upgrade_history(limit)


def get_upgrade_stats() -> dict:
    """Get aggregated upgrade statistics."""
    return LibraryRepository().get_upgrade_stats()


# ---- Whisper convenience functions ----------------------------------------------

def create_whisper_job(job_id: str, file_path: str, language: str = "") -> dict:
    """Create a new whisper job in the database."""
    return WhisperRepository().create_whisper_job(job_id, file_path, language)


def update_whisper_job(job_id: str, **kwargs) -> None:
    """Update a whisper job with arbitrary column values."""
    return WhisperRepository().update_whisper_job(job_id, **kwargs)


def get_whisper_job(job_id: str):
    """Get a whisper job by ID."""
    return WhisperRepository().get_whisper_job(job_id)


def get_whisper_jobs(status: str = None, limit: int = 50) -> list:
    """Get whisper jobs, optionally filtered by status."""
    return WhisperRepository().get_whisper_jobs(status, limit)


def delete_whisper_job(job_id: str) -> bool:
    """Delete a whisper job."""
    return WhisperRepository().delete_whisper_job(job_id)


def get_whisper_stats() -> dict:
    """Get aggregate whisper job statistics."""
    return WhisperRepository().get_whisper_stats()


# ---- Translation convenience functions ------------------------------------------

def record_translation_config(config_hash: str, ollama_model: str,
                               prompt_template: str, target_language: str):
    """Record or update a translation config hash."""
    return TranslationRepository().record_translation_config(
        config_hash, ollama_model, prompt_template, target_language
    )


def get_translation_config_history() -> list:
    """Get translation config history entries."""
    return TranslationRepository().get_translation_config_history()


def add_glossary_entry(series_id: int, source_term: str,
                       target_term: str, notes: str = "") -> int:
    """Add a new glossary entry for a series. Returns the entry ID."""
    return TranslationRepository().add_glossary_entry(
        series_id, source_term, target_term, notes
    )


def get_glossary_entries(series_id: int) -> list:
    """Get all glossary entries for a series."""
    return TranslationRepository().get_glossary_entries(series_id)


def get_glossary_for_series(series_id: int) -> list:
    """Get glossary entries for a series, optimized for translation pipeline."""
    return TranslationRepository().get_glossary_for_series(series_id)


def get_glossary_entry(entry_id: int):
    """Get a single glossary entry by ID."""
    return TranslationRepository().get_glossary_entry(entry_id)


def update_glossary_entry(entry_id: int, source_term: str = None,
                          target_term: str = None, notes: str = None) -> bool:
    """Update a glossary entry. Returns True if updated."""
    return TranslationRepository().update_glossary_entry(
        entry_id, source_term, target_term, notes
    )


def delete_glossary_entry(entry_id: int) -> bool:
    """Delete a glossary entry. Returns True if deleted."""
    return TranslationRepository().delete_glossary_entry(entry_id)


def delete_glossary_entries_for_series(series_id: int) -> int:
    """Delete all glossary entries for a series. Returns count deleted."""
    return TranslationRepository().delete_glossary_entries_for_series(series_id)


def search_glossary_terms(series_id: int, query: str) -> list:
    """Search glossary entries by source or target term."""
    return TranslationRepository().search_glossary_terms(series_id, query)


def add_prompt_preset(name: str, prompt_template: str,
                      is_default: bool = False) -> int:
    """Add a new prompt preset. Returns the preset ID."""
    return TranslationRepository().add_prompt_preset(name, prompt_template, is_default)


def get_prompt_presets() -> list:
    """Get all prompt presets."""
    return TranslationRepository().get_prompt_presets()


def get_prompt_preset(preset_id: int):
    """Get a single prompt preset by ID."""
    return TranslationRepository().get_prompt_preset(preset_id)


def get_default_prompt_preset():
    """Get the default prompt preset."""
    return TranslationRepository().get_default_prompt_preset()


def update_prompt_preset(preset_id: int, name: str = None,
                         prompt_template: str = None,
                         is_default: bool = None) -> bool:
    """Update a prompt preset. Returns True if updated."""
    return TranslationRepository().update_prompt_preset(
        preset_id, name, prompt_template, is_default
    )


def delete_prompt_preset(preset_id: int) -> bool:
    """Delete a prompt preset. Returns True if deleted."""
    return TranslationRepository().delete_prompt_preset(preset_id)


def record_backend_success(backend_name: str, response_time_ms: float,
                           characters_used: int):
    """Record a successful translation for a backend."""
    return TranslationRepository().record_backend_success(
        backend_name, response_time_ms, characters_used
    )


def record_backend_failure(backend_name: str, error_msg: str):
    """Record a failed translation for a backend."""
    return TranslationRepository().record_backend_failure(backend_name, error_msg)


def get_backend_stats() -> list:
    """Get stats for all translation backends."""
    return TranslationRepository().get_backend_stats()


def get_backend_stat(backend_name: str):
    """Get stats for a single translation backend."""
    return TranslationRepository().get_backend_stat(backend_name)


def reset_backend_stats(backend_name: str) -> bool:
    """Reset stats for a backend. Returns True if a row was deleted."""
    return TranslationRepository().reset_backend_stats(backend_name)


# ---- Quality convenience functions -----------------------------------------------

def save_health_result(file_path: str, score: int, issues_json: str,
                       checks_run: int, checked_at: str) -> dict:
    """Save a health check result to the database."""
    return QualityRepository().save_health_result(
        file_path, score, issues_json, checks_run, checked_at
    )


def get_health_result(file_path: str):
    """Get the most recent health result for a file path."""
    return QualityRepository().get_health_result(file_path)


def get_health_results_for_series(path_prefix: str) -> list:
    """Get all health results for files under a series path prefix."""
    return QualityRepository().get_health_results_for_series(path_prefix)


def get_quality_trends(days: int = 30) -> list:
    """Get daily average score and issue count for trend tracking."""
    return QualityRepository().get_quality_trends(days)


def delete_health_results(file_path: str) -> int:
    """Delete all health results for a file path."""
    return QualityRepository().delete_health_results(file_path)


# ---- Notification convenience functions ------------------------------------------

def create_notification_template(name: str, title_template: str = "",
                                  body_template: str = "", event_type: str = None,
                                  service_name: str = None, enabled: int = 1) -> dict:
    """Create a new notification template."""
    return NotificationRepository().create_template(
        name, title_template, body_template, event_type, service_name, enabled
    )


def get_notification_template(template_id: int):
    """Get a single notification template by ID."""
    return NotificationRepository().get_template(template_id)


def get_notification_templates(event_type: str = None) -> list:
    """Get all notification templates, optionally filtered by event_type."""
    return NotificationRepository().get_templates(event_type)


def update_notification_template(template_id: int, **kwargs):
    """Update a notification template."""
    return NotificationRepository().update_template(template_id, **kwargs)


def delete_notification_template(template_id: int) -> bool:
    """Delete a notification template."""
    return NotificationRepository().delete_template(template_id)


def find_template_for_event(event_type: str, service_name: str = None):
    """Find the best matching template for an event."""
    return NotificationRepository().find_template_for_event(event_type, service_name)


def log_notification(event_type: str, title: str, body: str,
                     template_id: int = None, service_urls: str = None,
                     status: str = "sent", error: str = "") -> dict:
    """Log a notification to history."""
    return NotificationRepository().log_notification(
        event_type, title, body, template_id, service_urls, status, error
    )


def get_notification_history(page: int = 1, per_page: int = 50,
                              event_type: str = None) -> dict:
    """Get paginated notification history."""
    return NotificationRepository().get_history(page, per_page, event_type)


def get_notification(notification_id: int):
    """Get a single notification history entry by ID."""
    return NotificationRepository().get_notification(notification_id)


def clear_notification_history(before_date: str = None) -> int:
    """Clear notification history."""
    return NotificationRepository().clear_history(before_date)


def create_quiet_hours(name: str, start_time: str, end_time: str,
                       days_of_week: str = "[0,1,2,3,4,5,6]",
                       exception_events: str = '["error"]',
                       enabled: int = 1) -> dict:
    """Create a quiet hours configuration."""
    return NotificationRepository().create_quiet_hours(
        name, start_time, end_time, days_of_week, exception_events, enabled
    )


def get_quiet_hours_configs() -> list:
    """Get all quiet hours configurations."""
    return NotificationRepository().get_quiet_hours_configs()


def update_quiet_hours(config_id: int, **kwargs):
    """Update a quiet hours config."""
    return NotificationRepository().update_quiet_hours(config_id, **kwargs)


def delete_quiet_hours(config_id: int) -> bool:
    """Delete a quiet hours config."""
    return NotificationRepository().delete_quiet_hours(config_id)


def is_quiet_hours(event_type: str) -> bool:
    """Check if current time falls within any active quiet hours window."""
    return NotificationRepository().is_quiet_hours(event_type)


# ---- AniDB absolute episode convenience functions --------------------------------

def get_anidb_absolute(tvdb_id: int, season: int, episode: int):
    """Return AniDB absolute episode number for a TVDB S/E pair, or None."""
    return AnidbRepository().get_anidb_absolute(tvdb_id, season, episode)


def upsert_anidb_mapping(
    tvdb_id: int, season: int, episode: int, anidb_absolute_episode: int,
    source: str = None,
) -> None:
    """Insert or update an AniDB absolute episode mapping."""
    return AnidbRepository().upsert_mapping(
        tvdb_id, season, episode, anidb_absolute_episode, source
    )


def list_anidb_mappings(tvdb_id: int) -> list:
    """Return all absolute episode mappings for a TVDB series."""
    return AnidbRepository().list_by_tvdb(tvdb_id)


def clear_anidb_mappings_for_tvdb(tvdb_id: int) -> int:
    """Delete all absolute episode mappings for a TVDB series."""
    return AnidbRepository().clear_for_tvdb(tvdb_id)


def get_series_absolute_order(sonarr_series_id: int) -> bool:
    """Return True if the series has absolute_order enabled."""
    return AnidbRepository().get_absolute_order(sonarr_series_id)


def set_series_absolute_order(sonarr_series_id: int, enabled: bool) -> None:
    """Enable or disable absolute_order mode for a series."""
    return AnidbRepository().set_absolute_order(sonarr_series_id, enabled)
