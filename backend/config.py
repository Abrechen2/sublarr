"""Centralized configuration using Pydantic Settings.

All settings can be overridden via environment variables with the SUBLARR_ prefix,
or via a .env file. Example: SUBLARR_PORT=8080
"""

import os
import hashlib

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Sublarr application settings."""

    # General
    port: int = 5765
    api_key: str = ""  # Empty = no auth required
    log_level: str = "INFO"
    log_file: str = "/config/sublarr.log"
    media_path: str = "/media"
    db_path: str = "/config/sublarr.db"

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
    provider_search_timeout: int = 30  # Global timeout fallback (seconds)
    provider_cache_ttl_minutes: int = 5  # Cache TTL for provider search results
    provider_auto_prioritize: bool = True  # Auto-prioritize providers based on success rate
    provider_rate_limit_enabled: bool = True  # Enable rate limiting per provider

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

    # Path Mapping (remote → local, for when *arr apps run on different host)
    # Format: "remote_prefix=local_prefix" (semicolon-separated for multiple)
    # Example: "/data/media=Z:\Media;/anime=Z:\Anime"
    path_mapping: str = ""

    # Wanted System
    wanted_scan_interval_hours: int = 6  # 0 = disabled
    wanted_anime_only: bool = True
    wanted_anime_movies_only: bool = False  # Filter Radarr movies by anime tag (separate from wanted_anime_only)
    wanted_scan_on_startup: bool = True
    wanted_max_search_attempts: int = 3
    use_embedded_subs: bool = True  # Check embedded subtitle streams in MKV files

    # Upgrade System
    upgrade_enabled: bool = True
    upgrade_min_score_delta: int = 50
    upgrade_window_days: int = 7
    upgrade_prefer_ass: bool = True  # SRT->ASS always upgrade

    # Hearing Impaired
    hi_removal_enabled: bool = False

    # Webhook Automation
    webhook_delay_minutes: int = 5  # Wait time after Sonarr/Radarr webhook
    webhook_auto_scan: bool = True
    webhook_auto_search: bool = True
    webhook_auto_translate: bool = True

    # Wanted Search Scheduler
    wanted_search_interval_hours: int = 24  # 0 = disabled
    wanted_search_on_startup: bool = False
    wanted_search_max_items_per_run: int = 50

    # Notifications (Apprise)
    notification_urls_json: str = ""  # JSON array or newline-separated Apprise URLs
    notify_on_download: bool = True
    notify_on_upgrade: bool = True
    notify_on_batch_complete: bool = True
    notify_on_error: bool = True
    notify_manual_actions: bool = False

    # Circuit Breaker
    circuit_breaker_failure_threshold: int = 5  # Consecutive failures before opening
    circuit_breaker_cooldown_seconds: int = 60  # Seconds in OPEN before HALF_OPEN probe

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

    # AniDB Integration
    anidb_enabled: bool = True  # Enable AniDB ID resolution
    anidb_cache_ttl_days: int = 30  # Cache TTL for TVDB → AniDB mappings
    anidb_custom_field_name: str = "anidb_id"  # Custom field name in Sonarr
    anidb_fallback_to_mapping: bool = True  # Use cache/mapping as fallback

    model_config = {
        "env_prefix": "SUBLARR_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

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
                return preset["prompt_template"]
        except Exception:
            # Database might not be initialized yet, fall through
            pass
        
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

    def get_translation_config_hash(self) -> str:
        """SHA256 hash of model+prompt+target_language (first 12 chars)."""
        content = f"{self.ollama_model}|{self.get_prompt_template()}|{self.target_language}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def get_safe_config(self) -> dict:
        """Get config dict without sensitive values (API keys)."""
        data = self.model_dump()
        for key in list(data.keys()):
            if "api_key" in key or "key" in key.split("_"):
                if data[key]:
                    data[key] = "***configured***"
                else:
                    data[key] = ""
        return data


def map_path(path: str) -> str:
    """Map a remote file path to a local path using configured path mappings.

    Path mapping is configured via the SUBLARR_PATH_MAPPING setting:
    Format: "remote_prefix=local_prefix" (multiple pairs separated by semicolons)
    Example: "/data/media=/mnt/media;/anime=/share/anime"

    On Windows, forward slashes in the mapped path are converted to backslashes.
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
            mapped = local_prefix + path[len(remote_prefix):]
            if os.name == 'nt':
                mapped = mapped.replace("/", "\\")
            return mapped

    return path


# Language tag mapping (ISO 639-1 -> all variants)
_LANGUAGE_TAGS = {
    "de": {"de", "deu", "ger", "german"},
    "en": {"en", "eng", "english"},
    "fr": {"fr", "fra", "fre", "french"},
    "es": {"es", "spa", "spanish"},
    "it": {"it", "ita", "italian"},
    "pt": {"pt", "por", "portuguese"},
    "ru": {"ru", "rus", "russian"},
    "ja": {"ja", "jpn", "japanese"},
    "zh": {"zh", "zho", "chi", "chinese"},
    "ko": {"ko", "kor", "korean"},
    "ar": {"ar", "ara", "arabic"},
    "nl": {"nl", "nld", "dut", "dutch"},
    "pl": {"pl", "pol", "polish"},
    "sv": {"sv", "swe", "swedish"},
    "da": {"da", "dan", "danish"},
    "no": {"no", "nor", "norwegian"},
    "fi": {"fi", "fin", "finnish"},
    "cs": {"cs", "ces", "cze", "czech"},
    "hu": {"hu", "hun", "hungarian"},
    "tr": {"tr", "tur", "turkish"},
    "th": {"th", "tha", "thai"},
    "vi": {"vi", "vie", "vietnamese"},
    "id": {"id", "ind", "indonesian"},
    "ms": {"ms", "msa", "may", "malay"},
    "hi": {"hi", "hin", "hindi"},
}


def _get_language_tags(lang_code: str) -> set[str]:
    """Get all known tags for a language code."""
    return _LANGUAGE_TAGS.get(lang_code, {lang_code})


# Singleton settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the singleton Settings instance."""
    global _settings
    if _settings is None:
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
                    update[key] = value.lower() in ("true", "1", "yes") if isinstance(value, str) else bool(value)
                elif expected_type is int:
                    update[key] = int(value)
                elif expected_type is float:
                    update[key] = float(value)
                else:
                    update[key] = str(value).strip()
            except (ValueError, TypeError):
                continue  # Skip invalid values

        if update:
            _settings = base.model_copy(update=update)
        else:
            _settings = base
    else:
        _settings = base

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
        return [{
            "name": "Default",
            "url": settings.sonarr_url,
            "api_key": settings.sonarr_api_key,
            "path_mapping": settings.path_mapping,
        }]
    
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
        return [{
            "name": "Default",
            "url": settings.radarr_url,
            "api_key": settings.radarr_api_key,
            "path_mapping": settings.path_mapping,
        }]
    
    return []
