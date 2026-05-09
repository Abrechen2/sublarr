"""Orphan subtitle scan + deletion routes.

Endpoints:
  POST   /api/v1/cleanup/orphaned/scan   — scan for orphaned subtitle files
  GET    /api/v1/cleanup/orphaned        — list results from last scan
  POST   /api/v1/cleanup/orphaned/delete — delete selected orphaned files
"""

import json
import logging

from flask import jsonify, request

from routes.cleanup import _orphan_lock, _orphan_state, bp

logger = logging.getLogger(__name__)


# ---- Orphaned Subtitle Endpoints ----------------------------------------------


@bp.route("/orphaned/scan", methods=["POST"])
def scan_orphaned():
    """Scan for orphaned subtitle files.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Scan for orphans
      description: Scans the media path for subtitle files whose parent media file no longer exists.
      responses:
        200:
          description: Orphan scan results
          content:
            application/json:
              schema:
                type: object
                properties:
                  orphaned:
                    type: array
                  count:
                    type: integer
        409:
          description: Scan already running
    """
    from config import get_settings
    from dedup_engine import scan_orphaned_subtitles

    with _orphan_lock:
        if _orphan_state["running"]:
            return jsonify({"status": "already_running"}), 409
        _orphan_state["running"] = True

    try:
        settings = get_settings()
        result = scan_orphaned_subtitles(settings.media_path)
        with _orphan_lock:
            _orphan_state["result"] = result
            _orphan_state["running"] = False

        return jsonify(
            {
                "orphaned": result,
                "count": len(result),
            }
        )
    except Exception as e:
        with _orphan_lock:
            _orphan_state["running"] = False
        logger.error("Orphan scan failed: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/orphaned", methods=["GET"])
def get_orphaned():
    """Get list of orphaned subtitle files from the last scan.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: List orphaned files
      description: Returns the results from the most recent orphan scan.
      responses:
        200:
          description: Orphaned files list
          content:
            application/json:
              schema:
                type: object
                properties:
                  orphaned:
                    type: array
                  count:
                    type: integer
    """
    with _orphan_lock:
        result = _orphan_state["result"]

    if result is None:
        return jsonify(
            {"orphaned": [], "count": 0, "message": "No scan results available. Run a scan first."}
        )

    return jsonify(
        {
            "orphaned": result,
            "count": len(result),
        }
    )


@bp.route("/orphaned/delete", methods=["POST"])
def delete_orphaned():
    """Delete selected orphaned subtitle files.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Delete orphaned files
      description: Deletes the specified orphaned subtitle files from disk and logs the operation.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_paths
              properties:
                file_paths:
                  type: array
                  items:
                    type: string
                  description: Paths of orphaned files to delete
      responses:
        200:
          description: Deletion results
          content:
            application/json:
              schema:
                type: object
                properties:
                  deleted:
                    type: integer
                  bytes_freed:
                    type: integer
                  errors:
                    type: array
        400:
          description: Missing file_paths
    """
    import os

    from config import get_settings
    from db.repositories.cleanup import CleanupRepository
    from services.cleanup_executors import _delete_or_trash, _media_path_reachable

    data = request.get_json() or {}
    file_paths = data.get("file_paths", [])
    permanent = bool(data.get("permanent_delete", False))

    if not file_paths:
        return jsonify({"error": "file_paths array is required"}), 400

    from security_utils import is_safe_path

    media_root_setting = get_settings().media_path
    if not _media_path_reachable(media_root_setting):
        # Same defence as the executors: a brief mount blip would
        # otherwise let the user trash every legitimate sidecar.
        return jsonify({"error": "media_path unreachable; aborting"}), 503

    media_root = os.path.realpath(media_root_setting)

    deleted = 0
    bytes_freed = 0
    errors = []

    for fp in file_paths:
        try:
            real_fp = os.path.realpath(fp)
            # Audit Gemini-2026-05-09 R6: replace the brittle
            # ``startswith(media_root + os.sep)`` boundary check with the
            # canonical ``is_safe_path`` helper. Same semantics on Linux,
            # but ``is_safe_path`` handles Windows separator quirks and
            # already-normalised inputs cleanly, and matches the policy
            # used everywhere else in the codebase. Argument order is
            # ``is_safe_path(file_path, base_dir)`` — same convention
            # already used by ``_validate_extract_target``.
            if not is_safe_path(real_fp, media_root):
                errors.append(f"Rejected (outside media dir): {fp}")
                continue

            if not os.path.isfile(real_fp):
                errors.append(f"File not found: {fp}")
                continue

            file_size = os.path.getsize(real_fp)
            # Audit E1-2: route now goes through the shared trash helper
            # so deletions are recoverable by default. Setting
            # ``permanent_delete=true`` in the request body keeps the
            # legacy hard-delete behaviour for callers that explicitly
            # want it.
            if not _delete_or_trash(real_fp, permanent=permanent):
                errors.append(f"Failed to {'delete' if permanent else 'trash'} {fp}")
                continue
            deleted += 1
            bytes_freed += file_size
            logger.info(
                "%s orphaned subtitle: %s (%d bytes)",
                "Deleted" if permanent else "Trashed",
                fp,
                file_size,
            )
        except Exception as e:
            errors.append(f"Failed to delete {fp}: {e}")

    # Log to cleanup history
    try:
        repo = CleanupRepository()
        repo.log_cleanup(
            action_type="orphaned_delete",
            files_processed=len(file_paths),
            files_deleted=deleted,
            bytes_freed=bytes_freed,
            details_json=json.dumps({"deleted_paths": file_paths[:50]}),
        )
    except Exception as e:
        logger.warning("Failed to log orphan cleanup: %s", e)

    return jsonify(
        {
            "deleted": deleted,
            "bytes_freed": bytes_freed,
            "errors": errors,
        }
    )
