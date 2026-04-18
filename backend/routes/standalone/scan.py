"""Scanner control for standalone mode: trigger full or per-folder scans + status."""

from __future__ import annotations

import logging

from flask import current_app, jsonify

from routes.standalone import bp

logger = logging.getLogger(__name__)


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
