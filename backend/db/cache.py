"""FFprobe cache, episode history, and AniDB mapping operations -- delegating to SQLAlchemy repository."""


from db.repositories.cache import CacheRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = CacheRepository()
    return _repo


def get_ffprobe_cache(file_path: str, mtime: float) -> dict | None:
    """Get cached ffprobe data if file hasn't changed (mtime matches)."""
    return _get_repo().get_ffprobe_cache(file_path, mtime)


def set_ffprobe_cache(file_path: str, mtime: float, probe_data: dict):
    """Cache ffprobe data for a file."""
    return _get_repo().set_ffprobe_cache(file_path, mtime, probe_data)


def clear_ffprobe_cache(file_path: str = None):
    """Clear ffprobe cache. If file_path is given, only clear that entry."""
    return _get_repo().clear_ffprobe_cache(file_path)


def get_episode_history(file_path: str) -> list:
    """Get combined download + job history for a file path."""
    return _get_repo().get_episode_history(file_path)


# --- AniDB Mapping Operations ---

def get_anidb_mapping(tvdb_id: int) -> int | None:
    """Get cached AniDB ID for a TVDB ID."""
    return _get_repo().get_anidb_mapping(tvdb_id)


def save_anidb_mapping(tvdb_id: int, anidb_id: int, series_title: str = ""):
    """Save or update an AniDB mapping in the cache."""
    return _get_repo().save_anidb_mapping(tvdb_id, anidb_id, series_title)


def cleanup_old_anidb_mappings(days: int = 90) -> int:
    """Remove AniDB mappings older than specified days."""
    return _get_repo().cleanup_old_anidb_mappings(days)


def get_anidb_mapping_stats() -> dict:
    """Get statistics about AniDB mappings cache."""
    return _get_repo().get_anidb_mapping_stats()


# --- Provider Cache Operations (used by providers/__init__.py) ---

def get_cached_results(provider_name: str, query_hash: str, format_filter: str = None) -> str | None:
    """Get cached provider results if not expired."""
    return _get_repo().get_cached_results(provider_name, query_hash, format_filter)


def save_cache_results(provider_name: str, query_hash: str, results_json: str,
                       ttl_hours: int = 6, format_filter: str = None):
    """Cache provider search results."""
    return _get_repo().save_cache_results(provider_name, query_hash, results_json,
                                          ttl_hours, format_filter)


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return _get_repo().get_cache_stats()
