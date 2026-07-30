"""Sublarr application settings — Boot + UI split (since v0.88.0-beta).

Structure:
- ``BootSettings(BaseSettings)``  — env-loadable. Holds the small set of
  fundamentals that have to be set before the database is reachable
  (DB URL, mount paths, port, log level, …). Curated allowlist enforced
  by ``tools/lint_no_new_env_fields.py``.
- ``UISettings(BaseModel)``        — DB-only. Holds every other configurable
  behaviour. ``BaseModel`` (not ``BaseSettings``) means Pydantic does NOT
  auto-load env vars, so the UI is the sole writer.
- ``Settings``                     — composite. Forwards attribute access to
  ``boot`` or ``ui`` so existing call-sites (``settings.api_key``,
  ``settings.opensubtitles_api_key``) keep working unchanged.

UI-first convention (V1, decided 2026-05-04): every new setting lands in
``UISettings``. The CI linter rejects new fields added to ``BootSettings``
outside ``_ALLOWED_BOOT_FIELDS``.

Importing rules:
- This module imports ``config_views`` for the property accessor return
  types — ``config_views`` does NOT import back (TYPE_CHECKING guard).
- Singleton management lives in ``config_singleton.py``; this module does
  NOT cache instances.
"""

import hashlib
import logging
import os
from typing import Any

from pydantic import BaseModel, Field, field_validator
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


# Curated allowlist for env-loadable fields. Any new entry here must clear
# the linter check (`tools/lint_no_new_env_fields.py`). Adding a UI feature?
# Put the field on UISettings, not here.
_ALLOWED_BOOT_FIELDS: frozenset[str] = frozenset(
    {
        "port",
        "api_key",
        "media_path",
        "db_path",
        "database_url",
        "config_dir",
        "log_level",
        "log_file",
        "log_format",
        "cors_origins",
        "redis_url",
        # Anonymous-stats kill-switch/redirect — must be env-overridable
        # pre-DB so self-hosters can disable sending before first boot.
        "stats_endpoint",
    }
)


class BootSettings(BaseSettings):
    """Bootstrap settings — env-loadable, pre-DB.

    Membership is gated by ``_ALLOWED_BOOT_FIELDS`` and enforced in CI by
    ``tools/lint_no_new_env_fields.py``. Add a UI feature? Put the field
    on ``UISettings`` instead.
    """

    # Server bind
    port: int = 5765

    # Initial auth bootstrap (empty = no auth required)
    api_key: str = ""

    # Mount paths — Docker volume targets that must exist before any
    # path-based code runs.
    media_path: str = "/media"
    config_dir: str = "/config"

    # Database — ``database_url`` (PG) wins over ``db_path`` (SQLite) at
    # ``Settings.get_database_url()`` time.
    db_path: str = "/config/sublarr.db"
    database_url: str = ""

    # Anonymous usage statistics (opt-in). Empty string disables sending entirely,
    # regardless of the in-app consent toggle (self-hoster kill-switch / redirect).
    stats_endpoint: str = "https://stats.sublarr.de/v1/ping"

    # Redis (optional cache + queue backend)
    redis_url: str = ""

    # Logging — needed before any log line can land in the right format.
    log_level: str = "INFO"
    # In-Repo default; Docker: set SUBLARR_LOG_FILE=/config/sublarr.log
    log_file: str = "log/sublarr.log"
    log_format: str = "text"  # "text" or "json" (structured for log aggregation)

    # Comma-separated allowed CORS/WebSocket origins (e.g. "https://app.example.com").
    # Defaults to localhost dev origins; set "*" only in fully trusted environments.
    cors_origins: str = "http://localhost:5173,http://localhost:5765"

    model_config = {
        "env_prefix": "SUBLARR_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


class UISettings(BaseModel):
    """UI-configured settings — DB-only.

    ``BaseModel`` (not ``BaseSettings``) means Pydantic does NOT load env
    vars for these fields. The UI writes them through ``config_entries``
    and ``reload_settings()`` overlays them onto the defaults below.

    UI-first convention: every new configurable behaviour lands here.
    """

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
    # Multi-language auto-translate source. When on, the missing target is
    # translated FROM whatever source subtitle actually exists (any language),
    # preferring the profile/global source; otherwise only the preferred source
    # language is used. ``auto_translate_provider_multilang`` additionally lets
    # the provider search try several source languages, and
    # ``auto_translate_source_languages`` is the ordered candidate/preference
    # list used for that search and for choosing among available local sources.
    auto_translate_any_source: bool = True
    auto_translate_provider_multilang: bool = True
    auto_translate_source_languages: list[str] = [
        "en",
        "ja",
        "zh",
        "ko",
        "es",
        "fr",
        "de",
        "pt",
        "it",
        "ru",
    ]

    @field_validator("auto_translate_source_languages", mode="before")
    @classmethod
    def _parse_source_language_list(cls, v):
        """Coerce a persisted config value into a list of language codes.

        The generic /config writer stores non-string values via ``str()``, so a
        list round-trips as its Python repr (``"['ja', 'en']"``). Accept a real
        list, a JSON array, that Python-repr string, or a comma-separated string
        so the setting survives an API/DB round-trip regardless of how it was
        stored.
        """
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            import ast as _ast
            import json as _json

            for _parse in (_json.loads, _ast.literal_eval):
                try:
                    parsed = _parse(s)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except (ValueError, SyntaxError):
                    pass
            return [p.strip() for p in s.split(",") if p.strip()]
        return v

    prompt_template: str = ""  # Empty = auto-generated from languages
    # Global default translation backend + optional single fallback. A language
    # profile with an empty translation_backend inherits these. Declared here as
    # UISettings so the /config API surfaces AND accepts them (the Backends-page
    # "Default translation backend" control reads/writes via /config). The
    # resolver reads them via db.config.get_config_entry — this default is only
    # the fallback when no config_entry row exists.
    translation_default_backend: str = "ollama"
    translation_default_fallback: str = ""

    # Subtitle Providers
    provider_priorities: str = "animetosho,jimaku,opensubtitles,subdl"
    providers_enabled: str = ""  # Empty = all registered providers enabled
    providers_hidden: str = ""  # Comma-separated provider names hidden from UI grid

    # Reverse-proxy header authentication (Authelia/authentik SSO).
    # When enabled, a request whose DIRECT peer IP (request.remote_addr — no
    # ProxyFix) is within proxy_auth_trusted_ips is authenticated if it carries
    # a non-empty proxy_auth_header. OFF by default; fails closed with no allowlist.
    proxy_auth_enabled: bool = False
    proxy_auth_trusted_ips: str = ""  # comma-separated IPs / CIDRs of trusted proxies
    proxy_auth_header: str = "Remote-User"

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
    github_token: str = ""  # Optional GitHub API token for higher rate limits

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

    # Custom HTTP/JSON provider (generic, user-configured REST endpoint —
    # see docs/CUSTOM_PROVIDER_API.md for the contract)
    customapi_base_url: str = ""
    customapi_api_key: str = ""
    customapi_api_key_header: str = "X-API-Key"
    customapi_search_path: str = "/search"
    customapi_download_path: str = "/download/{id}"
    customapi_results_path: str = "results"
    customapi_field_map: str = ""  # JSON object: SubtitleResult field -> response path
    customapi_extra_params: str = ""  # JSON object: extra query params sent on search
    customapi_instances_json: str = ""  # JSON array of additional instances

    # Sonarr (optional)
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    sonarr_instances_json: str = ""  # JSON array of Sonarr instances

    # Radarr (optional — for anime movies)
    radarr_url: str = ""
    radarr_api_key: str = ""
    radarr_instances_json: str = ""  # JSON array of Radarr instances

    # Jellyfin/Emby (optional — library refresh)
    jellyfin_url: str = ""
    jellyfin_api_key: str = ""

    # Media Servers (multi-backend: Jellyfin, Plex, Kodi)
    media_servers_json: str = ""  # JSON array of media server instances

    # Path Mapping (remote → local, for when *arr apps run on different host)
    # Format: "remote_prefix=local_prefix" (semicolon-separated for multiple)
    # Example: "/data/media=Z:\\Media;/anime=Z:\\Anime"
    path_mapping: str = ""

    # ffmpeg / ffprobe
    ffmpeg_timeout: int = 120  # Seconds before ffmpeg subtitle-extraction is killed

    # Scan Metadata Engine
    scan_metadata_engine: str = "auto"  # "ffprobe" | "mediainfo" | "auto"
    scan_metadata_max_workers: int = 2  # Parallel workers for batch metadata scans

    # Translation Workers
    translation_max_workers: int = 4  # Parallel workers in the job queue thread pool

    # Wanted System
    wanted_scan_interval_hours: int = 0  # 0 = disabled; event-driven
    wanted_anime_only: bool = True
    wanted_anime_movies_only: bool = False  # Filter Radarr movies by anime tag
    wanted_scan_on_startup: bool = False
    wanted_auto_extract: bool = False  # Auto-extract embedded subs during wanted scan
    wanted_auto_translate: bool = False  # Auto-translate after auto-extract
    wanted_max_search_attempts: int = 3
    # After ``wanted_max_search_attempts`` slow-mode cycles also fail, escalate
    # to status='unsourceable' so the row stops eating scheduler budget. Set
    # to a very high value to keep slow-mode forever (legacy behaviour).
    wanted_search_max_slow_cycles: int = Field(
        default=3,
        ge=0,
        le=999,
        description=(
            "After this many slow-mode no_result cycles, mark the wanted item "
            "as 'unsourceable' to remove it from the active scheduler queue."
        ),
    )
    use_embedded_subs: bool = True  # Check embedded subtitle streams in MKV files
    scan_yield_ms: int = 0  # Sleep between series/movies (ms) to yield CPU

    # 0.71.0 — Subtitle Automation (batteries-included extract/SDH/cleanup bundle)
    subtitle_automation_enabled: bool = False
    subtitle_automation_queue_enabled: bool = True  # Drain worker for pending extracts
    subtitle_automation_drain_interval_minutes: int = 2  # Scheduler tick cadence

    # SDH source tolerance.
    embedded_allow_sdh: bool = True
    embedded_sdh_penalty: int = 5

    # Dubtitle detection (roadmap A4 / issue #146). Off by default: surfaces
    # the dubtitle among multiple English tracks; suggest-then-confirm, never
    # silently applied. dubtitle_min_score is the Tier-2 audio-match threshold.
    dubtitle_detection: bool = False
    dubtitle_min_score: float = 0.55
    # Unattended-mode guardrails (Gemini review 2026-06-14): require a clear
    # gap between the best and runner-up audio match before auto-flagging, and
    # demand a denser dialogue track than the on-demand path so a sparse signs
    # track can't fluke a single-window match.
    dubtitle_min_margin: float = 0.15
    dubtitle_auto_min_cues: int = 70
    # When True, an English sidecar downloaded for an episode with English dub
    # audio is scored against the dub (Tier-2) before being kept; a sub that is a
    # confident low-score mismatch is KEPT but flagged (not trashed). Opt-in:
    # verification needs Whisper + dub audio and falls back to "keep" when either
    # is unavailable.
    dubtitle_verify_on_download: bool = False

    # Foreign-track cleanup. Destructive (remuxes the MKV with backup-to-trash).
    cleanup_foreign_tracks_default: bool = False
    cleanup_foreign_tracks_keep_und: bool = False
    # Languages always kept by foreign-track cleanup, on top of the item's
    # target/wanted languages. Guarantees e.g. English survives even when
    # only German is the download target. Empty list = target languages only.
    cleanup_foreign_tracks_keep_languages: list[str] = ["de", "en"]

    # Signs/forced/songs removal level (cleanup_signs rule + extract hook).
    # off | signs | signs_forced | signs_forced_songs. Default off.
    cleanup_signs_removal_level: str = "off"

    # Provider Re-ranking
    provider_reranking_enabled: bool = False  # Auto-adjust score modifiers
    provider_reranking_min_downloads: int = 20  # Min downloads before modifier applied
    provider_reranking_max_modifier: int = 50  # Absolute cap on computed modifier (±)

    # Release Group Filtering
    release_group_prefer: str = ""  # Comma-separated preferred release groups
    release_group_exclude: str = ""  # Comma-separated blocked release groups
    release_group_prefer_bonus: int = 20  # Score bonus for preferred release group matches

    # Upgrade System
    upgrade_enabled: bool = True
    upgrade_min_score_delta: int = 50
    upgrade_window_days: int = 7
    upgrade_prefer_ass: bool = True  # SRT->ASS always upgrade
    # Never auto-replace subtitles the user hand-edited in the editor
    upgrade_protect_user_modified: bool = True

    # Hearing Impaired
    hi_removal_enabled: bool = False
    hi_preference: str = "include"  # include | prefer | exclude | only

    # Staff Credit Filtering
    credit_threshold_sec: int = 90
    """Seconds from end of subtitle file to treat as credits region."""
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
    sync_sanity_threshold_ms: int = 45_000
    """Reject engine results whose absolute shift exceeds this many ms; the
    orchestrator then falls through to the next engine. ffsubsync's
    speech-detection sometimes mis-locks onto a wrong reference (intro vs
    cold-open), producing shifts clustered just under 60s with no real
    alignment. Default lowered from 60000 to 45000 (2026-06-10) after a prod
    bulk run surfaced a mis-lock cluster at ±56-60ms — just under the old
    ceiling. 45000 still admits genuine large offsets while rejecting that
    cluster; raise it again per-install if legitimate >45s shifts get cut."""

    # Post-download subtitle processing pipeline
    auto_process_common_fixes: bool = False
    auto_process_common_fixes_config_json: str = ""  # JSON; empty = all defaults
    auto_process_hi_removal: bool = False
    auto_process_credit_removal: bool = False
    auto_process_sync_threshold: int = 60  # score below which auto-sync triggers
    auto_process_sync_fallback_engine: str = "ffsubsync"

    # Post-download shell command
    post_download_command: str = ""  # Shell command to run after each subtitle download
    post_processing_enabled: bool = False  # Must be explicitly enabled

    # NFO Export
    auto_nfo_export: bool = False  # Expert: write XML NFO sidecar after every download

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
    wanted_scheduler_priority_weighting_enabled: bool = True
    wanted_scheduler_backlog_reserve_pct: int = 50
    provider_budget_enabled: bool = True
    provider_budget_stretch_mode: str = "stretch"  # 'stretch' | 'burst' | 'off'
    provider_budget_burst_window_hours: int = 6
    # Reserve this % below each provider's declared limit. Must be a declared
    # field (not just read via getattr) so the first-run wizard's profile
    # presets (light=40, balanced=20, aggressive=10) actually persist —
    # UISettings uses extra="ignore", so an undeclared key is silently dropped
    # and the budget manager would always fall back to the 20 default.
    provider_budget_safety_margin_pct: int = 20
    scheduler_profile: str = "balanced"  # 'light' | 'balanced' | 'aggressive' | 'custom'
    scheduler_history_retention_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description=(
            "Keep scheduler job-run history for this many days before "
            "the scheduler_history_cleanup cron deletes old rows."
        ),
    )
    translation_events_retention_days: int = Field(
        default=90,
        ge=7,
        le=365,
        description="Keep translation_events rows for this many days.",
    )
    setup_wizard_completed: bool = False

    # Upgrade Scheduler
    upgrade_scan_interval_hours: int = 0  # 0 = disabled; user must opt in

    # Wanted Adaptive Backoff
    wanted_adaptive_backoff_enabled: bool = True
    wanted_backoff_base_hours: float = 1.0
    wanted_backoff_cap_hours: int = 168  # 7 days

    # Wanted Early Exit
    wanted_skip_srt_on_no_ass: bool = True  # Skip SRT steps if no ASS found in steps 1+2

    # Wanted Disk Safety-Valve — pause wanted_search when /config disk pressure is critical.
    # /config holds the application DB and download cache; pushing it over the cliff
    # corrupts both. Set to >=100.0 to disable the gate entirely.
    wanted_search_disk_pause_pct: float = Field(
        default=98.0,
        ge=50.0,
        le=100.0,
        description=(
            "Pause wanted_search when /config disk usage reaches this percentage. "
            "Set to 100.0 to disable."
        ),
    )

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
    remux_trash_dir: str = ".sublarr"  # Relative (to media_path) or absolute path
    remux_backup_retention_days: int = 7  # 0 = keep forever
    remux_use_reflink: bool = True  # CoW reflink on Btrfs/XFS for zero-cost backups
    remux_arr_pause_enabled: bool = True  # Pause Sonarr/Radarr during remux

    # Subtitle backup files (.bak.srt/.bak.ass)
    subtitle_bak_retention_days: int = 30  # 0 = keep forever

    # Circuit Breaker
    circuit_breaker_failure_threshold: int = 5  # Consecutive failures before opening
    circuit_breaker_cooldown_seconds: int = 300  # Seconds in OPEN before HALF_OPEN probe
    provider_auto_disable_cooldown_minutes: int = (
        30  # Minutes before auto-disabled provider re-enables
    )
    provider_rate_limit_throttle_minutes: int = 60  # Extended throttle on HTTP 429

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
    auto_cleanup_after_extract: bool = False
    auto_cleanup_keep_languages: str = ""  # Comma-separated ISO-639-1 codes to keep
    auto_cleanup_keep_formats: str = "any"  # "ass" | "srt" | "any"

    # Subtitle Trash / Soft-Delete
    subtitle_trash_retention_days: int = 30  # 0 = keep forever

    # AniDB Integration
    anidb_enabled: bool = True  # Enable AniDB ID resolution
    anidb_cache_ttl_days: int = 30  # Cache TTL for TVDB → AniDB mappings
    anidb_custom_field_name: str = "anidb_id"  # Custom field name in Sonarr
    anidb_fallback_to_mapping: bool = True  # Use cache/mapping as fallback

    # Database (PERF-01, PERF-02) — pool tuning, not connection (URL is in BootSettings)
    db_pool_size: int = 5  # SQLAlchemy pool_size (ignored for SQLite)
    db_pool_max_overflow: int = 10  # SQLAlchemy max_overflow (ignored for SQLite)
    db_pool_recycle: int = 3600  # Recycle connections after N seconds

    # Redis behaviour (URL is in BootSettings)
    redis_cache_enabled: bool = True  # Use Redis for provider cache
    # RQ requires a SEPARATE `python worker.py` process (see docker-compose.redis.yml).
    # Sublarr ships single-container without that worker, so RQ must NOT be the
    # default: enabling it without a worker leaves every queued job stuck in
    # `queued` forever (silent). Opt in only alongside the rq-worker service.
    redis_queue_enabled: bool = False  # Use Redis+RQ for job queue (needs worker.py)

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
    """Wartezeit in Sekunden vor dem Retry nach HTTP 423 (Locked) von Gestdown."""

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

    # Subtitle Health
    subtitle_health_enabled: bool = True
    subtitle_health_sweep_enabled: bool = True
    subtitle_health_auto_fix: bool = False

    @field_validator("cleanup_signs_removal_level")
    @classmethod
    def _validate_signs_level(cls, v: str) -> str:
        allowed = {"off", "signs", "signs_forced", "signs_forced_songs"}
        if v not in allowed:
            raise ValueError(f"cleanup_signs_removal_level must be one of {sorted(allowed)}")
        return v

    model_config = {"extra": "ignore"}


def _split_kwargs_by_membership(
    kwargs: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Route caller-supplied kwargs into the boot vs. ui buckets by field name."""
    boot_kwargs: dict[str, Any] = {}
    ui_kwargs: dict[str, Any] = {}
    unknown: list[str] = []
    for key, value in kwargs.items():
        if key in BootSettings.model_fields:
            boot_kwargs[key] = value
        elif key in UISettings.model_fields:
            ui_kwargs[key] = value
        else:
            unknown.append(key)
    if unknown:
        raise TypeError(
            f"Settings(): unknown field(s) {sorted(unknown)!r}. "
            "Add them to BootSettings (env-loadable) or UISettings (DB-only)."
        )
    return boot_kwargs, ui_kwargs


class Settings:
    """Composite Settings — boot fields from ENV, UI fields from DB.

    Attribute access is forwarded to the right side automatically:
        settings.api_key                  → boot
        settings.opensubtitles_api_key    → ui
    so the ~370 existing call-sites keep working unchanged.

    Construction:
        Settings()                        — defaults for everything
        Settings(boot=..., ui=...)        — explicit composition
        Settings(api_key="x", port=80, …) — auto-routed by field membership
                                            (used by tests and reload_settings)
    """

    def __init__(
        self,
        boot: BootSettings | None = None,
        ui: UISettings | None = None,
        **kwargs: Any,
    ) -> None:
        if kwargs and (boot is not None or ui is not None):
            raise TypeError("Settings(): pass either kwargs OR boot/ui, not both.")
        if kwargs:
            boot_kwargs, ui_kwargs = _split_kwargs_by_membership(kwargs)
            self._boot = BootSettings(**boot_kwargs)
            self._ui = UISettings(**ui_kwargs)
        else:
            self._boot = boot if boot is not None else BootSettings()
            self._ui = ui if ui is not None else UISettings()

    @property
    def boot(self) -> BootSettings:
        return self._boot

    @property
    def ui(self) -> UISettings:
        return self._ui

    def __getattr__(self, name: str) -> Any:
        # __getattr__ is only invoked when normal attribute lookup fails,
        # so this never recurses into _boot / _ui / boot / ui / methods.
        if name.startswith("_"):
            raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")
        if name in BootSettings.model_fields:
            return getattr(self._boot, name)
        if name in UISettings.model_fields:
            return getattr(self._ui, name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def model_dump(self) -> dict[str, Any]:
        """Flat dump merging boot + ui fields (backwards-compat surface)."""
        return {**self._boot.model_dump(), **self._ui.model_dump()}

    def model_copy(self, *, update: dict[str, Any] | None = None) -> "Settings":
        """Return a copy. ``update`` is split across boot + ui by field membership."""
        if not update:
            return Settings(boot=self._boot.model_copy(), ui=self._ui.model_copy())
        boot_update, ui_update = _split_kwargs_by_membership(update)
        return Settings(
            boot=self._boot.model_copy(update=boot_update)
            if boot_update
            else self._boot.model_copy(),
            ui=self._ui.model_copy(update=ui_update) if ui_update else self._ui.model_copy(),
        )

    # --- Instance methods (preserved from pre-split Settings) ---

    def get_database_url(self) -> str:
        """Get the SQLAlchemy database URL.

        Returns database_url if set, otherwise constructs a SQLite URL from db_path.
        """
        if self._boot.database_url:
            return self._boot.database_url
        return f"sqlite:///{self._boot.db_path}"

    def get_prompt_template(self) -> str:
        """Get the translation prompt template.

        Priority:
        1. Default prompt preset from database (if exists)
        2. prompt_template setting (if set)
        3. Auto-generated template
        """
        try:
            from db.translation import get_default_prompt_preset

            preset = get_default_prompt_preset()
            if preset and preset.get("prompt_template"):
                template = preset["prompt_template"]
                template = template.replace("{source_language}", self._ui.source_language_name)
                template = template.replace("{target_language}", self._ui.target_language_name)
                return template
        except Exception as exc:
            logger.debug("Could not load default prompt preset: %s", exc)

        if self._ui.prompt_template:
            return self._ui.prompt_template

        return (
            f"Translate these anime subtitle lines from {self._ui.source_language_name} to {self._ui.target_language_name}.\n"
            f"Return ONLY the translated lines, one per line, same count.\n"
            f"Preserve \\N exactly as \\N (hard line break).\n"
            f"Do NOT add numbering or prefixes to the output lines.\n\n"
        )

    def get_target_patterns(self, fmt: str = "ass") -> list[str]:
        """Get file patterns for detecting existing target language subtitles."""
        lang_tags = _get_language_tags(self._ui.target_language)
        return [f".{tag}.{fmt}" for tag in lang_tags]

    def get_source_patterns(self, fmt: str = "ass") -> list[str]:
        """Get file patterns for detecting existing source language subtitles."""
        lang_tags = _get_language_tags(self._ui.source_language)
        return [f".{tag}.{fmt}" for tag in lang_tags]

    def get_target_lang_tags(self) -> set[str]:
        """Get all language tags for the target language."""
        return _get_language_tags(self._ui.target_language)

    def get_source_lang_tags(self) -> set[str]:
        """Get all language tags for the source language."""
        return _get_language_tags(self._ui.source_language)

    def get_translation_config_hash(self, backend_name: str = "ollama") -> str:
        """SHA256 hash of backend+model+prompt+target_language (first 12 chars)."""
        if backend_name == "ollama":
            content = f"{backend_name}|{self._ui.ollama_model}|{self.get_prompt_template()[:50]}|{self._ui.target_language}"
        else:
            content = f"{backend_name}||{self._ui.target_language}"
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


def warn_on_ignored_env_vars() -> list[str]:
    """Scan os.environ for SUBLARR_<ui_field>=... and log a per-key warning.

    UI-only fields silently dropped any env value before this function existed;
    the warning makes the migration loud so users notice they need to move the
    setting into the UI (Settings → ...). Boot fields are unaffected.

    Returns the list of ignored env-var names (for tests / startup metrics).
    """
    ignored: list[str] = []
    ui_fields = UISettings.model_fields
    for env_name in os.environ:
        if not env_name.startswith("SUBLARR_"):
            continue
        field_name = env_name.removeprefix("SUBLARR_").lower()
        if field_name in ui_fields:
            ignored.append(env_name)
            logger.warning(
                "%s is no longer ENV-configurable as of v0.88.0-beta. "
                "Sublarr is now UI-first — set this in the Settings page. "
                "The env value has been ignored.",
                env_name,
            )
    return ignored


__all__ = [
    "BootSettings",
    "Settings",
    "UISettings",
    "_ALLOWED_BOOT_FIELDS",
    "warn_on_ignored_env_vars",
]
