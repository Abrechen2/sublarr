"""Read-only grouped views into the Settings model.

Each view exposes a curated subset of Settings fields by name. Attribute
access is delegated to the underlying Settings instance for fields listed
in the subclass's _fields frozenset; everything else raises AttributeError.

Importing rule: this module MUST NOT import from `config_settings` at
module level (would cause a circular import). The `Settings` parameter
of `_SettingsView.__init__` is duck-typed; type-checking only sees it
through TYPE_CHECKING. See config_settings.py for the matching
dependency-contract comment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config_settings import Settings


class _SettingsView:
    """Base for read-only Settings group views.

    Delegates attribute access to the parent Settings instance for fields
    declared in the subclass ``_fields`` tuple. Raises ``AttributeError``
    for any field not in ``_fields``.
    """

    _fields: frozenset[str] = frozenset()

    def __init__(self, settings: Settings) -> None:
        object.__setattr__(self, "_s", settings)

    def __setattr__(self, name: str, value) -> None:
        raise AttributeError(f"{type(self).__name__!r} is read-only")

    def __getattr__(self, name: str):
        if name in self._fields:
            return getattr(self._s, name)
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")


class GeneralSettings(_SettingsView):
    """Infrastructure: port, logging, paths, DB, Redis, plugins, backup."""

    _fields = frozenset(
        (
            "port",
            "api_key",
            "log_level",
            "log_file",
            "log_format",
            "media_path",
            "db_path",
            "cors_origins",
            "database_url",
            "db_pool_size",
            "db_pool_max_overflow",
            "db_pool_recycle",
            "redis_url",
            "redis_cache_enabled",
            "redis_queue_enabled",
            "plugins_dir",
            "plugin_hot_reload",
            "backup_dir",
            "backup_retention_daily",
            "backup_retention_weekly",
            "backup_retention_monthly",
        )
    )


class TranslationSettings(_SettingsView):
    """LLM, translation languages, prompt template, glossary."""

    _fields = frozenset(
        (
            "source_language",
            "target_language",
            "source_language_name",
            "target_language_name",
            "auto_translate_any_source",
            "auto_translate_provider_multilang",
            "auto_translate_source_languages",
            "prompt_template",
            "ollama_url",
            "ollama_model",
            "batch_size",
            "request_timeout",
            "temperature",
            "max_retries",
            "backoff_base",
            "translation_max_workers",
            "glossary_enabled",
            "glossary_max_terms",
        )
    )


class ProviderSettings(_SettingsView):
    """Provider credentials, rate limiting, circuit breaker, reranking."""

    _fields = frozenset(
        (
            "provider_priorities",
            "providers_enabled",
            "providers_hidden",
            "provider_search_timeout",
            "provider_cache_ttl_minutes",
            "provider_auto_prioritize",
            "provider_rate_limit_enabled",
            "dedup_on_download",
            "provider_dynamic_timeout_enabled",
            "provider_dynamic_timeout_min_samples",
            "provider_dynamic_timeout_multiplier",
            "provider_dynamic_timeout_buffer_secs",
            "provider_dynamic_timeout_min_secs",
            "provider_dynamic_timeout_max_secs",
            "provider_reranking_enabled",
            "provider_reranking_min_downloads",
            "provider_reranking_max_modifier",
            "circuit_breaker_failure_threshold",
            "circuit_breaker_cooldown_seconds",
            "provider_auto_disable_cooldown_minutes",
            "provider_rate_limit_throttle_minutes",
            "addic7ed_username",
            "addic7ed_password",
            "turkcealtyazi_username",
            "turkcealtyazi_password",
            "opensubtitles_api_key",
            "opensubtitles_username",
            "opensubtitles_password",
            "jimaku_api_key",
            "subdl_api_key",
            "github_token",
            "anti_captcha_provider",
            "anti_captcha_api_key",
            "release_group_prefer",
            "release_group_exclude",
            "release_group_prefer_bonus",
        )
    )


class MediaServerSettings(_SettingsView):
    """Sonarr, Radarr, Jellyfin/Plex/Kodi, path mapping, ffmpeg, metadata."""

    _fields = frozenset(
        (
            "sonarr_url",
            "sonarr_api_key",
            "sonarr_instances_json",
            "radarr_url",
            "radarr_api_key",
            "radarr_instances_json",
            "jellyfin_url",
            "jellyfin_api_key",
            "media_servers_json",
            "path_mapping",
            "streaming_enabled",
            "ffmpeg_timeout",
            "scan_metadata_engine",
            "scan_metadata_max_workers",
        )
    )


class ScanningSettings(_SettingsView):
    """Wanted system, upgrade, HI, webhooks, automation, standalone, AniDB, notifications."""

    _fields = frozenset(
        (
            "wanted_scan_interval_hours",
            "wanted_anime_only",
            "wanted_anime_movies_only",
            "wanted_scan_on_startup",
            "wanted_auto_extract",
            "wanted_auto_translate",
            "wanted_max_search_attempts",
            "use_embedded_subs",
            "scan_yield_ms",
            # 0.71.0 subtitle automation bundle (see config_settings.py)
            "subtitle_automation_enabled",
            "subtitle_automation_queue_enabled",
            "subtitle_automation_drain_interval_minutes",
            "embedded_allow_sdh",
            "embedded_sdh_penalty",
            "embedded_extract_remove_from_container",
            "cleanup_foreign_tracks_default",
            "cleanup_foreign_tracks_keep_und",
            "cleanup_signs_removal_level",
            "dubtitle_detection",
            "dubtitle_min_score",
            "dubtitle_min_margin",
            "dubtitle_auto_min_cues",
            "wanted_search_interval_hours",
            "wanted_search_on_startup",
            "wanted_search_max_items_per_run",
            "wanted_search_order",
            "provider_budget_enabled",
            "provider_budget_stretch_mode",
            "scheduler_profile",
            "setup_wizard_completed",
            "wanted_adaptive_backoff_enabled",
            "wanted_backoff_base_hours",
            "wanted_backoff_cap_hours",
            "wanted_skip_srt_on_no_ass",
            "upgrade_enabled",
            "upgrade_min_score_delta",
            "upgrade_window_days",
            "upgrade_prefer_ass",
            "upgrade_protect_user_modified",
            "upgrade_scan_interval_hours",
            "hi_removal_enabled",
            "hi_preference",
            "forced_preference",
            "credit_threshold_sec",
            "op_window_sec",
            "webhook_delay_minutes",
            "webhook_auto_scan",
            "webhook_auto_search",
            "webhook_auto_translate",
            "jellyfin_play_translate_enabled",
            "auto_sync_after_download",
            "auto_sync_engine",
            "auto_nfo_export",
            "standalone_enabled",
            "standalone_scan_interval_hours",
            "standalone_debounce_seconds",
            "standalone_skip_extras",
            "tmdb_api_key",
            "tvdb_api_key",
            "tvdb_pin",
            "metadata_cache_ttl_days",
            "auto_cleanup_after_extract",
            "auto_cleanup_keep_languages",
            "auto_cleanup_keep_formats",
            "subtitle_trash_retention_days",
            "anidb_enabled",
            "anidb_cache_ttl_days",
            "anidb_custom_field_name",
            "anidb_fallback_to_mapping",
            "notification_urls_json",
            "notify_on_download",
            "notify_on_upgrade",
            "notify_on_batch_complete",
            "notify_on_error",
            "notify_manual_actions",
            "remux_trash_dir",
            "remux_backup_retention_days",
            "remux_use_reflink",
            "remux_arr_pause_enabled",
            "remux_hardlink_policy",
        )
    )


__all__ = [
    "_SettingsView",
    "GeneralSettings",
    "TranslationSettings",
    "ProviderSettings",
    "MediaServerSettings",
    "ScanningSettings",
]
