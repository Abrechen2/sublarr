"""Subtitle processing API routes.

POST /api/v1/tools/process                — apply mods (supports dry_run)
POST /api/v1/tools/process/undo           — restore .bak file
GET  /api/v1/tools/process/bak-exists     — check if .bak exists
POST /api/v1/library/series/<id>/process  — trigger series processing (background)
POST /api/v1/library/process-all          — trigger full library batch (background)
PATCH /api/v1/library/series/<id>/processing-config — save per-series override
GET  /api/v1/library/subtitle-backups     — list all subtitle .bak files
POST /api/v1/library/subtitle-backups/cleanup — bulk delete (TTL + orphans)
"""

import json
import logging
import os
import threading
from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request

import config
from security_utils import is_safe_path
from services.background_tasks import submit_background
from subtitle_filename import find_existing_bak


# Looked up on every call, not bound at import: a test that first imports this
# module inside patch("config.get_settings") otherwise leaves it reading the
# mock for the rest of the run.
def get_settings():
    return config.get_settings()


def map_path(path):
    return config.map_path(path)


bp = Blueprint("subtitle_processor", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_batch_lock = threading.Lock()
_batch_running = False


def _validate_path(path: str):
    """Validate subtitle path. Returns (error_tuple, None) or (None, abs_path)."""
    if not path:
        return ("path is required", 400), None
    mapped = map_path(path)
    s = get_settings()
    if not is_safe_path(mapped, s.media_path):
        return ("path must be under media_path", 403), None
    abs_path = os.path.realpath(mapped)
    if not os.path.exists(abs_path):
        return (f"File not found: {path}", 404), None
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return ("Only .srt, .ass, and .ssa files are supported", 400), None
    return None, abs_path


@bp.route("/tools/process", methods=["POST"])
def process_subtitle():
    """Apply mods to a subtitle file. Use dry_run=true for preview."""
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path", "")
    mods_raw = data.get("mods", [])
    dry_run = bool(data.get("dry_run", False))

    err, abs_path = _validate_path(path)
    if err:
        msg, code = err
        return jsonify({"error": msg}), code

    from subtitle_processor import ModConfig, ModName, apply_mods

    try:
        mods = [ModConfig(mod=ModName(m["mod"]), options=m.get("options", {})) for m in mods_raw]
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"Invalid mod config: {e}"}), 400

    try:
        result = apply_mods(abs_path, mods, dry_run=dry_run)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        logger.exception("process_subtitle failed for %s", abs_path)
        return jsonify({"error": "Internal server error"}), 500

    return (
        jsonify(
            {
                "changes": [
                    {
                        "event_index": c.event_index,
                        "timestamp": c.timestamp,
                        "original_text": c.original_text,
                        "modified_text": c.modified_text,
                        "mod_name": c.mod_name,
                    }
                    for c in result.changes
                ],
                "backed_up": result.backed_up,
                "output_path": result.output_path,
                "dry_run": result.dry_run,
            }
        ),
        200,
    )


@bp.route("/tools/process/undo", methods=["POST"])
def undo_process():
    """Restore a subtitle file from its .bak backup.

    When the active sidecar still exists, performs an atomic 3-rename swap:
    the current active becomes the new bak, the bak becomes the active. This
    guarantees no data loss if the user has re-downloaded or hand-edited the
    active sub between the original backup and this restore — they can simply
    invoke restore again to flip back. When the active is missing (deleted
    by hand), falls back to a single rename.
    """
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path", "")

    if not path:
        return jsonify({"error": "path is required"}), 400
    mapped = map_path(path)
    s = get_settings()
    if not is_safe_path(mapped, s.media_path):
        return jsonify({"error": "path must be under media_path"}), 403
    abs_path = os.path.realpath(mapped)
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return jsonify({"error": "Only .srt, .ass, and .ssa files are supported"}), 400

    from services.subtitle_restore import RestoreError, restore_from_bak

    try:
        result = restore_from_bak(abs_path)
    except RestoreError as e:
        return jsonify({"error": str(e)}), e.http_status
    return jsonify(result), 200


@bp.route("/tools/process/bak-exists", methods=["GET"])
def bak_exists():
    """Check whether a .bak file exists for a given subtitle path.

    Looks in both the canonical hidden location and the legacy sibling
    location so pre-migration backups are still reported as available.
    """
    path = request.args.get("path", "")
    err, abs_path = _validate_path(path)
    if err:
        msg, code = err
        return jsonify({"error": msg}), code
    exists = find_existing_bak(abs_path) is not None
    return jsonify({"exists": exists}), 200


@bp.route("/library/series/<int:series_id>/process", methods=["POST"])
def process_series(series_id):
    """Trigger background processing for all subtitles in a series."""
    global _batch_running
    with _batch_lock:
        if _batch_running:
            return jsonify({"error": "A batch process is already running"}), 409
        _batch_running = True

    app = current_app._get_current_object()

    def _run(app):
        global _batch_running
        try:
            with app.app_context():
                _batch_process_series(series_id)
        finally:
            _batch_running = False

    submit_background(_run, app)
    return jsonify({"status": "started", "series_id": series_id}), 202


@bp.route("/library/process-all", methods=["POST"])
def process_all():
    """Trigger background processing for all series in the library."""
    data = request.get_json(force=True, silent=True) or {}
    filter_mode = data.get("filter", "all")  # "all" | "unprocessed"

    VALID_FILTER_MODES = {"all", "unprocessed"}
    if filter_mode not in VALID_FILTER_MODES:
        return jsonify({"error": f"filter must be one of {sorted(VALID_FILTER_MODES)}"}), 400

    global _batch_running
    with _batch_lock:
        if _batch_running:
            return jsonify({"error": "A batch process is already running"}), 409
        _batch_running = True

    app = current_app._get_current_object()

    def _run(app):
        global _batch_running
        try:
            with app.app_context():
                _batch_process_library(filter_mode)
        finally:
            _batch_running = False

    submit_background(_run, app)
    return jsonify({"status": "started", "filter": filter_mode}), 202


@bp.route("/library/series/<int:series_id>/processing-config", methods=["PATCH"])
def update_series_processing_config(series_id):
    """Save per-series processing override config."""
    from db.models.core import SeriesSettings
    from extensions import db as _db

    data = request.get_json(force=True, silent=True) or {}
    allowed = {"hi_removal", "common_fixes", "credit_removal", "auto_sync"}
    config = {k: v for k, v in data.items() if k in allowed}

    row = _db.session.get(SeriesSettings, series_id)
    if row:
        row.processing_config = json.dumps(config) if config else None
        row.updated_at = datetime.now(UTC)
    else:
        row = SeriesSettings(
            sonarr_series_id=series_id,
            processing_config=json.dumps(config) if config else None,
            updated_at=datetime.now(UTC),
        )
        _db.session.add(row)
    _db.session.commit()

    return jsonify({"status": "ok", "series_id": series_id, "config": config}), 200


# ─── Background helpers ──────────────────────────────────────────────────────


def _build_pipeline_mods(cfg: dict):
    """Convert a resolved config dict into an ordered list of ModConfig objects."""
    from subtitle_processor import ModConfig, ModName

    mods = []
    if cfg.get("common_fixes"):
        raw = get_settings().auto_process_common_fixes_config_json.strip()
        try:
            options = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            logger.warning("[batch-process] invalid common_fixes JSON config, using defaults")
            options = {}
        mods.append(ModConfig(mod=ModName.COMMON_FIXES, options=options))
    if cfg.get("hi_removal"):
        mods.append(ModConfig(mod=ModName.HI_REMOVAL))
    if cfg.get("credit_removal"):
        mods.append(ModConfig(mod=ModName.CREDIT_REMOVAL))
    return mods


def _is_processing_exempt_sidecar(subtitle_path: str) -> bool:
    """True for sidecars the auto-mods must never rewrite.

    - Modifier variants (``.hi``, ``.sdh``, ``.cc``, ``.forced``): running
      HI-removal over a ``.hi`` file destroys the whole point of that
      variant (its non-HI twin usually sits right next to it).
    - Combined bilingual files (``.de-en.combined.ass``): composed
      artefacts, not processing fodder.
    """
    try:
        from subtitle_filename import parse_combined_filename, parse_subtitle_filename

        if parse_combined_filename(subtitle_path) is not None:
            return True
        parsed = parse_subtitle_filename(subtitle_path)
        if parsed is not None and parsed.primary_modifier in ("hi", "sdh", "cc", "forced"):
            return True
    except Exception:
        logger.debug("[pipeline] sidecar classification failed for %s", subtitle_path)
    return False


def _run_pipeline_for_path(subtitle_path: str, series_id: int | None) -> None:
    """Run the configured processing pipeline for one subtitle file.

    Called post-download (synchronously for fast ops) or from batch.
    No-ops if no processing mods are enabled.
    """
    ext = os.path.splitext(subtitle_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return
    if _is_processing_exempt_sidecar(subtitle_path):
        return

    from db.models.core import SeriesSettings
    from extensions import db as _db
    from subtitle_processor import apply_mods, resolve_config

    s = get_settings()
    global_cfg = {
        "common_fixes": s.auto_process_common_fixes,
        "hi_removal": s.auto_process_hi_removal,
        "credit_removal": s.auto_process_credit_removal,
    }

    series_cfg = None
    if series_id is not None:
        row = _db.session.get(SeriesSettings, series_id)
        if row and row.processing_config:
            try:
                series_cfg = json.loads(row.processing_config)
            except json.JSONDecodeError:
                logger.warning(
                    "[pipeline] malformed processing_config for series %s, using global config",
                    series_id,
                )

    resolved = resolve_config(global_cfg, series_cfg)
    mods = _build_pipeline_mods(resolved)
    if not mods:
        return

    try:
        apply_mods(subtitle_path, mods)
        logger.debug("[pipeline] processed %s", subtitle_path)
    except Exception as exc:
        logger.warning("[pipeline] failed for %s: %s", subtitle_path, exc)


def _series_video_paths(series_id: int) -> list[str]:
    """Video files of a series: from Sonarr, or (no Sonarr client) from the
    standalone series folder — same rule as the series detail."""
    from config import map_path as _map_path
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client:
        episode_files = client.get_episode_files_by_series(series_id) or {}
        return [_map_path(fi["path"]) for fi in episode_files.values() if fi.get("path")]

    from db.standalone import get_standalone_series
    from routes.library.series import _enumerate_series_episode_files

    series = get_standalone_series(series_id)
    if not series:
        return []
    return [fp for fp, _ in _enumerate_series_episode_files(series.get("folder_path", ""))]


def _library_series_ids() -> list[int]:
    """Sonarr series ids, or the standalone series ids without Sonarr."""
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client:
        return [s["id"] for s in client.get_series() or [] if s.get("id")]

    from db.standalone import get_standalone_series

    return [s["id"] for s in get_standalone_series() or [] if s.get("id")]


def _batch_process_series(series_id: int) -> None:
    """Process all subtitle sidecars for a series. Called in background thread."""
    from db.models.core import SeriesSettings
    from events import emit_event
    from extensions import db as _db
    from routes.subtitles import scan_subtitle_sidecars
    from subtitle_processor import apply_mods, resolve_config

    row = _db.session.get(SeriesSettings, series_id)
    series_cfg = json.loads(row.processing_config) if (row and row.processing_config) else None

    s = get_settings()
    global_cfg = {
        "common_fixes": s.auto_process_common_fixes,
        "hi_removal": s.auto_process_hi_removal,
        "credit_removal": s.auto_process_credit_removal,
    }
    resolved = resolve_config(global_cfg, series_cfg)
    mods = _build_pipeline_mods(resolved)
    if not mods:
        return

    video_paths = _series_video_paths(series_id)

    total = len(video_paths)
    processed = 0

    for video_path in video_paths:
        sidecars = scan_subtitle_sidecars(video_path)
        for sidecar in sidecars:
            sub_path = sidecar["path"]
            # Never rewrite modifier variants (.hi/.sdh/.cc/.forced) or
            # combined bilingual files — HI-removal over a .hi sidecar
            # destroys the variant it exists to provide.
            if sidecar.get("combined") or sidecar.get("modifier") in (
                "hi",
                "sdh",
                "cc",
                "forced",
            ):
                continue
            result = None
            try:
                result = apply_mods(sub_path, mods)
                status = "ok"
                changes_count = len(result.changes)
            except Exception as exc:
                logger.warning("[batch-process] failed for %s: %s", sub_path, exc)
                status = "failed"
                changes_count = 0

            processed += 1
            emit_event(
                "batch_process_progress",
                {
                    "series_id": series_id,
                    "current": processed,
                    "total": total,
                    "filename": os.path.basename(sub_path),
                    "status": status,
                    "changes": changes_count,
                    "backed_up": result.backed_up if (status == "ok" and result) else False,
                    "sub_path": sub_path,
                },
            )

    emit_event(
        "batch_process_completed",
        {
            "series_id": series_id,
            "total": processed,
        },
    )


def _batch_process_library(filter_mode: str) -> None:
    """Process all series in library. filter_mode: 'all' | 'unprocessed'."""
    from db.models.core import SeriesSettings
    from extensions import db as _db

    try:
        series_ids = _library_series_ids()
    except Exception as exc:
        logger.warning("[batch-process-library] failed to fetch series: %s", exc)
        return

    for series_id in series_ids:
        if filter_mode == "unprocessed":
            row = _db.session.get(SeriesSettings, series_id)
            if row and row.processing_config is not None:
                continue  # already has processing config, skip
        _batch_process_series(series_id)


# ─── Subtitle-backup management ───────────────────────────────────────────────


def _media_roots_for_baks() -> list[str]:
    """Resolve the media directories the bak walker should scan.

    Reads ``media_path`` and ``extra_media_paths`` from settings, the
    same shape as ``routes.remux._media_paths`` — kept inline to avoid
    cross-route imports just for this two-line helper.
    """
    s = get_settings()
    paths: list[str] = []
    media = getattr(s, "media_path", "")
    if media:
        paths.append(media)
    extra = getattr(s, "extra_media_paths", "")
    if extra:
        paths.extend(p.strip() for p in extra.split(",") if p.strip())
    return paths


@bp.route("/library/subtitle-backups", methods=["GET"])
def list_subtitle_backups():
    """Return every subtitle ``.bak`` file Sublarr knows about.

    Query parameters
    ----------------
    series_path : optional path prefix
        When provided, only baks whose path begins with this prefix are
        returned. The frontend uses the Sonarr series.path as the
        filter so the management UI can scope to one show.
    """
    from services.subtitle_backups import list_subtitle_baks

    s = get_settings()
    retention = int(getattr(s, "subtitle_bak_retention_days", 30) or 0)
    series_path = request.args.get("series_path") or None

    if series_path:
        # Defence-in-depth: never let the caller scan arbitrary paths.
        # The filter is a path prefix, not the actual scan root, so a
        # malicious value would just narrow results to nothing — but
        # we still validate it lies under media_path.
        roots = _media_roots_for_baks()
        if not any(is_safe_path(series_path, r) for r in roots):
            return jsonify({"error": "series_path is outside the configured media directory"}), 403

    baks = list_subtitle_baks(
        _media_roots_for_baks(),
        retention_days=retention,
        series_path_filter=series_path,
    )
    orphan_count = sum(1 for b in baks if b["is_orphan"])
    return jsonify(
        {
            "backups": baks,
            "count": len(baks),
            "orphan_count": orphan_count,
            "retention_days": retention,
        }
    ), 200


@bp.route("/library/subtitle-backups/cleanup", methods=["POST"])
def cleanup_subtitle_backups():
    """Bulk-delete subtitle backup files.

    Body
    ----
    older_than_days : int (optional, default = configured retention)
        Delete baks older than this many days. ``0`` disables the age
        check — combine with ``orphans_only=true`` for orphan-only mode.
    orphans_only : bool (optional, default false)
        Skip the age check entirely and only purge orphans.
    dry_run : bool (optional, default false)
        Preview without touching disk. Returns the same shape with the
        ``dry_run`` flag set.
    """
    from services.subtitle_backups import cleanup_subtitle_baks

    body = request.get_json(force=True, silent=True) or {}
    s = get_settings()
    default_retention = int(getattr(s, "subtitle_bak_retention_days", 30) or 0)
    try:
        older_than_days = int(body.get("older_than_days", default_retention))
    except (TypeError, ValueError):
        return jsonify({"error": "older_than_days must be an integer"}), 400
    # Negative values would underflow into a "delete everything" date. 0 stays
    # legal (intentional age-check disable, paired with orphans_only).
    older_than_days = max(0, older_than_days)
    orphans_only = bool(body.get("orphans_only", False))
    dry_run = bool(body.get("dry_run", False))

    result = cleanup_subtitle_baks(
        _media_roots_for_baks(),
        older_than_days=older_than_days,
        orphans_only=orphans_only,
        dry_run=dry_run,
    )
    return jsonify(result), 200
