"""Watched-folder CRUD for standalone mode."""

from __future__ import annotations

import logging
import os

from flask import current_app, jsonify, request

from routes.standalone import bp

logger = logging.getLogger(__name__)

# System paths that must never be used as a watched folder. Even on a
# single-tenant homelab API a typo ("/" or "/etc") would walk the entire
# container with ``followlinks=True`` and persist arbitrary file paths
# into ``wanted_items.file_path``. The blocklist is intentionally
# conservative — we don't strictly require paths under ``media_path``
# (some homelabs mount media at non-default locations), but we refuse the
# obviously-wrong roots.
_FORBIDDEN_FOLDER_ROOTS = (
    "/",
    "/etc",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/boot",
    "/root",
    "/var/log",
    "/var/run",
    "/var/lib",
    "/usr",
    "/lib",
    "/lib64",
    "/sbin",
    "/bin",
)


def _validate_watched_folder_path(path: str) -> str | None:
    """Return an error message if ``path`` is unsafe to register as a watched
    folder, otherwise None.

    Checks (in order):
      1. ``os.path.isdir`` — folder must exist
      2. realpath canonicalisation — symlinks resolved up-front
      3. forbidden-roots blocklist — refuses ``/``, ``/etc``, etc.
      4. ``is_safe_path`` against the configured ``media_path`` when set —
         soft check, only logged on miss; doesn't reject (homelab users
         frequently mount media outside the default).
    """
    # Reject the literal forbidden roots even before isdir-check so the
    # test passes on every platform (on Windows ``os.path.isdir("/")``
    # returns True for the C: drive root, which would let the canonical
    # check below skip the blocklist).
    raw = path.replace("\\", "/").rstrip("/") or "/"
    if raw in _FORBIDDEN_FOLDER_ROOTS:
        return f"Refusing forbidden system path: {path}"

    if not os.path.isdir(path):
        return f"Directory does not exist: {path}"

    canonical = os.path.realpath(path).replace("\\", "/")
    norm = canonical.rstrip("/") or "/"

    # Forbidden roots — exact match or direct child of one
    for root in _FORBIDDEN_FOLDER_ROOTS:
        if norm == root:
            return f"Refusing forbidden system path: {path}"
        if root != "/" and norm.startswith(root + "/"):
            return f"Refusing forbidden system path: {path}"

    # Soft boundary check against media_path
    try:
        from config import get_settings
        from security_utils import is_safe_path

        media_path = getattr(get_settings(), "media_path", "")
        if media_path and not is_safe_path(canonical, media_path):
            logger.info(
                "Watched folder %s is outside media_path=%s — accepted but "
                "flagged. Verify this is intentional.",
                canonical,
                media_path,
            )
    except Exception:
        # Soft check; never block on this path.
        logger.debug("Soft media_path boundary check skipped", exc_info=True)
    return None


def _hot_reload_standalone() -> None:
    """Hot-restart the StandaloneManager so the watcher picks up the new
    folder list immediately. Failures are logged but never block the
    HTTP response — the folder change is already persisted in the DB."""
    try:
        from extensions import socketio as _sock
        from standalone import reload_standalone_manager

        reload_standalone_manager(socketio=_sock, app=current_app._get_current_object())
    except Exception as exc:
        logger.warning("Standalone manager hot-reload failed: %s", exc)


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

    err = _validate_watched_folder_path(path)
    if err is not None:
        return jsonify({"error": err}), 400

    # Normalize symlinks to their real target so the scanner walks the
    # canonical path (avoids surprises like "I added /media but it's a
    # symlink to /mnt/raid" — both UI list and scanner agree).
    path = os.path.realpath(path)

    label = data.get("label", "")
    media_type = data.get("media_type", "auto")

    if media_type not in ("auto", "tv", "movie"):
        return jsonify({"error": "media_type must be one of: auto, tv, movie"}), 400

    try:
        folder_id = upsert_watched_folder(
            path=path, label=label, media_type=media_type, enabled=True
        )
        folder = get_watched_folder(folder_id)
        _hot_reload_standalone()
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

    if path != folder["path"]:
        err = _validate_watched_folder_path(path)
        if err is not None:
            return jsonify({"error": err}), 400
        # Same realpath normalization as POST so an updated symlinked
        # path becomes the canonical target.
        path = os.path.realpath(path)

    try:
        upsert_watched_folder(path=path, label=label, media_type=media_type, enabled=enabled)
        updated = get_watched_folder(folder_id)
        _hot_reload_standalone()
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
        _hot_reload_standalone()
        return jsonify({"success": True})
    except Exception as e:
        logger.error("Failed to delete watched folder %d: %s", folder_id, e)
        return jsonify({"error": "Failed to delete watched folder"}), 500
