"""Repository pattern for Sublarr database operations using SQLAlchemy ORM.

Each repository class provides methods that mirror the existing db/ module
functions but use SQLAlchemy ORM sessions instead of raw sqlite3 queries.

Module-level convenience functions delegate to repository instances, providing
a drop-in replacement API for the existing db/ modules.

The convenience functions themselves live in db/repositories/facade.py and
are re-exported here so ``from db.repositories import save_config_entry``
keeps working unchanged.
"""

from db.repositories.anidb import AnidbRepository
from db.repositories.base import BaseRepository
from db.repositories.blacklist import BlacklistRepository
from db.repositories.cache import CacheRepository
from db.repositories.cleanup import CleanupRepository
from db.repositories.config import ConfigRepository
from db.repositories.facade import (
    add_blacklist_entry,
    add_glossary_entry,
    add_prompt_preset,
    cleanup_old_anidb_mappings,
    clear_anidb_mappings_for_tvdb,
    clear_blacklist,
    clear_ffprobe_cache,
    clear_notification_history,
    create_notification_template,
    create_quiet_hours,
    create_whisper_job,
    delete_glossary_entries_for_series,
    delete_glossary_entry,
    delete_health_results,
    delete_notification_template,
    delete_plugin_config,
    delete_prompt_preset,
    delete_provider_modifier,
    delete_quiet_hours,
    delete_whisper_job,
    find_template_for_event,
    get_all_config_entries,
    get_all_plugin_configs,
    get_all_provider_modifiers,
    get_all_scoring_weights,
    get_anidb_absolute,
    get_anidb_mapping,
    get_anidb_mapping_stats,
    get_backend_stat,
    get_backend_stats,
    get_blacklist_count,
    get_blacklist_entries,
    get_config_entry,
    get_default_prompt_preset,
    get_download_history,
    get_download_stats,
    get_episode_history,
    get_ffprobe_cache,
    get_glossary_entries,
    get_glossary_entry,
    get_glossary_for_series,
    get_health_result,
    get_health_results_for_series,
    get_notification,
    get_notification_history,
    get_notification_template,
    get_notification_templates,
    get_plugin_config,
    get_prompt_preset,
    get_prompt_presets,
    get_provider_modifier,
    get_quality_trends,
    get_quiet_hours_configs,
    get_scoring_weights,
    get_series_absolute_order,
    get_translation_config_history,
    get_upgrade_history,
    get_upgrade_stats,
    get_whisper_job,
    get_whisper_jobs,
    get_whisper_stats,
    is_blacklisted,
    is_quiet_hours,
    list_anidb_mappings,
    log_notification,
    record_backend_failure,
    record_backend_success,
    record_translation_config,
    record_upgrade,
    remove_blacklist_entry,
    reset_backend_stats,
    reset_scoring_weights,
    save_anidb_mapping,
    save_config_entry,
    save_health_result,
    search_glossary_terms,
    set_ffprobe_cache,
    set_plugin_config,
    set_provider_modifier,
    set_scoring_weights,
    set_series_absolute_order,
    update_glossary_entry,
    update_notification_template,
    update_prompt_preset,
    update_quiet_hours,
    update_whisper_job,
    upsert_anidb_mapping,
)
from db.repositories.hooks import HookRepository
from db.repositories.jobs import JobRepository
from db.repositories.library import LibraryRepository
from db.repositories.notifications import NotificationRepository
from db.repositories.plugins import PluginRepository
from db.repositories.presets import FilterPresetsRepository
from db.repositories.profiles import ProfileRepository
from db.repositories.providers import ProviderRepository
from db.repositories.quality import QualityRepository
from db.repositories.scoring import ScoringRepository
from db.repositories.search import SearchRepository
from db.repositories.standalone import StandaloneRepository
from db.repositories.translation import TranslationRepository
from db.repositories.wanted import WantedRepository
from db.repositories.whisper import WhisperRepository

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
