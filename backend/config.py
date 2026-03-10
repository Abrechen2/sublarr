"""Centralized configuration using Pydantic Settings.

All settings can be overridden via environment variables with the SUBLARR_ prefix,
or via a .env file. Example: SUBLARR_PORT=8080
"""

import hashlib
import logging
import os
import threading

logger = logging.getLogger(__name__)


from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Sublarr application settings."""

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

    # Dynamic Provider Timeouts (Phase 3)
    provider_dynamic_timeout_enabled: bool = True
    provider_dynamic_timeout_min_samples: int = 5
    provider_dynamic_timeout_multiplier: float = 3.0
    provider_dynamic_timeout_buffer_secs: float = 2.0
    provider_dynamic_timeout_min_secs: int = 5
    provider_dynamic_timeout_max_secs: int = 30

    # OpenSubtitles.com (API v2)
    opensubtitles_api_key: str = ""
    opensubtitles_username: str = ""
    opensubtitles_password: str = ""

    # Jimaku (anime subtitles)
    jimaku_api_key: str = ""

    # SubDL (Subscene successor)
    subdl_api_key: str = ""

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
    scan_metadata_max_workers: int = 4  # Parallel workers for batch metadata scans

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

    # Forced Subtitles
    forced_preference: str = "include"  # include | prefer | exclude | only

    # Webhook Automation
    webhook_delay_minutes: int = 5  # Wait time after Sonarr/Radarr webhook
    webhook_auto_scan: bool = True
    webhook_auto_search: bool = True
    webhook_auto_translate: bool = True

    # Video Sync (ffsubsync / alass)
    auto_sync_after_download: bool = False  # Auto-sync subtitle against video after download
    auto_sync_engine: str = "ffsubsync"  # Engine for auto-sync: "ffsubsync" | "alass"

    # Wanted Search Scheduler
    wanted_search_interval_hours: int = 24  # 0 = disabled
    wanted_search_on_startup: bool = False
    wanted_search_max_items_per_run: int = 50

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
    circuit_breaker_cooldown_seconds: int = 60  # Seconds in OPEN before HALF_OPEN probe
    provider_auto_disable_cooldown_minutes: int = (
        30  # Minutes before auto-disabled provider is re-enabled
    )

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
        7  # Days to keep trashed files before auto-purge (0 = keep forever)
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
        _JSON_BLOB_FIELDS = {
            "sonarr_instances_json",
            "radarr_instances_json",
            "media_servers_json",
        }
        _CREDENTIAL_SUBKEYS = {"api_key", "apiKey", "password", "token", "secret", "pin"}

        data = self.model_dump()
        for key in list(data.keys()):
            if (
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


def map_path(path: str) -> str:
    """Map a remote file path to a local path using configured path mappings.

    Path mapping is configured via the SUBLARR_PATH_MAPPING setting:
    Format: "remote_prefix=local_prefix" (multiple pairs separated by semicolons)
    Example: "/data/media=/mnt/media;/anime=/share/anime"

    On Windows, forward slashes in the mapped path are converted to backslashes.

    SECURITY NOTE: This function performs string-based prefix replacement only.
    Callers that serve or delete files MUST validate the mapped result with
    ``security_utils.is_safe_path(mapped, media_path)`` before using it,
    to guard against path traversal after mapping.
    """
    s = get_settings()
    mapping = s.path_mapping
    if not mapping:
        return path

    for pair in mapping.split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        remote_prefix, local_prefix = pair.split("=", 1)
        remote_prefix = remote_prefix.strip()
        local_prefix = local_prefix.strip()
        if not remote_prefix or not local_prefix:
            continue

        if path.startswith(remote_prefix):
            mapped = local_prefix + path[len(remote_prefix) :]
            if os.name == "nt":
                mapped = mapped.replace("/", "\\")
            return mapped

    return path


# Language tag mapping (ISO 639-1 -> all known file/metadata variants)
_LANGUAGE_TAGS = {
    # Western Europe
    "de": {"de", "deu", "ger", "german"},
    "en": {"en", "eng", "english"},
    "fr": {"fr", "fra", "fre", "french"},
    "es": {"es", "spa", "spanish"},
    "it": {"it", "ita", "italian"},
    "pt": {"pt", "por", "portuguese"},
    "nl": {"nl", "nld", "dut", "dutch"},
    "sv": {"sv", "swe", "swedish"},
    "da": {"da", "dan", "danish"},
    "no": {"no", "nor", "norwegian"},
    "fi": {"fi", "fin", "finnish"},
    "is": {"is", "isl", "ice", "icelandic"},
    "eu": {"eu", "eus", "baq", "basque"},
    "ca": {"ca", "cat", "catalan"},
    "gl": {"gl", "glg", "galician"},
    # Eastern Europe
    "pl": {"pl", "pol", "polish"},
    "cs": {"cs", "ces", "cze", "czech"},
    "sk": {"sk", "slk", "slo", "slovak"},
    "hu": {"hu", "hun", "hungarian"},
    "ro": {"ro", "ron", "rum", "romanian"},
    "bg": {"bg", "bul", "bulgarian"},
    "hr": {"hr", "hrv", "croatian"},
    "sr": {"sr", "srp", "serbian"},
    "sl": {"sl", "slv", "slovenian"},
    "bs": {"bs", "bos", "bosnian"},
    "mk": {"mk", "mkd", "macedonian"},
    "sq": {"sq", "alb", "sqi", "albanian"},
    "lt": {"lt", "lit", "lithuanian"},
    "lv": {"lv", "lav", "latvian"},
    "et": {"et", "est", "estonian"},
    "uk": {"uk", "ukr", "ukrainian"},
    "ru": {"ru", "rus", "russian"},
    # Caucasus / Central Asia
    "hy": {"hy", "hye", "arm", "armenian"},
    "ka": {"ka", "kat", "geo", "georgian"},
    "az": {"az", "aze", "azerbaijani"},
    "kk": {"kk", "kaz", "kazakh"},
    "uz": {"uz", "uzb", "uzbek"},
    # Middle East
    "ar": {"ar", "ara", "arabic"},
    "he": {"he", "heb", "hebrew"},
    "fa": {"fa", "per", "fas", "persian"},
    "tr": {"tr", "tur", "turkish"},
    # South / Southeast Asia
    "hi": {"hi", "hin", "hindi"},
    "bn": {"bn", "ben", "bengali"},
    "ur": {"ur", "urd", "urdu"},
    "ta": {"ta", "tam", "tamil"},
    "te": {"te", "tel", "telugu"},
    "ml": {"ml", "mal", "malayalam"},
    "kn": {"kn", "kan", "kannada"},
    "si": {"si", "sin", "sinhala"},
    "th": {"th", "tha", "thai"},
    "vi": {"vi", "vie", "vietnamese"},
    "id": {"id", "ind", "indonesian"},
    "ms": {"ms", "msa", "may", "malay"},
    "tl": {"tl", "fil", "tagalog", "filipino"},
    # East Asia
    "ja": {"ja", "jpn", "japanese"},
    "ko": {"ko", "kor", "korean"},
    "zh": {"zh", "zho", "chi", "chinese"},
    "zh-hans": {"zh-hans", "zhs", "chs", "chi-sim", "chinese simplified"},
    "zh-hant": {"zh-hant", "zht", "cht", "chi-tra", "chinese traditional"},
    "mn": {"mn", "mon", "mongolian"},
    # Other
    "el": {"el", "ell", "gre", "greek"},
    "af": {"af", "afr", "afrikaans"},
    "sw": {"sw", "swa", "swahili"},
}

# Ordered list of supported languages for the UI language picker
SUPPORTED_LANGUAGES: list[dict] = [
    {"code": "af", "name": "Afrikaans"},
    {"code": "sq", "name": "Albanian"},
    {"code": "ar", "name": "Arabic"},
    {"code": "hy", "name": "Armenian"},
    {"code": "az", "name": "Azerbaijani"},
    {"code": "eu", "name": "Basque"},
    {"code": "bn", "name": "Bengali"},
    {"code": "bs", "name": "Bosnian"},
    {"code": "bg", "name": "Bulgarian"},
    {"code": "ca", "name": "Catalan"},
    {"code": "zh", "name": "Chinese"},
    {"code": "zh-hans", "name": "Chinese (Simplified)"},
    {"code": "zh-hant", "name": "Chinese (Traditional)"},
    {"code": "hr", "name": "Croatian"},
    {"code": "cs", "name": "Czech"},
    {"code": "da", "name": "Danish"},
    {"code": "nl", "name": "Dutch"},
    {"code": "en", "name": "English"},
    {"code": "et", "name": "Estonian"},
    {"code": "tl", "name": "Filipino"},
    {"code": "fi", "name": "Finnish"},
    {"code": "fr", "name": "French"},
    {"code": "gl", "name": "Galician"},
    {"code": "ka", "name": "Georgian"},
    {"code": "de", "name": "German"},
    {"code": "el", "name": "Greek"},
    {"code": "he", "name": "Hebrew"},
    {"code": "hi", "name": "Hindi"},
    {"code": "hu", "name": "Hungarian"},
    {"code": "is", "name": "Icelandic"},
    {"code": "id", "name": "Indonesian"},
    {"code": "it", "name": "Italian"},
    {"code": "ja", "name": "Japanese"},
    {"code": "kn", "name": "Kannada"},
    {"code": "kk", "name": "Kazakh"},
    {"code": "ko", "name": "Korean"},
    {"code": "lv", "name": "Latvian"},
    {"code": "lt", "name": "Lithuanian"},
    {"code": "mk", "name": "Macedonian"},
    {"code": "ms", "name": "Malay"},
    {"code": "ml", "name": "Malayalam"},
    {"code": "mn", "name": "Mongolian"},
    {"code": "no", "name": "Norwegian"},
    {"code": "fa", "name": "Persian"},
    {"code": "pl", "name": "Polish"},
    {"code": "pt", "name": "Portuguese"},
    {"code": "ro", "name": "Romanian"},
    {"code": "ru", "name": "Russian"},
    {"code": "sr", "name": "Serbian"},
    {"code": "si", "name": "Sinhala"},
    {"code": "sk", "name": "Slovak"},
    {"code": "sl", "name": "Slovenian"},
    {"code": "es", "name": "Spanish"},
    {"code": "sw", "name": "Swahili"},
    {"code": "sv", "name": "Swedish"},
    {"code": "ta", "name": "Tamil"},
    {"code": "te", "name": "Telugu"},
    {"code": "th", "name": "Thai"},
    {"code": "tr", "name": "Turkish"},
    {"code": "uk", "name": "Ukrainian"},
    {"code": "ur", "name": "Urdu"},
    {"code": "uz", "name": "Uzbek"},
    {"code": "vi", "name": "Vietnamese"},
]


def _get_language_tags(lang_code: str) -> set[str]:
    """Get all known tags for a language code."""
    return _LANGUAGE_TAGS.get(lang_code, {lang_code})


# Singleton settings instance
_settings: Settings | None = None
_settings_lock = threading.Lock()


def get_settings() -> Settings:
    """Get or create the singleton Settings instance (thread-safe)."""
    global _settings
    if _settings is not None:
        return _settings
    with _settings_lock:
        if _settings is not None:
            return _settings
        _settings = Settings()
        return _settings


def reload_settings(overrides: dict = None) -> Settings:
    """Force reload settings from environment/file, with optional DB overrides.

    Args:
        overrides: Dict of key-value pairs (from DB config_entries) to apply
                   on top of the env/file settings.
    """
    global _settings
    base = Settings()
    new_settings = base

    if overrides:
        # Build update dict with correct types
        base_data = base.model_dump()
        update = {}
        for key, value in overrides.items():
            if key not in base_data:
                continue
            # Convert string values from DB to the correct field type
            expected_type = type(base_data[key])
            try:
                if expected_type is bool:
                    update[key] = (
                        value.lower() in ("true", "1", "yes")
                        if isinstance(value, str)
                        else bool(value)
                    )
                elif expected_type is int:
                    update[key] = int(value)
                elif expected_type is float:
                    update[key] = float(value)
                else:
                    update[key] = str(value).strip()
            except (ValueError, TypeError):
                continue  # Skip invalid values

        if update:
            new_settings = base.model_copy(update=update)

    with _settings_lock:
        _settings = new_settings

    return _settings


def get_sonarr_instances() -> list[dict]:
    """Get Sonarr instances from config, with fallback to legacy settings.

    Returns list of instance dicts: [{"name": "...", "url": "...", "api_key": "...", "path_mapping": "..."}]
    """
    import json

    settings = get_settings()

    # Try new multi-instance config
    if settings.sonarr_instances_json:
        try:
            instances = json.loads(settings.sonarr_instances_json)
            if isinstance(instances, list) and len(instances) > 0:
                return instances
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance config
    if settings.sonarr_url and settings.sonarr_api_key:
        return [
            {
                "name": "Default",
                "url": settings.sonarr_url,
                "api_key": settings.sonarr_api_key,
                "path_mapping": settings.path_mapping,
            }
        ]

    return []


def get_radarr_instances() -> list[dict]:
    """Get Radarr instances from config, with fallback to legacy settings.

    Returns list of instance dicts: [{"name": "...", "url": "...", "api_key": "...", "path_mapping": "..."}]
    """
    import json

    settings = get_settings()

    # Try new multi-instance config
    if settings.radarr_instances_json:
        try:
            instances = json.loads(settings.radarr_instances_json)
            if isinstance(instances, list) and len(instances) > 0:
                return instances
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance config
    if settings.radarr_url and settings.radarr_api_key:
        return [
            {
                "name": "Default",
                "url": settings.radarr_url,
                "api_key": settings.radarr_api_key,
                "path_mapping": settings.path_mapping,
            }
        ]

    return []


def get_media_server_instances() -> list[dict]:
    """Get media server instances from config, with fallback to legacy Jellyfin settings.

    Checks config_entries for media_servers_json first.
    If not found, auto-migrates legacy jellyfin_url + jellyfin_api_key to the new format.

    Returns list of instance dicts:
        [{"type": "jellyfin", "name": "...", "enabled": true, "url": "...", "api_key": "..."}]
    """
    import json

    from db.config import get_config_entry, save_config_entry

    # Try new multi-instance config from DB
    raw = get_config_entry("media_servers_json")
    if raw:
        try:
            instances = json.loads(raw)
            if isinstance(instances, list) and len(instances) > 0:
                return instances
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to legacy single-instance Jellyfin config
    settings = get_settings()
    if settings.jellyfin_url and settings.jellyfin_api_key:
        migrated = [
            {
                "type": "jellyfin",
                "name": "Jellyfin",
                "enabled": True,
                "url": settings.jellyfin_url,
                "api_key": settings.jellyfin_api_key,
            }
        ]
        # One-time migration: store back into config_entries
        try:
            save_config_entry("media_servers_json", json.dumps(migrated))
        except Exception:
            pass  # Migration is best-effort
        return migrated

    return []
