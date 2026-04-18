"""Watched-folder CRUD for standalone mode."""

from __future__ import annotations

import logging
import os

from flask import jsonify, request

from routes.standalone import bp

logger = logging.getLogger(__name__)


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
