"""Generic cleanup-preview + non-target-subs routes."""

import datetime
import glob
import logging
import os
import shutil

from flask import jsonify, request

from routes.cleanup import bp

logger = logging.getLogger(__name__)


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
        logger.exception("Preview failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500


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
    from config import get_settings
    from config_language_data import normalize_language_code
    from db.profiles import get_default_profile
    from db.repositories.profiles import ProfileRepository
    from remux import _SIDECAR_EXTS, _parse_sidecar_language, _resolve_trash_dir
    from services.cleanup_executors import _media_path_reachable, _safe_walk

    data = request.get_json(silent=True) or {}
    dry_run = bool(data.get("dry_run", True))
    # Always read media_path from settings — never from the request body.
    # An accepted override would let any API-key holder walk arbitrary
    # directories and trash sidecars outside the configured library.
    media_path = get_settings().media_path
    if not media_path or not os.path.isdir(media_path):
        return jsonify({"error": "media_path not configured or not a directory"}), 400
    # Audit C2-1 + C0-3: probe the root and use the inode-tracking walker
    # so symlink cycles can't hang the scan and a transient mount blip
    # can't make every file look "missing".
    if not _media_path_reachable(media_path):
        return jsonify({"error": "media_path unreachable; aborting"}), 503

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

    for root, files in _safe_walk(media_path):
        # Skip our own trash folder to avoid re-trashing moved files.
        # Use a robust separator-agnostic check that also catches a
        # top-level ".sublarr" without a leading separator.
        norm = root.replace("\\", "/")
        if "/.sublarr/" in (norm + "/") or norm.endswith("/.sublarr"):
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
