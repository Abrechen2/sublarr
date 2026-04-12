"""Standalone mode API endpoints.

Manages watched folders, standalone series/movies, metadata refresh,
and scanner control for folder-watch mode without Sonarr/Radarr.

Business logic lives in ``services.standalone_manager``; this module
contains only thin HTTP adapter handlers and OpenAPI docstrings.
"""

import logging
import os

from flask import Blueprint, current_app, jsonify, redirect, request, send_file

bp = Blueprint("standalone", __name__, url_prefix="/api/v1/standalone")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watched Folders
# ---------------------------------------------------------------------------


@bp.route("/folders", methods=["GET"])
def list_folders():
    """List all watched folders (enabled_only=False for settings display).
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: List watched folders
      description: Returns all configured watched folders for standalone mode, including disabled ones.
      responses:
        200:
          description: List of watched folders
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: integer
                    path:
                      type: string
                    label:
                      type: string
                    media_type:
                      type: string
                      enum: [auto, tv, movie]
                    enabled:
                      type: boolean
        500:
          description: Server error
    """
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
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Add a watched folder
      description: Adds a new directory to be watched for media files in standalone mode.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - path
              properties:
                path:
                  type: string
                  description: Absolute path to directory
                label:
                  type: string
                media_type:
                  type: string
                  enum: [auto, tv, movie]
                  default: auto
      responses:
        201:
          description: Folder added
          content:
            application/json:
              schema:
                type: object
        400:
          description: Invalid path or media_type
        500:
          description: Server error
    """
    from db.standalone import get_watched_folder, upsert_watched_folder

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
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Update a watched folder
      description: Updates an existing watched folder configuration.
      parameters:
        - in: path
          name: folder_id
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                path:
                  type: string
                label:
                  type: string
                media_type:
                  type: string
                  enum: [auto, tv, movie]
                enabled:
                  type: boolean
      responses:
        200:
          description: Updated folder
          content:
            application/json:
              schema:
                type: object
        400:
          description: Invalid media_type or path
        404:
          description: Folder not found
        500:
          description: Server error
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
        upsert_watched_folder(path=path, label=label, media_type=media_type, enabled=enabled)
        updated = get_watched_folder(folder_id)
        return jsonify(updated)
    except Exception as e:
        logger.error("Failed to update watched folder %d: %s", folder_id, e)
        return jsonify({"error": "Failed to update watched folder"}), 500


@bp.route("/folders/<int:folder_id>", methods=["DELETE"])
def delete_folder(folder_id):
    """Delete a watched folder.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Delete a watched folder
      description: Removes a watched folder from standalone mode.
      parameters:
        - in: path
          name: folder_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Folder deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        404:
          description: Folder not found
        500:
          description: Server error
    """
    from db.standalone import delete_watched_folder, get_watched_folder

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
    """List all standalone series with episode counts and wanted counts.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: List standalone series
      description: Returns all standalone series with episode counts and the number of wanted subtitle items.
      responses:
        200:
          description: List of standalone series
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
        500:
          description: Server error
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import enrich_series_list

    try:
        series_list = get_standalone_series()
        return jsonify(enrich_series_list(series_list))
    except Exception as e:
        logger.error("Failed to list standalone series: %s", e)
        return jsonify({"error": "Failed to list standalone series"}), 500


@bp.route("/series/<int:series_id>", methods=["GET"])
def get_series(series_id):
    """Get a single standalone series with its files and wanted status.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Get standalone series detail
      description: Returns a single standalone series with its associated wanted items.
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Series with wanted items
          content:
            application/json:
              schema:
                type: object
        404:
          description: Series not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import enrich_series_detail

    try:
        series = get_standalone_series(series_id)
        if not series:
            return jsonify({"error": "Series not found"}), 404

        return jsonify(enrich_series_detail(series, series_id))
    except Exception as e:
        logger.error("Failed to get standalone series %d: %s", series_id, e)
        return jsonify({"error": "Failed to get standalone series"}), 500


@bp.route("/series/<int:series_id>/poster", methods=["GET"])
def series_poster(series_id):
    """Serve the local poster image for a standalone series.

    Returns the local poster.jpg/poster.png found in the series folder
    during scanning. Falls back to 404 if no local poster is stored.
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import resolve_poster_path

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    poster_path, error, status = resolve_poster_path(
        series, folder_key="folder_path", use_parent=False
    )
    if error:
        return jsonify({"error": error}), status

    if poster_path.startswith(("http://", "https://")):
        return redirect(poster_path)

    try:
        return send_file(poster_path)
    except Exception as e:
        logger.error("Failed to serve poster for series %d: %s", series_id, e)
        return jsonify({"error": "Failed to serve poster"}), 500


@bp.route("/series/<int:series_id>", methods=["DELETE"])
def delete_series(series_id):
    """Delete a standalone series and its wanted items.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Delete standalone series
      description: Deletes a standalone series and cascades to remove associated wanted items.
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Series deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        404:
          description: Series not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import delete_series_cascade

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    try:
        delete_series_cascade(series_id)
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete standalone series %d: %s", series_id, e)
        return jsonify({"error": "Failed to delete standalone series"}), 500


# ---------------------------------------------------------------------------
# Standalone Movies
# ---------------------------------------------------------------------------


@bp.route("/movies", methods=["GET"])
def list_movies():
    """List all standalone movies with wanted status.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: List standalone movies
      description: Returns all standalone movies with wanted count information.
      responses:
        200:
          description: List of standalone movies
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import enrich_movie_list

    try:
        movies = get_standalone_movies()
        return jsonify(enrich_movie_list(movies))
    except Exception as e:
        logger.error("Failed to list standalone movies: %s", e)
        return jsonify({"error": "Failed to list standalone movies"}), 500


@bp.route("/movies/<int:movie_id>", methods=["GET"])
def get_movie(movie_id):
    """Get a single standalone movie by ID.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Get standalone movie
      description: Returns a single standalone movie by ID with wanted count.
      parameters:
        - in: path
          name: movie_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Movie found
          content:
            application/json:
              schema:
                type: object
        404:
          description: Movie not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import enrich_movie_detail, get_radarr_movie_fallback

    movie = get_standalone_movies(movie_id)
    if not movie:
        fallback = get_radarr_movie_fallback(movie_id)
        if fallback:
            return jsonify(fallback)
        return jsonify({"error": "Movie not found"}), 404

    try:
        return jsonify(enrich_movie_detail(movie, movie_id))
    except Exception as e:
        logger.error("Failed to get movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to get movie"}), 500


@bp.route("/movies/<int:movie_id>/poster", methods=["GET"])
def movie_poster(movie_id):
    """Serve the local poster image for a standalone movie."""
    from db.standalone import get_standalone_movies
    from services.standalone_manager import resolve_poster_path

    movie = get_standalone_movies(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    poster_path, error, status = resolve_poster_path(movie, folder_key="file_path", use_parent=True)
    if error:
        return jsonify({"error": error}), status

    if poster_path.startswith(("http://", "https://")):
        return redirect(poster_path)

    try:
        return send_file(poster_path)
    except Exception as e:
        logger.error("Failed to serve poster for movie %d: %s", movie_id, e)
        return jsonify({"error": "Failed to serve poster"}), 500


@bp.route("/movies/<int:movie_id>", methods=["DELETE"])
def delete_movie(movie_id):
    """Delete a standalone movie and its wanted items.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Delete standalone movie
      description: Deletes a standalone movie and cascades to remove associated wanted items.
      parameters:
        - in: path
          name: movie_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Movie deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        404:
          description: Movie not found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_movies
    from services.standalone_manager import delete_movie_cascade

    movie = get_standalone_movies(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    try:
        delete_movie_cascade(movie_id)
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
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Scan all watched folders
      description: Triggers a full scan of all enabled watched folders in a background thread. Returns immediately with 202.
      responses:
        202:
          description: Scan started
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
    """
    from services.standalone_manager import launch_full_scan

    app = current_app._get_current_object()
    launch_full_scan(app)
    return jsonify({"message": "Scan started"}), 202


@bp.route("/scan/<int:folder_id>", methods=["POST"])
def scan_folder(folder_id):
    """Scan a single watched folder.

    Runs in a background thread. Returns 202 immediately.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Scan a single folder
      description: Triggers a scan of a specific watched folder in a background thread. Returns immediately with 202.
      parameters:
        - in: path
          name: folder_id
          required: true
          schema:
            type: integer
      responses:
        202:
          description: Scan started
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
        404:
          description: Folder not found
    """
    from db.standalone import get_watched_folder
    from services.standalone_manager import launch_folder_scan

    folder = get_watched_folder(folder_id)
    if not folder:
        return jsonify({"error": "Folder not found"}), 404

    app = current_app._get_current_object()
    launch_folder_scan(app, folder_id, folder["path"])
    return jsonify({"message": f"Scan started for folder {folder_id}"}), 202


@bp.route("/status", methods=["GET"])
def get_status():
    """Get standalone mode status from StandaloneManager.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Get standalone mode status
      description: Returns the current standalone mode status including enabled state, watcher status, and counts.
      responses:
        200:
          description: Standalone status
          content:
            application/json:
              schema:
                type: object
                properties:
                  enabled:
                    type: boolean
                  watched_folders:
                    type: integer
                  series_count:
                    type: integer
                  movie_count:
                    type: integer
        500:
          description: Server error
    """
    from services.standalone_manager import get_standalone_status

    try:
        return jsonify(get_standalone_status())
    except ImportError:
        return jsonify(
            {
                "status": "not_implemented",
                "message": "StandaloneManager is not yet implemented",
            }
        ), 501
    except Exception as e:
        logger.error("Failed to get standalone status: %s", e)
        return jsonify({"error": "Failed to get standalone status"}), 500


# ---------------------------------------------------------------------------
# Series Scan
# ---------------------------------------------------------------------------


@bp.route("/series/<int:series_id>/scan", methods=["POST"])
def scan_series(series_id):
    """Trigger a re-scan of a single standalone series.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Re-scan standalone series
      description: Triggers a re-scan of file contents for a single standalone series.
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Scan started
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                  series_id:
                    type: integer
        404:
          description: Series not found
        500:
          description: Scan failed
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import scan_series_or_fallback

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    try:
        scan_series_or_fallback(series_id)
        return jsonify({"message": "Scan started", "series_id": series_id})
    except Exception as e:
        logger.error("Failed to scan series %d: %s", series_id, e)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@bp.route("/series/<int:series_id>/refresh-metadata", methods=["POST"])
def refresh_series_metadata(series_id):
    """Re-resolve metadata for a standalone series.

    Clears cache and re-fetches from TMDB/AniList/TVDB.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Standalone
      summary: Refresh series metadata
      description: Re-resolves metadata for a standalone series from external sources (TMDB, AniList, TVDB).
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Metadata refreshed
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  series:
                    type: object
        404:
          description: Series not found or no metadata found
        500:
          description: Server error
    """
    from db.standalone import get_standalone_series
    from services.standalone_manager import refresh_series_metadata_sync

    series = get_standalone_series(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    try:
        updated = refresh_series_metadata_sync(series_id)
        if updated:
            return jsonify({"success": True, "series": updated})
        return jsonify({"success": False, "message": "No metadata found"}), 404
    except ImportError as e:
        logger.warning("Metadata resolver not available: %s", e)
        return jsonify({"error": "Metadata resolver not available"}), 500
    except Exception as e:
        logger.error("Failed to refresh metadata for series %d: %s", series_id, e)
        return jsonify({"error": "Failed to refresh metadata"}), 500
