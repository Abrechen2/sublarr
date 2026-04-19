"""Sublarr application settings — Pydantic model.

Holds the declarative field definitions, the 8 instance methods used by
the rest of the app, and the 5 grouped-view property accessors.

Importing rules:
- This module imports `config_views` for the property accessor return
  types — `config_views` does NOT import back (TYPE_CHECKING guard).
- Singleton management lives in `config_singleton.py`; this module does
  NOT cache instances.
"""

import hashlib
import logging

from pydantic import Field
from pydantic_settings import BaseSettings

from config_language_data import _get_language_tags

# Runtime import of the view classes — used by the @property accessors below.
#
# Dependency contract (one-directional): config_settings -> config_views.
# config_views MUST NOT import config_settings at runtime (it uses
# TYPE_CHECKING + from __future__ import annotations to keep the forward
# reference lazy). Adding a runtime import of Settings into config_views
# would create a circular import at module load time.
from config_views import (
    GeneralSettings,
    MediaServerSettings,
    ProviderSettings,
    ScanningSettings,
    TranslationSettings,
)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Sublarr application settings.

    All fields can be overridden via SUBLARR_-prefixed env vars or a .env
    file. See backend/config.py for the public re-export surface.
    """

    # General
    port: int = 5765
    api_key: str = ""  # Empty = no auth required
    log_level: str = "INFO"
    log_file: str = (
        "log/sublarr.log"  # In-Repo default; Docker: set SUBLARR_LOG_FILE=/config/sublarr.log
    )
    media_path: str = "/media"
    db_path: str = "/config/sublarr.db"
    # Comma-separated allowed CORS/WebSocket origins (e.g. "https://app.example.com")
    # Defaults to localhost dev origins; set "*" only in fully trusted environments.
    cors_origins: str = "http://localhost:5173,http://localhost:5765"

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b-instruct"
    batch_size: int = 15
    request_timeout: int = 90
    temperature: float = 0.3
    max_retries: int = 3
    backoff_base: int = 5

    # Translation
    translation_enabled: bool = False  # Must be explicitly enabled — Beta feature
    source_language: str = "en"
    target_language: str = "de"
    source_language_name: str = "English"
    target_language_name: str = "German"
    prompt_template: str = ""  # Empty = auto-generated from languages

    # Subtitle Providers
    provider_priorities: str = "animetosho,jimaku,opensubtitles,subdl"
    providers_enabled: str = ""  # Empty = all registered providers enabled
    providers_hidden: str = (
        ""  # Comma-separated provider names hidden from the UI grid (truly removed)
    )

    # Addic7ed (TV subtitles — optional credentials increase download limit)
    addic7ed_username: str = ""
    addic7ed_password: str = ""

    # Turkcealtyazi (Turkish subtitles — account required)
    turkcealtyazi_username: str = ""
    turkcealtyazi_password: str = ""
    provider_search_timeout: int = 30  # Global timeout fallback (seconds)
    provider_cache_ttl_minutes: int = 5  # Cache TTL for provider search results
    provider_auto_prioritize: bool = True  # Auto-prioritize providers based on success rate
    provider_rate_limit_enabled: bool = True  # Enable rate limiting per provider
    dedup_on_download: bool = True  # Skip download if identical content already exists (SHA-256)
    # Plan B5 — subtitle repair pass before saving. Set False to disable.
    enable_subtitle_repair: bool = True
    github_token: str = ""  # Optional GitHub API token for higher rate limits (5000/h vs 60/h); env: SUBLARR_GITHUB_TOKEN

    # Dynamic Provider Timeouts (Phase 3)
    provider_dynamic_timeout_enabled: bool = True
    provider_dynamic_timeout_min_samples: int = 5
    provider_dynamic_timeout_multiplier: float = 3.0
    provider_dynamic_timeout_buffer_secs: float = 2.0
    provider_dynamic_timeout_min_secs: int = 5
    provider_dynamic_timeout_max_secs: int = 30

    # OpenSubtitles.com (API v2)
    opensubtitles_api_key: str = ""
    betaseries_api_key: str = ""
    opensubtitles_username: str = ""
    opensubtitles_password: str = ""

    # Jimaku (anime subtitles)
    jimaku_api_key: str = ""

    # SubDL (Subscene successor)
    subdl_api_key: str = ""

    # SubsDump (self-hosted Subscene archive)
    subsdump_url: str = "http://192.168.178.195"
    subsdump_api_key: str = ""

    # Sonarr (optional)
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    sonarr_instances_json: str = ""  # JSON array of Sonarr instances: [{"name": "Main", "url": "...", "api_key": "...", "path_mapping": "..."}]

    # Radarr (optional — for anime movies)
    radarr_url: str = ""
    radarr_api_key: str = ""
    radarr_instances_json: str = ""  # JSON array of Radarr instances: [{"name": "Main", "url": "...", "api_key": "...", "path_mapping": "..."}]

    # Jellyfin/Emby (optional — library refresh)
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    # Media Servers (multi-backend: Jellyfin, Plex, Kodi)
    media_servers_json: str = ""  # JSON array of media server instances

    # Path Mapping (remote → local, for when *arr apps run on different host)
    # Format: "remote_prefix=local_prefix" (semicolon-separated for multiple)
    # Example: "/data/media=Z:\Media;/anime=Z:\Anime"
    path_mapping: str = ""

    # ffmpeg / ffprobe
    ffmpeg_timeout: int = (
        120  # Seconds before ffmpeg subtitle-extraction is killed (SUBLARR_FFMPEG_TIMEOUT)
    )

    # Scan Metadata Engine
    scan_metadata_engine: str = "auto"  # "ffprobe" | "mediainfo" | "auto"
    scan_metadata_max_workers: int = 2  # Parallel workers for batch metadata scans

    # Translation Workers
    translation_max_workers: int = 4  # Parallel workers in the job queue thread pool

    # Wanted System
    wanted_scan_interval_hours: int = (
        0  # 0 = disabled; scan is event-driven (webhook / manual / file-watcher)
    )
    wanted_anime_only: bool = True
    wanted_anime_movies_only: bool = (
        False  # Filter Radarr movies by anime tag (separate from wanted_anime_only)
    )
    wanted_scan_on_startup: bool = False
    wanted_auto_extract: bool = False  # Auto-extract embedded subs during wanted scan
    wanted_auto_translate: bool = False  # Auto-translate after auto-extract during wanted scan
    wanted_max_search_attempts: int = 3
    use_embedded_subs: bool = True  # Check embedded subtitle streams in MKV files
    scan_yield_ms: int = 0  # Sleep between series/movies (ms) to yield CPU to API threads

    # Provider Re-ranking
    provider_reranking_enabled: bool = False  # Auto-adjust score modifiers from download history
    provider_reranking_min_downloads: int = (
        20  # Min successful downloads before modifier is applied
    )
    provider_reranking_max_modifier: int = 50  # Absolute cap on computed modifier (±)

    # Release Group Filtering
    release_group_prefer: str = (
        ""  # Comma-separated preferred release groups (e.g. "SubsPlease,Erai-raws")
    )
    release_group_exclude: str = ""  # Comma-separated blocked release groups (e.g. "HorribleSubs")
    release_group_prefer_bonus: int = 20  # Score bonus for preferred release group matches

    # Upgrade System
    upgrade_enabled: bool = True
    upgrade_min_score_delta: int = 50
    upgrade_window_days: int = 7
    upgrade_prefer_ass: bool = True  # SRT->ASS always upgrade

    # Hearing Impaired
    hi_removal_enabled: bool = False
    hi_preference: str = "include"  # include | prefer | exclude | only

    # Staff Credit Filtering
    credit_threshold_sec: int = 90
    """Seconds from end of subtitle file to treat as credits region.
    Set via SUBLARR_CREDIT_THRESHOLD_SEC."""
    op_window_sec: int = 300  # seconds from start/end of file to consider OP/ED window

    # Forced Subtitles
    forced_preference: str = "include"  # include | prefer | exclude | only

    # Webhook Automation
    webhook_delay_minutes: int = 5  # Wait time after Sonarr/Radarr webhook
    webhook_auto_scan: bool = True
    webhook_auto_search: bool = True
    webhook_auto_translate: bool = True
    jellyfin_play_translate_enabled: bool = False  # Auto-translate when Jellyfin starts playback

    # Video Sync (ffsubsync / alass)
    auto_sync_after_download: bool = False  # Auto-sync subtitle against video after download
    auto_sync_engine: str = "ffsubsync"  # Engine for auto-sync: "ffsubsync" | "alass"

    # Post-download subtitle processing pipeline
    auto_process_common_fixes: bool = False
    auto_process_common_fixes_config_json: str = ""  # JSON; empty = all defaults
    auto_process_hi_removal: bool = False
    auto_process_credit_removal: bool = False
    auto_process_sync_threshold: int = 60  # score below which auto-sync triggers
    auto_process_sync_fallback_engine: str = "ffsubsync"

    # HI interjections list (newline-separated; empty = use backend/data/hi_interjections.txt)
    hi_interjections_list: str = ""

    # Post-download shell command
    post_download_command: str = ""  # Shell command to run after each subtitle download
    post_processing_enabled: bool = (
        False  # Must be explicitly enabled; gate for post_download_command
    )

    # NFO Export
    auto_nfo_export: bool = False  # Expert: write XML NFO sidecar after every download/translation

    # Glossary
    glossary_enabled: bool = True  # Enable glossary injection during translation
    glossary_max_terms: int = 100  # Maximum number of glossary terms injected per translation

    # Web Player
    streaming_enabled: bool = True  # Enable HTTP range-request video streaming endpoint

    # Wanted Search Scheduler
    wanted_search_interval_hours: int = 24  # 0 = disabled
    wanted_search_on_startup: bool = True
    wanted_search_max_items_per_run: int = 500
    wanted_search_order: str = "fair"  # 'fair' | 'newest_first' | 'weighted'
    # Prepend a priority rank (premium=0, standard=1, backlog=2) to the scheduler
    # ORDER BY so premium items always win the first slice of the tick budget.
    wanted_scheduler_priority_weighting_enabled: bool = True
    # Day-budget spent % above which backlog-priority items are deferred to the
    # next tick. Ensures premium+standard items always get a fair slice.
    wanted_scheduler_backlog_reserve_pct: int = 50
    # Master gate for the per-provider API-budget manager. When False, the
    # search coordinator reverts to pre-V1 behaviour (no budget accounting).
    provider_budget_enabled: bool = True
    # Pacing strategy for the budget manager:
    #   'stretch' (default) — block calls once the current-hour pace exceeds
    #       an evenly-paced share of the day's limit; prevents burning the
    #       whole daily quota in the first hour.
    #   'burst'  — raw window caps only for the first
    #       ``provider_budget_burst_window_hours`` hours of the UTC day; after
    #       that, the REMAINING day quota is paced across the REMAINING hours.
    #       Use this for providers where the quota resets at midnight UTC and
    #       you want to front-load the search queue.
    #   'off'    — alias; use provider_budget_enabled=false to disable fully.
    provider_budget_stretch_mode: str = "stretch"
    # Burst window length in hours (UTC). Only applies when
    # provider_budget_stretch_mode='burst'.
    provider_budget_burst_window_hours: int = 6
    # Scheduler profile (mapped to preset values via services/scheduler_profile.py)
    scheduler_profile: str = "balanced"  # 'light' | 'balanced' | 'aggressive' | 'custom'
    # Scheduler history retention — days of job_run rows kept before
    # scheduler_history_cleanup cron deletes them.
    scheduler_history_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description=(
            "Keep scheduler job-run history for this many days before "
            "the scheduler_history_cleanup cron deletes old rows."
        ),
    )
    # Translation telemetry retention — days of translation_events rows kept
    # before the translation_events_cleanup cron deletes them.
    translation_events_retention_days: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Keep translation_events rows for this many days.",
    )
    # First-run wizard completion flag — persisted by the wizard endpoints so
    # the UI shows the wizard at most once per installation.
    setup_wizard_completed: bool = False

    # Upgrade Scheduler
    upgrade_scan_interval_hours: int = 0  # 0 = disabled; user must opt in

    # Wanted Adaptive Backoff
    wanted_adaptive_backoff_enabled: bool = True
    wanted_backoff_base_hours: float = 1.0
    wanted_backoff_cap_hours: int = 168  # 7 days

    # Wanted Early Exit
    wanted_skip_srt_on_no_ass: bool = True  # Skip SRT steps if no ASS found in steps 1+2

    # Notifications (Apprise)
    notification_urls_json: str = ""  # JSON array or newline-separated Apprise URLs
    notify_on_download: bool = True
    notify_on_upgrade: bool = True
    notify_on_batch_complete: bool = True
    notify_on_error: bool = True
    notify_manual_actions: bool = False

    # Anti-Captcha
    anti_captcha_provider: str = ""  # "" | "anticaptcha" | "capmonster"
    anti_captcha_api_key: str = ""

    # Remux / Stream Removal
    remux_trash_dir: str = ".sublarr"  # Relative (to media_path) or absolute path for backup trash
    remux_backup_retention_days: int = 7  # 0 = keep forever
    remux_use_reflink: bool = True  # CoW reflink on Btrfs/XFS for zero-cost backups
    remux_arr_pause_enabled: bool = True  # Pause Sonarr/Radarr during remux

    # Circuit Breaker
    circuit_breaker_failure_threshold: int = 5  # Consecutive failures before opening
    circuit_breaker_cooldown_seconds: int = 300  # Seconds in OPEN before HALF_OPEN probe
    provider_auto_disable_cooldown_minutes: int = (
        30  # Minutes before auto-disabled provider is re-enabled
    )
    provider_rate_limit_throttle_minutes: int = 60  # Extended throttle on HTTP 429

    # Logging
    log_format: str = "text"  # "text" or "json" (structured JSON for log aggregation)

    # Database Backup
    backup_dir: str = "/config/backups"
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_retention_monthly: int = 3

    # Plugin System
    plugins_dir: str = "/config/plugins"
    plugin_hot_reload: bool = False  # Enable watchdog file watcher for plugins directory

    # Standalone Mode
    standalone_enabled: bool = False
    standalone_scan_interval_hours: int = 6  # 0 = disabled
    standalone_debounce_seconds: int = 10
    standalone_skip_extras: bool = True  # Skip trailers/featurettes/samples during scan
    tmdb_api_key: str = ""  # TMDB API v3 Bearer token
    tvdb_api_key: str = ""  # TVDB API v4 key (optional)
    tvdb_pin: str = ""  # TVDB PIN (optional)
    metadata_cache_ttl_days: int = 30

    # Sidecar Auto-Cleanup
    auto_cleanup_after_extract: bool = False  # Delete extra-language sidecars after batch-extract
    auto_cleanup_keep_languages: str = (
        ""  # Comma-separated ISO-639-1 codes to keep (empty = nothing deleted)
    )
    auto_cleanup_keep_formats: str = (
        "any"  # "ass" | "srt" | "any" — delete SRT when ASS exists for same lang
    )

    # Subtitle Trash / Soft-Delete
    subtitle_trash_retention_days: int = (
        30  # Days to keep trashed subtitle files before auto-purge (0 = keep forever)
    )

    # AniDB Integration
    anidb_enabled: bool = True  # Enable AniDB ID resolution
    anidb_cache_ttl_days: int = 30  # Cache TTL for TVDB → AniDB mappings
    anidb_custom_field_name: str = "anidb_id"  # Custom field name in Sonarr
    anidb_fallback_to_mapping: bool = True  # Use cache/mapping as fallback

    # Database (PERF-01, PERF-02)
    database_url: str = ""  # Empty = SQLite at db_path. Set to postgresql://... for PG.
    db_pool_size: int = 5  # SQLAlchemy pool_size (ignored for SQLite)
    db_pool_max_overflow: int = 10  # SQLAlchemy max_overflow (ignored for SQLite)
    db_pool_recycle: int = 3600  # Recycle connections after N seconds

    # Redis (PERF-04, PERF-06)
    redis_url: str = ""  # Empty = no Redis. e.g., redis://localhost:6379/0
    redis_cache_enabled: bool = True  # Use Redis for provider cache (when redis_url set)
    redis_queue_enabled: bool = True  # Use Redis+RQ for job queue (when redis_url set)

    # Interface Preferences (Step 37)
    interface_language: str = "en"
    items_per_page: int = 25
    default_library_view: str = "grid"  # "grid" | "list"
    default_library_sort: str = "alpha"  # "alpha" | "date" | "score"
    datetime_format: str = "relative"  # "relative" | "absolute"

    # Subtitle Naming (Step 38)
    subtitle_language_code_format: str = "iso_639_1"  # "iso_639_1" | "iso_639_2"
    subtitle_suffix_separator: str = "dot"  # "dot" | "dash" | "underscore"
    subtitle_hi_suffix: str = "hi"
    subtitle_forced_suffix: str = "forced"

    # Quiet Hours (Step 39)
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = "23:00"
    quiet_hours_end: str = "07:00"
    quiet_hours_timezone: str = "UTC"

    # Auto Backup (Step 40)
    backup_auto_enabled: bool = False
    backup_auto_interval_hours: int = 24
    backup_auto_on_startup: bool = False
    backup_notify_on_failure: bool = True

    # Disk Monitoring (Step 41)
    disk_warning_threshold_percent: int = 90
    disk_warning_notify: bool = True

    # Scan Ignore Patterns (Step 42)
    scan_ignore_patterns: str = "[]"  # JSON array of glob patterns
    scan_min_file_size_mb: float = 0.0
    scan_ignore_languages: str = "[]"  # JSON array of ISO-639-1 codes

    # Per-Language Score Thresholds (Step 43)
    score_threshold_per_language: str = "{}"  # JSON object: {"de": 80, "fr": 70}

    # Download Limits (Step 44)
    max_concurrent_provider_searches: int = 3
    max_subtitle_file_size_kb: int = 2048
    download_delay_between_providers_ms: int = 0
    gestdown_retry_delay_s: float = 1.0
    """Wartezeit in Sekunden vor dem Retry nach HTTP 423 (Locked) von Gestdown.
    Niedrigere Werte beschleunigen Batch-Scans; 0.0 deaktiviert das Warten.
    Env: SUBLARR_GESTDOWN_RETRY_DELAY_S"""

    # Translation Context (Step 45)
    translation_use_episode_context: bool = False
    translation_context_episodes: int = 1
    translation_series_glossary_auto: bool = False

    # Translation Context Window (Phase A4 — lookback/lookahead for LLM backends)
    translation_context_enabled: bool = Field(
        default=True,
        description=(
            "Include lookback/lookahead subtitle lines as context when "
            "translating via LLM backends. Improves narrative coherence "
            "and pronoun resolution. Token cost: ~300 extra tokens per "
            "batch of 50 lines."
        ),
    )
    translation_context_lookback_lines: int = Field(
        default=10,
        ge=0,
        le=50,
        description="Lines BEFORE each batch included as context (LLM-only).",
    )
    translation_context_lookahead_lines: int = Field(
        default=5,
        ge=0,
        le=50,
        description="Lines AFTER each batch included as context (LLM-only).",
    )

    # Extended Security (Step 46)
    session_timeout_minutes: int = 0  # 0 = no timeout
    max_login_attempts: int = 20
    lockout_duration_minutes: int = 60
    allowed_ip_ranges: str = ""  # Comma-separated CIDR ranges; empty = allow all

    model_config = {
        "env_prefix": "SUBLARR_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_database_url(self) -> str:
        """Get the SQLAlchemy database URL.

        Returns database_url if set, otherwise constructs a SQLite URL from db_path.
        """
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"

    def get_prompt_template(self) -> str:
        """Get the translation prompt template.

        Priority:
        1. Default prompt preset from database (if exists)
        2. prompt_template setting (if set)
        3. Auto-generated template
        """
        # Try to get default preset from database
        try:
            from db.translation import get_default_prompt_preset

            preset = get_default_prompt_preset()
            if preset and preset.get("prompt_template"):
                template = preset["prompt_template"]
                # Substitute {source_language}/{target_language} placeholders
                template = template.replace("{source_language}", self.source_language_name)
                template = template.replace("{target_language}", self.target_language_name)
                return template
        except Exception as exc:
            # Database might not be initialized yet, fall through
            logger.debug("Could not load default prompt preset: %s", exc)

        # Fall back to config setting
        if self.prompt_template:
            return self.prompt_template

        # Auto-generated template
        return (
            f"Translate these anime subtitle lines from {self.source_language_name} to {self.target_language_name}.\n"
            f"Return ONLY the translated lines, one per line, same count.\n"
            f"Preserve \\N exactly as \\N (hard line break).\n"
            f"Do NOT add numbering or prefixes to the output lines.\n\n"
        )

    def get_target_patterns(self, fmt: str = "ass") -> list[str]:
        """Get file patterns for detecting existing target language subtitles."""
        lang = self.target_language
        # Common language tags for the target language
        lang_tags = _get_language_tags(lang)
        return [f".{tag}.{fmt}" for tag in lang_tags]

    def get_source_patterns(self, fmt: str = "ass") -> list[str]:
        """Get file patterns for detecting existing source language subtitles."""
        lang = self.source_language
        lang_tags = _get_language_tags(lang)
        return [f".{tag}.{fmt}" for tag in lang_tags]

    def get_target_lang_tags(self) -> set[str]:
        """Get all language tags for the target language."""
        return _get_language_tags(self.target_language)

    def get_source_lang_tags(self) -> set[str]:
        """Get all language tags for the source language."""
        return _get_language_tags(self.source_language)

    def get_translation_config_hash(self, backend_name: str = "ollama") -> str:
        """SHA256 hash of backend+model+prompt+target_language (first 12 chars).

        For Ollama backends, includes the model name and prompt template.
        For non-Ollama backends (DeepL, Google, etc.), model is not relevant
        so the hash is based on backend name and target language only.

        Args:
            backend_name: Translation backend name (default "ollama")
        """
        if backend_name == "ollama":
            content = f"{backend_name}|{self.ollama_model}|{self.get_prompt_template()[:50]}|{self.target_language}"
        else:
            content = f"{backend_name}||{self.target_language}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def get_safe_config(self) -> dict:
        """Get config dict without sensitive values (API keys, passwords, tokens)."""
        import json as _json

        _SENSITIVE_PARTS = {"password", "pin", "secret", "token", "api_key"}
        # Fields that contain credentials but don't match _SENSITIVE_PARTS name heuristics
        _EXPLICIT_MASKED = {"database_url", "redis_url"}
        _JSON_BLOB_FIELDS = {
            "sonarr_instances_json",
            "radarr_instances_json",
            "media_servers_json",
        }
        _CREDENTIAL_SUBKEYS = {"api_key", "apiKey", "password", "token", "secret", "pin"}

        data = self.model_dump()
        for key in list(data.keys()):
            if key in _EXPLICIT_MASKED or (
                "api_key" in key
                or "key" in key.split("_")
                or any(s in key for s in _SENSITIVE_PARTS)
            ):
                if data[key]:
                    data[key] = "***configured***"
                else:
                    data[key] = ""
            elif key == "notification_urls_json" and data[key]:
                data[key] = "***configured***"
            elif key in _JSON_BLOB_FIELDS and data[key]:
                try:
                    parsed = _json.loads(data[key])
                    if isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict):
                                for sub in _CREDENTIAL_SUBKEYS:
                                    if sub in item and item[sub]:
                                        item[sub] = "***configured***"
                    data[key] = _json.dumps(parsed)
                except Exception:
                    data[key] = "***configured***"
        return data

    # --- Grouped settings views (read-only delegation) ---

    @property
    def general(self) -> "GeneralSettings":
        """View into general/infrastructure settings."""
        return GeneralSettings(self)

    @property
    def translation(self) -> "TranslationSettings":
        """View into LLM and translation settings."""
        return TranslationSettings(self)

    @property
    def providers(self) -> "ProviderSettings":
        """View into subtitle provider and credential settings."""
        return ProviderSettings(self)

    @property
    def media_servers(self) -> "MediaServerSettings":
        """View into *arr, media server, and ffmpeg settings."""
        return MediaServerSettings(self)

    @property
    def scanning(self) -> "ScanningSettings":
        """View into scanning, wanted, upgrade, and automation settings."""
        return ScanningSettings(self)


__all__ = ["Settings"]
