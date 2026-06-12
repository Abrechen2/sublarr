"""Dedup scan + duplicate management routes.

Endpoints:
  POST   /api/v1/cleanup/scan              — start background dedup scan
  GET    /api/v1/cleanup/scan/status       — poll scan progress
  GET    /api/v1/cleanup/duplicates        — list duplicate groups
  POST   /api/v1/cleanup/duplicates/delete — delete selected duplicates
"""

import logging
import uuid

from flask import jsonify, request

from routes.cleanup import _scan_lock, _scan_state, bp
from services.background_tasks import submit_background

logger = logging.getLogger(__name__)


# ---- Deduplication Endpoints ---------------------------------------------------


@bp.route("/scan", methods=["POST"])
def start_scan():
    """Start a background deduplication scan.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Start dedup scan
      description: Starts a background scan of the media path to detect duplicate subtitle files via SHA-256 content hashing. Progress emitted via WebSocket.
      responses:
        200:
          description: Scan started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  scan_id:
                    type: string
        409:
          description: Scan already running
    """
    from config import get_settings
    from extensions import socketio

    with _scan_lock:
        if _scan_state["running"]:
            return jsonify(
                {
                    "status": "already_running",
                    "scan_id": _scan_state["scan_id"],
                }
            ), 409

        scan_id = str(uuid.uuid4())
        _scan_state["running"] = True
        _scan_state["scan_id"] = scan_id
        _scan_state["progress"] = 0
        _scan_state["total"] = 0
        _scan_state["result"] = None

    settings = get_settings()
    media_path = settings.media_path

    def _run_scan():
        from dedup_engine import scan_for_duplicates

        try:
            result = scan_for_duplicates(media_path, socketio=socketio)
            with _scan_lock:
                _scan_state["result"] = result
                _scan_state["running"] = False
            socketio.emit("scan_complete", result)
            logger.info("Dedup scan complete: %s", scan_id)
        except Exception as e:
            logger.error("Dedup scan failed: %s", e)
            with _scan_lock:
                _scan_state["result"] = {"error": str(e)}
                _scan_state["running"] = False
            socketio.emit("scan_error", {"error": str(e)})

    submit_background(_run_scan)

    return jsonify({"status": "scanning", "scan_id": scan_id})


@bp.route("/scan/status", methods=["GET"])
def scan_status():
    """Get current scan status.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Get scan status
      description: Returns whether a dedup scan is running, its progress, and the last result.
      responses:
        200:
          description: Scan status
          content:
            application/json:
              schema:
                type: object
                properties:
                  running:
                    type: boolean
                  scan_id:
                    type: string
                  result:
                    type: object
                    nullable: true
    """
    with _scan_lock:
        return jsonify(
            {
                "running": _scan_state["running"],
                "scan_id": _scan_state["scan_id"],
                "result": _scan_state["result"],
            }
        )


@bp.route("/duplicates", methods=["GET"])
def get_duplicates():
    """Get duplicate groups from the last scan.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: List duplicate groups
      description: Returns groups of subtitle files sharing identical content hashes. Each group contains 2+ files.
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
      responses:
        200:
          description: Duplicate groups
          content:
            application/json:
              schema:
                type: object
                properties:
                  groups:
                    type: array
                  total:
                    type: integer
    """
    from db.repositories.cleanup import CleanupRepository

    page = max(1, request.args.get("page", 1, type=int))
    per_page = max(1, min(request.args.get("per_page", 50, type=int), 200))

    repo = CleanupRepository()
    all_groups = repo.get_duplicate_groups()

    total = len(all_groups)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_groups[start:end]

    return jsonify(
        {
            "groups": paginated,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    )


@bp.route("/duplicates/delete", methods=["POST"])
def delete_duplicates():
    """Delete selected files from duplicate groups.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Delete duplicates
      description: Deletes selected duplicate files while enforcing keep-at-least-one per group safety guard. Returns 400 if any group would have no files remaining.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - groups
              properties:
                groups:
                  type: array
                  items:
                    type: object
                    required:
                      - keep
                      - delete
                    properties:
                      keep:
                        type: string
                        description: Path to the file to keep
                      delete:
                        type: array
                        items:
                          type: string
                        description: Paths of files to delete
      responses:
        200:
          description: Deletion results
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_deleted:
                    type: integer
                  total_bytes_freed:
                    type: integer
                  results:
                    type: array
        400:
          description: Safety guard violation (missing keep path or empty delete list)
    """
    from dedup_engine import delete_duplicates as do_delete

    data = request.get_json() or {}
    groups = data.get("groups", [])

    if not groups:
        return jsonify({"error": "groups array is required"}), 400

    # Validate all groups before any deletion
    for i, group in enumerate(groups):
        keep = group.get("keep", "")
        delete_paths = group.get("delete", [])

        if not keep:
            return jsonify({"error": f"Group {i}: keep path is required"}), 400
        if not delete_paths:
            return jsonify({"error": f"Group {i}: delete list is empty"}), 400
        if keep in delete_paths:
            return jsonify({"error": f"Group {i}: keep path '{keep}' is in the delete list"}), 400

    # Execute deletions
    results = []
    total_deleted = 0
    total_bytes_freed = 0

    for group in groups:
        result = do_delete(
            file_paths=group["delete"],
            keep_path=group["keep"],
        )
        results.append(result)
        total_deleted += result["deleted"]
        total_bytes_freed += result["bytes_freed"]

    return jsonify(
        {
            "total_deleted": total_deleted,
            "total_bytes_freed": total_bytes_freed,
            "results": results,
        }
    )
