"""Standalone mode service layer.

Extracted from routes/standalone.py so that route handlers are thin
HTTP-adapter shims and all business logic lives here.
"""

import logging
import os
import threading

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Module-level import seams (allow monkeypatching in tests)
try:
    from db.standalone import get_watched_folder  # noqa: F401
except ImportError:
    get_watched_folder = None  # type: ignore[assignment]

VALID_MEDIA_TYPES = ("auto", "tv", "movie")


# ---------------------------------------------------------------------------
# Folder validation
# ---------------------------------------------------------------------------


def validate_folder_input(data: dict) -> str | None:
    """Validate the data dict for adding/updating a watched folder.

    Returns:
        None if valid, or an error message string.
    """
    path = data.get("path", "").strip()
    media_type = data.get("media_type", "auto")

    if not path:
        return "path is required"

    if not os.path.isdir(path):
        return f"Directory does not exist: {path}"

    if media_type not in VALID_MEDIA_TYPES:
        return f"media_type must be one of: {', '.join(VALID_MEDIA_TYPES)}"

    return None


def validate_folder_exists_for_scan(folder_id: int) -> dict | None:
    """Look up a watched folder by ID.

    Returns:
        The folder dict, or None if not found.
    """
    import services.standalone_manager as _self

    return _self.get_watched_folder(folder_id)


# ---------------------------------------------------------------------------
# Series business logic
# ---------------------------------------------------------------------------


def enrich_series_list(series_list: list[dict]) -> list[dict]:
    """Add wanted_count to each series dict from the wanted_items table.

    Returns a new list with enriched copies (original dicts are mutated
    for compatibility with the existing caller contract — the dicts come
    from the DB layer and are not reused).
    """
    from db import get_db

    db = get_db()
    for series in series_list:
        row = db.execute(
            text(
                "SELECT COUNT(*) FROM wanted_items "
                "WHERE standalone_series_id=:sid AND status='wanted'"
            ),
            {"sid": series["id"]},
        ).fetchone()
        series["wanted_count"] = row[0] if row else 0
    return series_list


def enrich_series_detail(series: dict, series_id: int) -> dict:
    """Add wanted_items list to a series dict.

    Returns the same dict with a ``wanted_items`` key added.
    """
    from db import get_db

    db = get_db()
    rows = db.execute(
        text("SELECT * FROM wanted_items WHERE standalone_series_id=:sid ORDER BY file_path"),
        {"sid": series_id},
    ).fetchall()
    series["wanted_items"] = [dict(row._mapping) for row in rows]
    return series


def delete_series_cascade(series_id: int) -> None:
    """Delete wanted items for a series, then delete the series itself."""
    from db import get_db
    from db.standalone import delete_standalone_series

    db = get_db()
    db.execute(
        text("DELETE FROM wanted_items WHERE standalone_series_id=:sid"),
        {"sid": series_id},
    )
    db.commit()
    delete_standalone_series(series_id)


def scan_series_or_fallback(series_id: int) -> dict | None:
    """Re-scan a single standalone series via StandaloneScanner.

    Falls back to a status-refresh UPDATE only when the scanner module
    cannot be imported (e.g. test environments without watchdog/guessit).
    Returns the scanner's summary dict on success, ``None`` when the
    fallback path was used.
    """
    try:
        from standalone.scanner import get_scanner

        scanner = get_scanner()
        return scanner.scan_series(series_id)
    except ImportError as e:
        logger.warning("scan_series: scanner unavailable, using DB fallback: %s", e)

    from db import get_db

    db = get_db()
    db.execute(
        text(
            "UPDATE wanted_items SET status='wanted' WHERE standalone_series_id=:sid"
            " AND status NOT IN ('downloaded','blacklisted')"
        ),
        {"sid": series_id},
    )
    db.commit()
    return None


def refresh_series_metadata_sync(series_id: int) -> dict | None:
    """Re-resolve metadata for a standalone series (synchronous).

    Returns the updated series dict on success, or None if no metadata
    was found.

    Raises:
        ImportError: if MetadataResolver is unavailable.
        Exception: for other failures.
    """
    from db.standalone import get_standalone_series, upsert_standalone_series
    from metadata import MetadataResolver

    series = get_standalone_series(series_id)
    if not series:
        return None

    resolver = MetadataResolver()
    title = series.get("title", "")
    year = series.get("year")

    result = resolver.resolve_series(title, year=year, is_anime=bool(series.get("is_anime")))
    if not result:
        return None

    upsert_standalone_series(
        title=result.get("title", title),
        folder_path=series["folder_path"],
        year=result.get("year", year),
        tmdb_id=result.get("tmdb_id"),
        tvdb_id=result.get("tvdb_id"),
        anilist_id=result.get("anilist_id"),
        imdb_id=result.get("imdb_id", ""),
        poster_url=result.get("poster_url", ""),
        is_anime=bool(series.get("is_anime")),
        episode_count=series.get("episode_count", 0),
        season_count=series.get("season_count", 0),
        metadata_source=result.get("metadata_source", ""),
    )
    return get_standalone_series(series_id)


# ---------------------------------------------------------------------------
# Movie business logic
# ---------------------------------------------------------------------------


def enrich_movie_list(movies: list[dict]) -> list[dict]:
    """Add wanted_count to each movie dict from the wanted_items table."""
    from db import get_db

    db = get_db()
    for movie in movies:
        row = db.execute(
            text(
                "SELECT COUNT(*) FROM wanted_items "
                "WHERE standalone_movie_id=:mid AND status='wanted'"
            ),
            {"mid": movie["id"]},
        ).fetchone()
        movie["wanted_count"] = row[0] if row else 0
    return movies


def enrich_movie_detail(movie: dict, movie_id: int) -> dict:
    """Add wanted_count, profile_name, and profile_id to a single movie dict."""
    from db import get_db
    from db.profiles import get_default_profile, get_movie_profile

    db = get_db()
    row = db.execute(
        text(
            "SELECT COUNT(*) FROM wanted_items WHERE standalone_movie_id=:mid AND status='wanted'"
        ),
        {"mid": movie_id},
    ).fetchone()
    movie["wanted_count"] = row[0] if row else 0

    profile = get_movie_profile(movie_id)
    if not profile:
        profile = get_default_profile()
    movie["profile_name"] = profile.get("name", "Default") if profile else "Default"
    movie["profile_id"] = profile.get("id") if profile else None

    return movie


def get_radarr_movie_fallback(movie_id: int) -> dict | None:
    """Try to fetch a movie from Radarr as a fallback when not in standalone DB.

    Returns a normalised movie dict, or None.
    """
    try:
        from radarr_client import get_radarr_client

        radarr = get_radarr_client()
        if not radarr:
            return None
        radarr_movie = radarr.get_movie_by_id(movie_id)
        if not radarr_movie:
            return None
        poster = next(
            (
                img.get("remoteUrl", "")
                for img in radarr_movie.get("images", [])
                if img.get("coverType") == "poster"
            ),
            "",
        )
        return {
            "id": radarr_movie.get("id"),
            "title": radarr_movie.get("title"),
            "year": radarr_movie.get("year"),
            "poster_url": poster,
            "file_path": radarr_movie.get("path", ""),
            "wanted_count": 0,
            "source": "radarr",
        }
    except Exception as e:
        logger.debug("Radarr fallback failed for movie %d: %s", movie_id, e)
        return None


def delete_movie_cascade(movie_id: int) -> None:
    """Delete wanted items for a movie, then delete the movie itself."""
    from db import get_db
    from db.standalone import delete_standalone_movie

    db = get_db()
    db.execute(
        text("DELETE FROM wanted_items WHERE standalone_movie_id=:mid"),
        {"mid": movie_id},
    )
    db.commit()
    delete_standalone_movie(movie_id)


# ---------------------------------------------------------------------------
# Poster helpers
# ---------------------------------------------------------------------------


def resolve_poster_path(
    entity: dict, folder_key: str = "folder_path", use_parent: bool = False
) -> tuple[str | None, str | None, int | None]:
    """Validate and resolve a poster path for a series or movie.

    Args:
        entity: The series or movie dict (must contain ``poster_url``).
        folder_key: Dict key for the folder path (``folder_path`` for series,
            derived from ``file_path`` for movies).
        use_parent: If True, derive the folder from ``os.path.dirname(entity[folder_key])``.

    Returns:
        A tuple of ``(poster_path, error_message, http_status)``.
        If ``poster_path`` is not None the caller should serve that file.
        If ``error_message`` is not None the caller should return that error.
        Exactly one of the two will be non-None.
    """
    from security_utils import is_safe_path

    poster_path = entity.get("poster_url", "")
    if not poster_path:
        return None, "No local poster available", 404

    # Remote URL — signal the caller to redirect
    if poster_path.startswith(("http://", "https://")):
        return poster_path, None, None

    if not os.path.isfile(poster_path):
        return None, "No local poster available", 404

    base_folder = entity.get(folder_key, "")
    if use_parent and base_folder:
        base_folder = os.path.dirname(base_folder)
    elif not use_parent:
        # For series the poster may live one level above folder_path
        pass

    if base_folder:
        allowed = is_safe_path(poster_path, base_folder) or is_safe_path(
            poster_path, os.path.dirname(base_folder)
        )
        if not allowed:
            return None, "Forbidden", 403

    return poster_path, None, None


# ---------------------------------------------------------------------------
# Scanner control
# ---------------------------------------------------------------------------


def launch_full_scan(app) -> None:
    """Start a background full scan of all watched folders."""

    def _run_scan():
        with app.app_context():
            try:
                from standalone.scanner import get_scanner

                scanner = get_scanner()
                scanner.scan_all_folders()
            except Exception as e:
                logger.error("Standalone scan failed: %s", e)

    threading.Thread(target=_run_scan, daemon=True).start()


def launch_folder_scan(app, folder_id: int, folder_path: str) -> None:
    """Start a background scan of a single watched folder."""

    def _run_scan():
        with app.app_context():
            try:
                from standalone.scanner import get_scanner

                scanner = get_scanner()
                scanner.scan_folder(folder_path)
            except Exception as e:
                logger.error("Standalone scan for folder %d failed: %s", folder_id, e)

    threading.Thread(target=_run_scan, daemon=True).start()


def get_standalone_status() -> dict:
    """Return the current standalone-scan status from the StandaloneManager.

    Raises:
        ImportError: if the standalone module is unavailable.
    """
    from standalone import get_standalone_manager

    manager = get_standalone_manager()
    return manager.get_status()


def refresh_series_metadata_async(app, series_id: int) -> None:
    """Trigger an asynchronous metadata refresh for a standalone series."""

    def _run():
        with app.app_context():
            try:
                updated = refresh_series_metadata_sync(series_id)
                if updated:
                    logger.info("Metadata refreshed for series %d", series_id)
                else:
                    logger.warning("No metadata found for series %d", series_id)
            except Exception as e:
                logger.error("Metadata refresh failed for series %d: %s", series_id, e)

    threading.Thread(target=_run, daemon=True).start()
