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
from routes.cleanup import dedup, orphan, rules  # noqa: E402, F401
