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

__all__ = [
    # Base
    "BaseRepository",
    # Repositories
    "ConfigRepository",
    "BlacklistRepository",
    "CacheRepository",
    "PluginRepository",
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
