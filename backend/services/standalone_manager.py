"""Standalone mode service layer.

Extracted from routes/standalone.py so that route handlers are thin
HTTP-adapter shims and all business logic lives here.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

# Module-level import seams (allow monkeypatching in tests)
try:
    from db.standalone import get_watched_folder  # noqa: F401
except ImportError:
    get_watched_folder = None  # type: ignore[assignment]

VALID_MEDIA_TYPES = ("auto", "tv", "movie")


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


def launch_full_scan(app) -> None:
    """Start a background full scan of all watched folders."""

    def _run_scan():
        with app.app_context():
            try:
                from standalone.scanner import StandaloneScanner

                scanner = StandaloneScanner()
                scanner.scan_all_folders()
            except Exception as e:
                logger.error("Standalone scan failed: %s", e)

    threading.Thread(target=_run_scan, daemon=True).start()


def launch_folder_scan(app, folder_id: int, folder_path: str) -> None:
    """Start a background scan of a single watched folder."""

    def _run_scan():
        with app.app_context():
            try:
                from standalone.scanner import StandaloneScanner

                scanner = StandaloneScanner()
                scanner.scan_folder(folder_path)
            except Exception as e:
                logger.error("Standalone scan for folder %d failed: %s", folder_id, e)

    threading.Thread(target=_run_scan, daemon=True).start()


def get_standalone_status() -> dict:
    """Return the status from StandaloneManager, or a not-implemented placeholder.

    Raises:
        ImportError: if StandaloneManager is not yet available.
        Exception: for other unexpected failures.
    """
    from standalone import get_standalone_manager

    manager = get_standalone_manager()
    return manager.get_status()


def refresh_series_metadata_async(app, series_id: int) -> None:
    """Trigger an asynchronous metadata refresh for a standalone series."""

    def _run():
        with app.app_context():
            try:
                from metadata import MetadataResolver
                from db.standalone import get_standalone_series, upsert_standalone_series

                series = get_standalone_series(series_id)
                if not series:
                    logger.warning("Series %d not found for metadata refresh", series_id)
                    return

                resolver = MetadataResolver()
                title = series.get("title", "")
                year = series.get("year")

                result = resolver.resolve_series(
                    title, year=year, is_anime=bool(series.get("is_anime"))
                )
                if result:
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
                    logger.info("Metadata refreshed for series %d", series_id)
                else:
                    logger.warning("No metadata found for series %d", series_id)
            except Exception as e:
                logger.error("Metadata refresh failed for series %d: %s", series_id, e)

    threading.Thread(target=_run, daemon=True).start()
