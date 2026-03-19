"""Subtitle processing API routes.

POST /api/v1/tools/process                — apply mods (supports dry_run)
POST /api/v1/tools/process/undo           — restore .bak file
GET  /api/v1/tools/process/bak-exists     — check if .bak exists
GET  /api/v1/tools/process/interjections  — get interjections list
PUT  /api/v1/tools/process/interjections  — replace interjections list
POST /api/v1/library/series/<id>/process  — trigger series processing (background)
POST /api/v1/library/process-all          — trigger full library batch (background)
PATCH /api/v1/library/series/<id>/processing-config — save per-series override
"""

import json
import logging
import os
import shutil
import threading
from datetime import UTC, datetime

from flask import Blueprint, current_app, jsonify, request

from config import get_settings, map_path
from security_utils import is_safe_path

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
    """Restore a subtitle file from its .bak backup."""
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path", "")

    err, abs_path = _validate_path(path)
    if err:
        msg, code = err
        return jsonify({"error": msg}), code

    base, ext = os.path.splitext(abs_path)
    bak_path = f"{base}.bak{ext}"

    if not os.path.exists(bak_path):
        return jsonify({"error": "No backup found for this file"}), 404

    try:
        shutil.move(bak_path, abs_path)
    except OSError as e:
        return jsonify({"error": f"Could not restore backup: {e}"}), 409

    return jsonify({"status": "restored", "path": abs_path}), 200


@bp.route("/tools/process/bak-exists", methods=["GET"])
def bak_exists():
    """Check whether a .bak file exists for a given subtitle path."""
    path = request.args.get("path", "")
    err, abs_path = _validate_path(path)
    if err:
        msg, code = err
        return jsonify({"error": msg}), code
    base, ext = os.path.splitext(abs_path)
    exists = os.path.exists(f"{base}.bak{ext}")
    return jsonify({"exists": exists}), 200


@bp.route("/tools/process/interjections", methods=["GET"])
def get_interjections():
    """Return the current interjections list."""
    s = get_settings()
    raw = s.hi_interjections_list.strip()
    if raw:
        items = [line.strip() for line in raw.splitlines() if line.strip()]
        is_custom = True
    else:
        data_file = os.path.join(os.path.dirname(__file__), "..", "data", "hi_interjections.txt")
        if os.path.exists(data_file):
            with open(data_file, encoding="utf-8") as f:
                items = [line.strip() for line in f if line.strip()]
        else:
            items = []
        is_custom = False

    return jsonify({"items": items, "is_custom": is_custom}), 200


@bp.route("/tools/process/interjections", methods=["PUT"])
def put_interjections():
    """Replace the interjections list. Empty items list resets to default."""
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry

    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items", [])

    if not isinstance(items, list):
        return jsonify({"error": "items must be an array"}), 400

    saved = [str(i).strip() for i in items if str(i).strip()]
    new_value = "\n".join(saved)
    save_config_entry("hi_interjections_list", new_value)
    reload_settings(get_all_config_entries())

    return jsonify({"status": "ok", "count": len(saved)}), 200


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

    threading.Thread(target=_run, args=(app,), daemon=True).start()
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

    threading.Thread(target=_run, args=(app,), daemon=True).start()
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
        row.updated_at = datetime.now(UTC).isoformat()
    else:
        row = SeriesSettings(
            sonarr_series_id=series_id,
            processing_config=json.dumps(config) if config else None,
            updated_at=datetime.now(UTC).isoformat(),
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

    from config import map_path as _map_path
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if not client:
        return
    episode_files = client.get_episode_files_by_series(series_id)

    total = len(episode_files)
    processed = 0

    for file_info in episode_files.values():
        raw_path = file_info.get("path")
        if not raw_path:
            continue
        video_path = _map_path(raw_path)
        sidecars = scan_subtitle_sidecars(video_path)
        for sidecar in sidecars:
            sub_path = sidecar["path"]
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
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if not client:
        return

    try:
        all_series = client.get_series()
    except Exception as exc:
        logger.warning("[batch-process-library] failed to fetch series: %s", exc)
        return

    for series in all_series:
        series_id = series.get("id")
        if not series_id:
            continue
        if filter_mode == "unprocessed":
            row = _db.session.get(SeriesSettings, series_id)
            if row and row.processing_config is not None:
                continue  # already has processing config, skip
        _batch_process_series(series_id)
