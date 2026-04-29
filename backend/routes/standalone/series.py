"""Standalone series endpoints: list, detail, poster, delete, scan, metadata refresh."""

from __future__ import annotations

import logging

from flask import jsonify, redirect, send_file

from routes.standalone import bp

logger = logging.getLogger(__name__)


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
        summary = scan_series_or_fallback(series_id)
        response = {"message": "Scan completed", "series_id": series_id}
        if summary:
            response["summary"] = summary
        return jsonify(response)
    except Exception as e:
        logger.error("Failed to scan series %d: %s", series_id, e)
        return jsonify({"error": str(e)}), 500


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
