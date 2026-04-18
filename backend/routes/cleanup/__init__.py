"""Cleanup API endpoints package.

Blueprint: /api/v1/cleanup

The package hosts the Blueprint object, shared scan state, and locks.
Route handlers live in domain-scoped submodules that import ``bp`` from
this package and register routes via @bp.route decorators.

Current submodules:
  - dedup: dedup scan + duplicate management (Task 2)
  - orphan: orphan subtitle scan + deletion (Task 3 — TBD)
  - rules: cleanup-rule CRUD + run + preview (Task 4 — TBD)
  - stats: cleanup stats + history (Task 5 — TBD)
  - preview: generic dry-run + non-target-subs (Task 6 — TBD)
"""

import json
import logging
import threading

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


@bp.route("/non-target-subs", methods=["POST"])
def cleanup_non_target_subs():
    """Walk the media library and trash sidecar subtitles whose language is
    not in any configured profile's target_languages.

    Complements the automatic post-extract cleanup in the batch-probe pipeline
    by reconciling legacy files that were extracted before the filter was
    introduced (e.g. all the `.jpn.ass` files from pre-0.51.11 extractions).

    Body (JSON, all optional):
      - dry_run: bool (default True) — when True, only counts/samples and
                 leaves the filesystem untouched.
      - media_path: str — override of settings.media_path.

    Returns:
      {
        "dry_run": bool,
        "would_trash": int,
        "trashed": int,
        "scanned_files": int,
        "keep_langs": ["de","en",…],
        "sample": [ {path, language}, … up to 20 ]
      }
    ---
    post:
      tags: [Cleanup]
      summary: Trash non-target subtitle sidecars across the library
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cleanup summary
    """
    import glob
    import os

    from config import get_settings
    from config_language_data import normalize_language_code
    from db.profiles import get_default_profile
    from db.repositories.profiles import ProfileRepository
    from remux import _SIDECAR_EXTS, _parse_sidecar_language, _resolve_trash_dir

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    media_path = data.get("media_path") or get_settings().media_path
    if not media_path or not os.path.isdir(media_path):
        return jsonify({"error": "media_path not configured or not a directory"}), 400

    # Union target_languages across every profile (series, movies, default).
    # The idea: a file under a movie root might belong to a profile with
    # different langs — we take the union so no user's configured target
    # ever gets trashed, regardless of which profile governs its series/movie.
    keep_langs: set[str] = set()
    try:
        settings = get_settings()
        repo = ProfileRepository()
        profiles = repo.get_profiles()
        if not profiles:
            profiles = [get_default_profile()]
        for p in profiles:
            for code in p.get("target_languages", []) or []:
                nc = normalize_language_code(code)
                if nc:
                    keep_langs.add(nc)
            # Source language is needed when any profile has translation on —
            # conservatively include it so translation inputs aren't deleted.
            if getattr(settings, "wanted_auto_translate", False):
                src = normalize_language_code(settings.source_language)
                if src:
                    keep_langs.add(src)
    except Exception as exc:
        logger.error("Profile aggregation failed: %s", exc)
        return jsonify({"error": f"could not aggregate profiles: {exc}"}), 500

    if not keep_langs:
        return (
            jsonify(
                {
                    "error": "no target languages configured — aborting to avoid wiping everything",
                }
            ),
            400,
        )

    video_exts = (".mkv", ".mp4", ".m4v", ".avi", ".mov")
    to_trash: list[tuple[str, str]] = []  # (path, normalized_lang)
    scanned = 0
    trash_dir_setting = getattr(settings, "remux_trash_dir", ".sublarr")
    import datetime
    import shutil

    for root, _dirs, files in os.walk(media_path):
        # Skip our own trash folder to avoid re-trashing moved files.
        if os.sep + ".sublarr" + os.sep in (root + os.sep):
            continue
        for fname in files:
            if not fname.lower().endswith(video_exts):
                continue
            scanned += 1
            video_path = os.path.join(root, fname)
            video_base = os.path.splitext(video_path)[0]
            for ext in _SIDECAR_EXTS:
                for candidate in glob.glob(f"{video_base}.*{ext}"):
                    raw_lang = _parse_sidecar_language(candidate, video_base)
                    if raw_lang is None:
                        continue
                    normalised = normalize_language_code(raw_lang)
                    if not normalised or normalised == "und":
                        continue
                    if normalised in keep_langs:
                        continue
                    to_trash.append((candidate, normalised))

    trashed_count = 0
    if not dry_run:
        for candidate, _lang in to_trash:
            try:
                resolved = _resolve_trash_dir(candidate, trash_dir_setting or ".sublarr")
                date_str = datetime.date.today().isoformat()
                dest_dir = os.path.join(resolved, "trash", date_str)
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, os.path.basename(candidate))
                if os.path.exists(dest):
                    import time as _time

                    stem, dext = os.path.splitext(dest)
                    dest = f"{stem}.{int(_time.time())}{dext}"
                shutil.move(candidate, dest)
                trashed_count += 1
            except OSError as exc:
                logger.warning("non-target-subs: could not trash %s: %s", candidate, exc)

    sample = [{"path": p, "language": lang} for p, lang in to_trash[:20]]
    return jsonify(
        {
            "dry_run": dry_run,
            "would_trash": len(to_trash),
            "trashed": trashed_count,
            "scanned_files": scanned,
            "keep_langs": sorted(keep_langs),
            "sample": sample,
        }
    )


# Submodule imports — triggers @bp.route decorator registration
from routes.cleanup import dedup, orphan  # noqa: E402, F401
