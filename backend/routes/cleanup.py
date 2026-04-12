"""Cleanup API endpoints -- dedup scan, orphan detection, rules, stats, history.

Blueprint: /api/v1/cleanup

Provides deduplication scanning, duplicate/orphan management, configurable
cleanup rules with manual execution, disk space statistics, and a dry-run
preview mode for safe operation.
"""

import json
import logging
import threading
import uuid

from flask import Blueprint, jsonify, request

from error_utils import handle_api_error

bp = Blueprint("cleanup", __name__, url_prefix="/api/v1/cleanup")
logger = logging.getLogger(__name__)

# Module-level scan state (same pattern as wanted_scanner)
_scan_state = {
    "running": False,
    "scan_id": None,
    "progress": 0,
    "total": 0,
    "result": None,
}
_scan_lock = threading.Lock()

# Module-level orphan state
_orphan_state = {
    "running": False,
    "result": None,
}
_orphan_lock = threading.Lock()


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

    thread = threading.Thread(target=_run_scan, daemon=True)
    thread.start()

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

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

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

    data = request.get_json() or {}
    file_paths = data.get("file_paths", [])

    if not file_paths:
        return jsonify({"error": "file_paths array is required"}), 400

    media_root = os.path.realpath(get_settings().media_path)

    deleted = 0
    bytes_freed = 0
    errors = []

    for fp in file_paths:
        try:
            real_fp = os.path.realpath(fp)
            if not real_fp.startswith(media_root + os.sep):
                errors.append(f"Rejected (outside media dir): {fp}")
                continue

            if not os.path.isfile(real_fp):
                errors.append(f"File not found: {fp}")
                continue

            file_size = os.path.getsize(real_fp)
            os.remove(real_fp)
            deleted += 1
            bytes_freed += file_size
            logger.info("Deleted orphaned subtitle: %s (%d bytes)", fp, file_size)
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


# ---- Cleanup Rules Endpoints ---------------------------------------------------


@bp.route("/rules", methods=["GET"])
def list_rules():
    """List all cleanup rules.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: List cleanup rules
      description: Returns all configured cleanup rules.
      responses:
        200:
          description: Cleanup rules
          content:
            application/json:
              schema:
                type: object
                properties:
                  rules:
                    type: array
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    rules = repo.get_rules()
    return jsonify({"rules": rules})


@bp.route("/rules", methods=["POST"])
def create_rule():
    """Create a new cleanup rule.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Create cleanup rule
      description: Creates a new cleanup rule with the specified type and configuration.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - name
                - rule_type
              properties:
                name:
                  type: string
                  maxLength: 100
                rule_type:
                  type: string
                  enum: [dedup, orphaned, old_backups]
                config_json:
                  type: string
                  default: "{}"
                enabled:
                  type: boolean
                  default: true
      responses:
        201:
          description: Rule created
        400:
          description: Invalid parameters
    """
    from db.repositories.cleanup import CleanupRepository

    data = request.get_json() or {}
    name = data.get("name", "").strip()
    rule_type = data.get("rule_type", "").strip()
    config_json = data.get("config_json", "{}")
    enabled = data.get("enabled", True)
    schedule = data.get("schedule", "manual")

    if not name:
        return jsonify({"error": "name is required"}), 400

    valid_types = {
        "dedup",
        "orphaned",
        "old_backups",
        "language_filter",
        "format_upgrade",
        "orphan_files",
        "orphan_db",
    }
    if rule_type not in valid_types:
        return jsonify({"error": f"rule_type must be one of: {sorted(valid_types)}"}), 400

    # Validate config_json is valid JSON
    try:
        json.loads(config_json) if isinstance(config_json, str) else config_json
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "config_json must be valid JSON"}), 400

    if isinstance(config_json, dict):
        config_json = json.dumps(config_json)

    repo = CleanupRepository()
    rule = repo.create_rule(
        name=name,
        rule_type=rule_type,
        config_json=config_json,
        enabled=enabled,
        schedule=schedule,
    )

    return jsonify(rule), 201


@bp.route("/rules/<int:rule_id>", methods=["PUT"])
def update_rule(rule_id: int):
    """Update a cleanup rule.
    ---
    put:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Update cleanup rule
      description: Updates an existing cleanup rule.
      parameters:
        - in: path
          name: rule_id
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
                name:
                  type: string
                rule_type:
                  type: string
                  enum: [dedup, orphaned, old_backups, language_filter, format_upgrade, orphan_files, orphan_db]
                config_json:
                  type: string
                enabled:
                  type: boolean
                schedule:
                  type: string
                  enum: [manual, daily, weekly, after_scan]
      responses:
        200:
          description: Rule updated
        404:
          description: Rule not found
    """
    from db.repositories.cleanup import CleanupRepository

    data = request.get_json() or {}

    # Validate config_json if provided
    if "config_json" in data:
        cfg = data["config_json"]
        try:
            json.loads(cfg) if isinstance(cfg, str) else cfg
        except (json.JSONDecodeError, TypeError):
            return jsonify({"error": "config_json must be valid JSON"}), 400
        if isinstance(cfg, dict):
            data["config_json"] = json.dumps(cfg)

    repo = CleanupRepository()
    result = repo.update_rule(rule_id, **data)

    if result is None:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify(result)


@bp.route("/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule(rule_id: int):
    """Delete a cleanup rule.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Delete cleanup rule
      description: Deletes a cleanup rule by ID.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Rule deleted
        404:
          description: Rule not found
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()
    deleted = repo.delete_rule(rule_id)

    if not deleted:
        return jsonify({"error": "Rule not found"}), 404

    return jsonify({"status": "deleted", "id": rule_id})


@bp.route("/rules/<int:rule_id>/run", methods=["POST"])
@handle_api_error("Rule execution failed")
def run_rule(rule_id: int):
    """Execute a cleanup rule manually.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Run cleanup rule
      description: Manually executes a cleanup rule and returns the result.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Rule execution result
        404:
          description: Rule not found
        500:
          description: Execution error
    """
    from extensions import socketio
    from services.cleanup_rule_runner import execute_rule

    try:
        result = execute_rule(rule_id, socketio=socketio)
        return jsonify(result)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        return jsonify({"error": str(e)}), code
    except Exception as e:
        logger.error("Rule %d failed: %s", rule_id, e)
        return jsonify({"error": str(e)}), 500


@bp.route("/rules/<int:rule_id>/preview", methods=["POST"])
def preview_rule_endpoint(rule_id: int):
    """Dry-run a cleanup rule — return what would be deleted without deleting.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Preview cleanup rule
      description: Runs a cleanup rule in dry-run mode and returns what would be affected without making any changes.
      parameters:
        - in: path
          name: rule_id
          required: true
          schema:
            type: integer
      responses:
        200:
          description: Preview results
        404:
          description: Rule not found
        400:
          description: Preview not supported for rule type
        500:
          description: Preview error
    """
    from services.cleanup_rule_runner import preview_rule

    try:
        result = preview_rule(rule_id)
        return jsonify(result)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        return jsonify({"error": str(e)}), code
    except Exception as e:
        logger.error("Preview for rule %d failed: %s", rule_id, e)
        return jsonify({"error": str(e)}), 500


# ---- Dashboard Endpoints -------------------------------------------------------


@bp.route("/stats", methods=["GET"])
@handle_api_error("Cleanup stats failed")
def cleanup_stats():
    """Get disk space analysis and cleanup statistics.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Cleanup statistics
      description: Returns comprehensive disk space analysis including total files, sizes, duplicate waste, format breakdown, and cleanup trends.
      responses:
        200:
          description: Disk space analysis
          content:
            application/json:
              schema:
                type: object
                properties:
                  disk:
                    type: object
                  cleanup:
                    type: object
    """
    from db.repositories.cleanup import CleanupRepository

    repo = CleanupRepository()

    disk_stats = repo.get_disk_stats()

    # Reshape by_format from dict to array expected by the frontend DiskSpaceStats type
    raw_by_format = disk_stats.get("by_format", {})
    by_format = [
        {"format": fmt, "count": v["count"], "size_bytes": v["size"]}
        for fmt, v in raw_by_format.items()
    ]

    return jsonify(
        {
            "total_files": disk_stats.get("total_files", 0),
            "total_size_bytes": disk_stats.get("total_size_bytes", 0),
            "by_format": by_format,
            "duplicate_files": disk_stats.get("duplicate_count", 0),
            "duplicate_size_bytes": disk_stats.get("duplicate_size_bytes", 0),
            "potential_savings_bytes": disk_stats.get("potential_savings_bytes", 0),
            "trends": disk_stats.get("recent_cleanups", []),
        }
    )


@bp.route("/history", methods=["GET"])
@handle_api_error("Cleanup history failed")
def cleanup_history():
    """Get cleanup execution history.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Cleanup history
      description: Returns paginated cleanup execution history with operation details.
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
          description: Cleanup history
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                  total:
                    type: integer
                  page:
                    type: integer
                  per_page:
                    type: integer
    """
    from db.repositories.cleanup import CleanupRepository

    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)

    repo = CleanupRepository()
    result = repo.get_history(page, per_page)
    return jsonify(result)


# ---- Preview Endpoint ----------------------------------------------------------


@bp.route("/preview", methods=["POST"])
def preview_cleanup():
    """Preview what a cleanup operation would do without executing.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Cleanup
      summary: Preview cleanup operation
      description: Returns a list of files that would be affected by the specified cleanup action without actually modifying anything.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - action
              properties:
                action:
                  type: string
                  enum: [dedup, orphaned, rule]
                params:
                  type: object
      responses:
        200:
          description: Preview results
          content:
            application/json:
              schema:
                type: object
                properties:
                  action:
                    type: string
                  affected_files:
                    type: array
                  total_size:
                    type: integer
        400:
          description: Invalid action
    """
    from services.cleanup_rule_runner import preview_cleanup_action

    data = request.get_json() or {}
    action = data.get("action", "")
    params = data.get("params", {})

    try:
        result = preview_cleanup_action(action, params)
        return jsonify(result)
    except ValueError as e:
        code = 404 if "not found" in str(e) else 400
        return jsonify({"error": str(e)}), code
    except Exception as e:
        logger.error("Preview failed: %s", e)
        return jsonify({"error": str(e)}), 500
