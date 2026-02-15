"""Standalone mode API endpoints.

Manages watched folders, standalone series/movies, metadata refresh,
and scanner control for folder-watch mode without Sonarr/Radarr.
"""

import logging
import os
import threading

from flask import Blueprint, request, jsonify

bp = Blueprint("standalone", __name__, url_prefix="/api/v1/standalone")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watched Folders
# ---------------------------------------------------------------------------

@bp.route("/folders", methods=["GET"])
def list_folders():
    """List all watched folders (enabled_only=False for settings display)."""
    from db.standalone import get_watched_folders

    try:
        folders = get_watched_folders(enabled_only=False)
        return jsonify(folders)
    except Exception as e:
        logger.error("Failed to list watched folders: %s", e)
        return jsonify({"error": "Failed to list watched folders"}), 500


@bp.route("/folders", methods=["POST"])
def add_folder():
    """Add a new watched folder.

    Body: {path: str, label?: str, media_type?: str}
    """
    from db.standalone import upsert_watched_folder, get_watched_folder

    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()

    if not path:
        return jsonify({"error": "path is required"}), 400

    if not os.path.isdir(path):
        return jsonify({"error": f"Directory does not exist: {path}"}), 400

    label = data.get("label", "")
    media_type = data.get("media_type", "auto")

    if media_type not in ("auto", "tv", "movie"):
        return jsonify({"error": "media_type must be one of: auto, tv, movie"}), 400

    try:
        folder_id = upsert_watched_folder(
            path=path, label=label, media_type=media_type, enabled=True
        )
        folder = get_watched_folder(folder_id)
        return jsonify(folder), 201
    except Exception as e:
        logger.error("Failed to add watched folder '%s': %s", path, e)
        return jsonify({"error": "Failed to add watched folder"}), 500


@bp.route("/folders/<int:folder_id>", methods=["PUT"])
def update_folder(folder_id):
    """Update a watched folder.

    Body: {path?: str, label?: str, media_type?: str, enabled?: bool}
    """
    from db.standalone import get_watched_folder, upsert_watched_folder

    folder = get_watched_folder(folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    data = request.get_json(silent=True) or {}

    path = data.get("path", folder["path"]).strip()
    label = data.get("label", folder.get("label", ""))
    media_type = data.get("media_type", folder.get("media_type", "auto"))
    enabled = data.get("enabled", bool(folder.get("enabled", 1)))

    if media_type not in ("auto", "tv", "movie"):
        return jsonify({"error": "media_type must be one of: auto, tv, movie"}), 400

    if path != folder["path"] and not os.path.isdir(path):
        return jsonify({"error": f"Directory does not exist: {path}"}), 400

    try:
        upsert_watched_folder(
            path=path, label=label, media_type=media_type, enabled=enabled
        )
        updated = get_watched_folder(folder_id)
        return jsonify(updated)
    except Exception as e:
        logger.error("Failed to update watched folder %d: %s", folder_id, e)
        return jsonify({"error": "Failed to update watched folder"}), 500


@bp.route("/folders/<int:folder_id>", methods=["DELETE"])
def delete_folder(folder_id):
    """Delete a watched folder."""
    from db.standalone import get_watched_folder, delete_watched_folder

    folder = get_watched_folder(folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    try:
        delete_watched_folder(folder_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete watched folder %d: %s", folder_id, e)
        return jsonify({"error": "Failed to delete watched folder"}), 500


# ---------------------------------------------------------------------------
# Standalone Series
# ---------------------------------------------------------------------------

@bp.route("/series", methods=["GET"])
def list_series():
    """List all standalone series with episode counts and wanted counts."""
    from db.standalone import get_standalone_series
    from db import get_db, _db_lock

    try:
        series_list = get_standalone_series()

        # Enrich with wanted counts from wanted_items table
        db = get_db()
        with _db_lock:
            for series in series_list:
                row = db.execute(
                    "SELECT COUNT(*) FROM wanted_items WHERE standalone_series_id=? AND status='wanted'",
                    (series["id"],),
                ).fetchone()
                series["wanted_count"] = row[0] if row else 0

        return jsonify(series_list)
    except Exception as e:
        logger.error("Failed to list standalone series: %s", e)
        return jsonify({"error": "Failed to list standalone series"}), 500


@bp.route("/series/<int:series_id>", methods=["GET"])
def get_series(series_id):
    """Get a single standalone series with its files and wanted status."""
    from db.standalone import get_standalone_series
    from db import get_db, _db_lock

    try:
        series = get_standalone_series(series_id)
        if not series:
            return jsonify({"error": "Series not found"}), 404

        # Get wanted items for this series
        db = get_db()
        with _db_lock:
            rows = db.execute(
                "SELECT * FROM wanted_items WHERE standalone_series_id=? ORDER BY file_path",
                (series_id,),
            ).fetchall()
        series["wanted_items"] = [dict(row) for row in rows]

        return jsonify(series)
    except Exception as e:
        logger.error("Failed to get standalone series %d: %s", series_id, e)
        return jsonify({"error": "Failed to get standalone series"}), 500


@bp.route("/series/<int:series_id>", methods=["DELETE"])
def delete_series(series_id):
    """Delete a standalone series and its wanted items."""
    from db.standalone import get_standalone_series, delete_standalone_series
    from db import get_db, _db_lock

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    try:
        # Delete associated wanted items first
        db = get_db()
        with _db_lock:
            db.execute(
                "DELETE FROM wanted_items WHERE standalone_series_id=?",
                (series_id,),
            )
            db.commit()

        delete_standalone_series(series_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete standalone series %d: %s", series_id, e)
        return jsonify({"error": "Failed to delete standalone series"}), 500


# ---------------------------------------------------------------------------
# Standalone Movies
# ---------------------------------------------------------------------------

@bp.route("/movies", methods=["GET"])
def list_movies():
    """List all standalone movies with wanted status."""
    from db.standalone import get_standalone_movies
    from db import get_db, _db_lock

    try:
        movies = get_standalone_movies()

        # Enrich with wanted status
        db = get_db()
        with _db_lock:
            for movie in movies:
                row = db.execute(
                    "SELECT COUNT(*) FROM wanted_items WHERE standalone_movie_id=? AND status='wanted'",
                    (movie["id"],),
                ).fetchone()
                movie["wanted_count"] = row[0] if row else 0

        return jsonify(movies)
    except Exception as e:
        logger.error("Failed to list standalone movies: %s", e)
        return jsonify({"error": "Failed to list standalone movies"}), 500


@bp.route("/movies/<int:movie_id>", methods=["DELETE"])
def delete_movie(movie_id):
    """Delete a standalone movie and its wanted items."""
    from db.standalone import get_standalone_movies, delete_standalone_movie
    from db import get_db, _db_lock

    movie = get_standalone_movies(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    try:
        # Delete associated wanted items first
        db = get_db()
        with _db_lock:
            db.execute(
                "DELETE FROM wanted_items WHERE standalone_movie_id=?",
                (movie_id,),
            )
            db.commit()

        delete_standalone_movie(movie_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete standalone movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to delete standalone movie"}), 500


# ---------------------------------------------------------------------------
# Scanner Control
# ---------------------------------------------------------------------------

@bp.route("/scan", methods=["POST"])
def scan_all():
    """Trigger a full scan of all watched folders.

    Runs in a background thread. Returns 202 immediately.
    """
    def _run_scan():
        try:
            from standalone.scanner import StandaloneScanner
            scanner = StandaloneScanner()
            scanner.scan_all_folders()
        except Exception as e:
            logger.error("Standalone scan failed: %s", e)

    threading.Thread(target=_run_scan, daemon=True).start()
    return jsonify({"message": "Scan started"}), 202


@bp.route("/scan/<int:folder_id>", methods=["POST"])
def scan_folder(folder_id):
    """Scan a single watched folder.

    Runs in a background thread. Returns 202 immediately.
    """
    from db.standalone import get_watched_folder

    folder = get_watched_folder(folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    def _run_scan():
        try:
            from standalone.scanner import StandaloneScanner
            scanner = StandaloneScanner()
            scanner.scan_folder(folder["path"])
        except Exception as e:
            logger.error("Standalone scan for folder %d failed: %s", folder_id, e)

    threading.Thread(target=_run_scan, daemon=True).start()
    return jsonify({"message": f"Scan started for folder {folder_id}"}), 202


@bp.route("/status", methods=["GET"])
def get_status():
    """Get standalone mode status from StandaloneManager."""
    try:
        from standalone import get_standalone_manager
        manager = get_standalone_manager()
        status = manager.get_status()
        return jsonify(status)
    except ImportError:
        # StandaloneManager not yet implemented -- return basic status
        from db.standalone import get_watched_folders, get_standalone_series, get_standalone_movies
        from config import get_settings

        settings = get_settings()
        folders = get_watched_folders(enabled_only=False)
        series = get_standalone_series()
        movies = get_standalone_movies()

        return jsonify({
            "enabled": getattr(settings, "standalone_enabled", False),
            "watched_folders": len(folders),
            "series_count": len(series) if isinstance(series, list) else 0,
            "movie_count": len(movies) if isinstance(movies, list) else 0,
        })
    except Exception as e:
        logger.error("Failed to get standalone status: %s", e)
        return jsonify({"error": "Failed to get standalone status"}), 500


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@bp.route("/series/<int:series_id>/refresh-metadata", methods=["POST"])
def refresh_series_metadata(series_id):
    """Re-resolve metadata for a standalone series.

    Clears cache and re-fetches from TMDB/AniList/TVDB.
    """
    from db.standalone import get_standalone_series

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    try:
        from metadata import MetadataResolver
        resolver = MetadataResolver()

        # Clear cached metadata for this series
        title = series.get("title", "")
        year = series.get("year")

        # Re-resolve metadata
        result = resolver.resolve_series(title, year=year, is_anime=bool(series.get("is_anime")))

        if result:
            # Update the series record with new metadata
            from db.standalone import upsert_standalone_series
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

            updated = get_standalone_series(series_id)
            return jsonify({"success": True, "series": updated})
        else:
            return jsonify({"success": False, "message": "No metadata found"}), 404

    except ImportError as e:
        logger.warning("Metadata resolver not available: %s", e)
        return jsonify({"error": "Metadata resolver not available"}), 500
    except Exception as e:
        logger.error("Failed to refresh metadata for series %d: %s", series_id, e)
        return jsonify({"error": "Failed to refresh metadata"}), 500
