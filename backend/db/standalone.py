"""Standalone mode database operations.

CRUD for watched_folders, standalone_series, standalone_movies, and metadata_cache.
All functions use _db_lock for thread safety and return dicts (not Row objects).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from db import get_db, _db_lock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watched Folders
# ---------------------------------------------------------------------------

def upsert_watched_folder(path: str, label: str = "", media_type: str = "auto",
                          enabled: bool = True) -> int:
    """Insert or update a watched folder by path.

    Args:
        path: Absolute filesystem path to the folder.
        label: Human-readable label for the folder.
        media_type: One of 'auto', 'tv', 'movie'.
        enabled: Whether the folder is actively watched.

    Returns:
        The row id of the inserted/updated folder.
    """
    now = datetime.utcnow().isoformat()
    enabled_int = 1 if enabled else 0
    db = get_db()

    with _db_lock:
        existing = db.execute(
            "SELECT id FROM watched_folders WHERE path=?", (path,)
        ).fetchone()

        if existing:
            row_id = existing[0]
            db.execute(
                """UPDATE watched_folders
                   SET label=?, media_type=?, enabled=?, updated_at=?
                   WHERE id=?""",
                (label, media_type, enabled_int, now, row_id),
            )
        else:
            cursor = db.execute(
                """INSERT INTO watched_folders
                   (path, label, media_type, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (path, label, media_type, enabled_int, now, now),
            )
            row_id = cursor.lastrowid
        db.commit()

    return row_id


def get_watched_folders(enabled_only: bool = True) -> list[dict]:
    """Return all watched folders, optionally filtered to enabled-only.

    Args:
        enabled_only: If True, only return folders where enabled=1.

    Returns:
        List of folder dicts.
    """
    db = get_db()
    with _db_lock:
        if enabled_only:
            rows = db.execute(
                "SELECT * FROM watched_folders WHERE enabled=1 ORDER BY path"
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM watched_folders ORDER BY path"
            ).fetchall()

    return [dict(row) for row in rows]


def get_watched_folder(folder_id: int) -> Optional[dict]:
    """Get a single watched folder by ID.

    Returns:
        Folder dict or None if not found.
    """
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM watched_folders WHERE id=?", (folder_id,)
        ).fetchone()

    if not row:
        return None
    return dict(row)


def delete_watched_folder(folder_id: int) -> bool:
    """Delete a watched folder by ID.

    Returns:
        True if a row was deleted, False if not found.
    """
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            "DELETE FROM watched_folders WHERE id=?", (folder_id,)
        )
        db.commit()

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Standalone Series
# ---------------------------------------------------------------------------

def upsert_standalone_series(title: str, folder_path: str, year: int = None,
                             tmdb_id: int = None, tvdb_id: int = None,
                             anilist_id: int = None, imdb_id: str = "",
                             poster_url: str = "", is_anime: bool = False,
                             episode_count: int = 0, season_count: int = 0,
                             metadata_source: str = "") -> int:
    """Insert or update a standalone series by folder_path.

    Args:
        title: Series title.
        folder_path: Absolute path to the series folder.
        year: Release year (optional).
        tmdb_id: TMDB ID (optional).
        tvdb_id: TVDB ID (optional).
        anilist_id: AniList ID (optional).
        imdb_id: IMDb ID string (optional).
        poster_url: URL to poster image (optional).
        is_anime: Whether the series is anime.
        episode_count: Total episode count.
        season_count: Total season count.
        metadata_source: Source of metadata (e.g., 'tmdb', 'tvdb').

    Returns:
        The row id of the inserted/updated series.
    """
    now = datetime.utcnow().isoformat()
    is_anime_int = 1 if is_anime else 0
    db = get_db()

    with _db_lock:
        existing = db.execute(
            "SELECT id FROM standalone_series WHERE folder_path=?", (folder_path,)
        ).fetchone()

        if existing:
            row_id = existing[0]
            db.execute(
                """UPDATE standalone_series
                   SET title=?, year=?, tmdb_id=?, tvdb_id=?, anilist_id=?,
                       imdb_id=?, poster_url=?, is_anime=?, episode_count=?,
                       season_count=?, metadata_source=?, updated_at=?
                   WHERE id=?""",
                (title, year, tmdb_id, tvdb_id, anilist_id, imdb_id,
                 poster_url, is_anime_int, episode_count, season_count,
                 metadata_source, now, row_id),
            )
        else:
            cursor = db.execute(
                """INSERT INTO standalone_series
                   (title, folder_path, year, tmdb_id, tvdb_id, anilist_id,
                    imdb_id, poster_url, is_anime, episode_count, season_count,
                    metadata_source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, folder_path, year, tmdb_id, tvdb_id, anilist_id,
                 imdb_id, poster_url, is_anime_int, episode_count,
                 season_count, metadata_source, now, now),
            )
            row_id = cursor.lastrowid
        db.commit()

    return row_id


def get_standalone_series(series_id: int = None) -> dict | list[dict]:
    """Get a single series by ID, or all series if no ID given.

    Args:
        series_id: Specific series ID, or None for all.

    Returns:
        Single series dict (if series_id), or list of all series dicts.
    """
    db = get_db()
    with _db_lock:
        if series_id is not None:
            row = db.execute(
                "SELECT * FROM standalone_series WHERE id=?", (series_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
        else:
            rows = db.execute(
                "SELECT * FROM standalone_series ORDER BY title"
            ).fetchall()
            return [dict(row) for row in rows]


def get_standalone_series_by_folder(folder_path: str) -> Optional[dict]:
    """Get a standalone series by its folder path.

    Returns:
        Series dict or None if not found.
    """
    db = get_db()
    with _db_lock:
        row = db.execute(
            "SELECT * FROM standalone_series WHERE folder_path=?", (folder_path,)
        ).fetchone()

    if not row:
        return None
    return dict(row)


def delete_standalone_series(series_id: int) -> bool:
    """Delete a standalone series by ID.

    Returns:
        True if a row was deleted, False if not found.
    """
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            "DELETE FROM standalone_series WHERE id=?", (series_id,)
        )
        db.commit()

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Standalone Movies
# ---------------------------------------------------------------------------

def upsert_standalone_movie(title: str, file_path: str, year: int = None,
                            tmdb_id: int = None, imdb_id: str = "",
                            poster_url: str = "", metadata_source: str = "") -> int:
    """Insert or update a standalone movie by file_path.

    Args:
        title: Movie title.
        file_path: Absolute path to the movie file.
        year: Release year (optional).
        tmdb_id: TMDB ID (optional).
        imdb_id: IMDb ID string (optional).
        poster_url: URL to poster image (optional).
        metadata_source: Source of metadata (e.g., 'tmdb').

    Returns:
        The row id of the inserted/updated movie.
    """
    now = datetime.utcnow().isoformat()
    db = get_db()

    with _db_lock:
        existing = db.execute(
            "SELECT id FROM standalone_movies WHERE file_path=?", (file_path,)
        ).fetchone()

        if existing:
            row_id = existing[0]
            db.execute(
                """UPDATE standalone_movies
                   SET title=?, year=?, tmdb_id=?, imdb_id=?, poster_url=?,
                       metadata_source=?, updated_at=?
                   WHERE id=?""",
                (title, year, tmdb_id, imdb_id, poster_url,
                 metadata_source, now, row_id),
            )
        else:
            cursor = db.execute(
                """INSERT INTO standalone_movies
                   (title, file_path, year, tmdb_id, imdb_id, poster_url,
                    metadata_source, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (title, file_path, year, tmdb_id, imdb_id, poster_url,
                 metadata_source, now, now),
            )
            row_id = cursor.lastrowid
        db.commit()

    return row_id


def get_standalone_movies(movie_id: int = None) -> dict | list[dict]:
    """Get a single movie by ID, or all movies if no ID given.

    Args:
        movie_id: Specific movie ID, or None for all.

    Returns:
        Single movie dict (if movie_id), or list of all movie dicts.
    """
    db = get_db()
    with _db_lock:
        if movie_id is not None:
            row = db.execute(
                "SELECT * FROM standalone_movies WHERE id=?", (movie_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)
        else:
            rows = db.execute(
                "SELECT * FROM standalone_movies ORDER BY title"
            ).fetchall()
            return [dict(row) for row in rows]


def delete_standalone_movie(movie_id: int) -> bool:
    """Delete a standalone movie by ID.

    Returns:
        True if a row was deleted, False if not found.
    """
    db = get_db()
    with _db_lock:
        cursor = db.execute(
            "DELETE FROM standalone_movies WHERE id=?", (movie_id,)
        )
        db.commit()

    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Metadata Cache
# ---------------------------------------------------------------------------

def cache_metadata(cache_key: str, provider: str, response_json: str,
                   ttl_days: int = 30) -> None:
    """Insert or replace a metadata cache entry with TTL.

    Args:
        cache_key: Unique cache key (e.g., 'tmdb:tv:12345').
        provider: Metadata provider name (e.g., 'tmdb', 'tvdb').
        response_json: JSON string of the cached response.
        ttl_days: Time-to-live in days before expiration.
    """
    now = datetime.utcnow()
    cached_at = now.isoformat()
    expires_at = (now + timedelta(days=ttl_days)).isoformat()
    db = get_db()

    with _db_lock:
        db.execute(
            """INSERT OR REPLACE INTO metadata_cache
               (cache_key, provider, response_json, cached_at, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (cache_key, provider, response_json, cached_at, expires_at),
        )
        db.commit()


def get_cached_metadata(cache_key: str) -> Optional[dict]:
    """Get a cached metadata entry if not expired.

    Args:
        cache_key: The cache key to look up.

    Returns:
        Dict with cache_key, provider, response_json, cached_at, expires_at
        or None if not found or expired.
    """
    now = datetime.utcnow().isoformat()
    db = get_db()

    with _db_lock:
        row = db.execute(
            "SELECT * FROM metadata_cache WHERE cache_key=? AND expires_at > ?",
            (cache_key, now),
        ).fetchone()

    if not row:
        return None
    return dict(row)


def cleanup_expired_cache() -> int:
    """Delete all expired metadata cache entries.

    Returns:
        Number of entries deleted.
    """
    now = datetime.utcnow().isoformat()
    db = get_db()

    with _db_lock:
        cursor = db.execute(
            "DELETE FROM metadata_cache WHERE expires_at <= ?", (now,)
        )
        db.commit()

    return cursor.rowcount
