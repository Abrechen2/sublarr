"""Standalone mode database operations -- delegating to SQLAlchemy repository."""

from db.repositories.standalone import StandaloneRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = StandaloneRepository()
    return _repo


# ---- Watched Folders ----


def upsert_watched_folder(
    path: str, label: str = "", media_type: str = "auto", enabled: bool = True
) -> int:
    """Insert or update a watched folder by path. Returns the row id."""
    if enabled:
        # Create or update through the repository
        result = _get_repo().create_watched_folder(path, label, media_type)
        return result.get("id", 0)
    else:
        # For disabled folders, use update_watched_folder if existing
        folders = _get_repo().get_watched_folders(enabled_only=False)
        for f in folders:
            if f["path"] == path:
                _get_repo().update_watched_folder(
                    f["id"], label=label, media_type=media_type, enabled=0
                )
                return f["id"]
        # Create as enabled then disable
        result = _get_repo().create_watched_folder(path, label, media_type)
        folder_id = result.get("id", 0)
        if folder_id:
            _get_repo().update_watched_folder(folder_id, enabled=0)
        return folder_id


def get_watched_folders(enabled_only: bool = True) -> list:
    """Return all watched folders, optionally filtered to enabled-only."""
    return _get_repo().get_watched_folders(enabled_only)


def get_watched_folder(folder_id: int) -> dict | None:
    """Get a single watched folder by ID."""
    return _get_repo().get_watched_folder(folder_id)


def delete_watched_folder(folder_id: int) -> bool:
    """Delete a watched folder by ID."""
    return _get_repo().delete_watched_folder(folder_id)


# ---- Standalone Series ----


def upsert_standalone_series(
    title: str,
    folder_path: str,
    year: int = None,
    tmdb_id: int = None,
    tvdb_id: int = None,
    anilist_id: int = None,
    imdb_id: str = "",
    poster_url: str = "",
    is_anime: bool = False,
    episode_count: int = 0,
    season_count: int = 0,
    metadata_source: str = "",
) -> int:
    """Insert or update a standalone series by folder_path. Returns the row id."""
    result = _get_repo().upsert_standalone_series(
        title,
        folder_path,
        year,
        tmdb_id,
        tvdb_id,
        anilist_id,
        imdb_id,
        poster_url,
        is_anime,
        episode_count,
        season_count,
        metadata_source,
    )
    return result.get("id", 0) if isinstance(result, dict) else result


def get_standalone_series(series_id: int = None):
    """Get a single series by ID, or all series if no ID given."""
    if series_id is not None:
        return _get_repo().get_standalone_series(series_id)
    else:
        return _get_repo().get_all_standalone_series()


def get_standalone_series_by_folder(folder_path: str) -> dict | None:
    """Get a standalone series by its folder path."""
    return _get_repo().get_standalone_series_by_folder(folder_path)


def delete_standalone_series(series_id: int) -> bool:
    """Delete a standalone series by ID."""
    return _get_repo().delete_standalone_series(series_id)


# ---- Standalone Movies ----


def upsert_standalone_movie(
    title: str,
    file_path: str,
    year: int = None,
    tmdb_id: int = None,
    imdb_id: str = "",
    poster_url: str = "",
    metadata_source: str = "",
) -> int:
    """Insert or update a standalone movie by file_path. Returns the row id."""
    result = _get_repo().upsert_standalone_movie(
        title, file_path, year, tmdb_id, imdb_id, poster_url, metadata_source
    )
    return result.get("id", 0) if isinstance(result, dict) else result


def get_standalone_movies(movie_id: int = None):
    """Get a single movie by ID, or all movies if no ID given."""
    if movie_id is not None:
        return _get_repo().get_standalone_movie(movie_id)
    else:
        return _get_repo().get_all_standalone_movies()


def delete_standalone_movie(movie_id: int) -> bool:
    """Delete a standalone movie by ID."""
    return _get_repo().delete_standalone_movie(movie_id)


# ---- Metadata Cache ----


def cache_metadata(cache_key: str, provider: str, response_json: str, ttl_days: int = 30) -> None:
    """Insert or replace a metadata cache entry with TTL."""
    return _get_repo().save_metadata_cache(cache_key, provider, response_json, ttl_days)


def get_cached_metadata(cache_key: str) -> dict | None:
    """Get a cached metadata entry if not expired."""
    return _get_repo().get_metadata_cache(cache_key)


def cleanup_expired_cache() -> int:
    """Delete all expired metadata cache entries."""
    return _get_repo().clear_expired_metadata_cache()


# ---- AniDB Mappings (via standalone repository) ----


def get_anidb_mapping(tvdb_id: int) -> dict | None:
    """Get cached AniDB mapping for a TVDB ID."""
    return _get_repo().get_anidb_mapping(tvdb_id)


def save_anidb_mapping(tvdb_id: int, anidb_id: int, series_title: str = ""):
    """Save or update an AniDB mapping."""
    return _get_repo().save_anidb_mapping(tvdb_id, anidb_id, series_title)


def clear_old_anidb_mappings(ttl_days: int = 90) -> int:
    """Remove AniDB mappings older than specified days."""
    return _get_repo().clear_old_anidb_mappings(ttl_days)
