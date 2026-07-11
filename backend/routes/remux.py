"""Remux routes — remove subtitle streams from video containers.

POST /api/v1/library/episodes/<ep_id>/tracks/<index>/remove-from-container
    Start an async remux job to strip the subtitle stream.
    Body: { "subtitle_track_index": int }   (optional; derived from index if omitted)

GET  /api/v1/remux/jobs
    List recent remux jobs (in-memory, cleared on restart).

GET  /api/v1/remux/jobs/<job_id>
    Get status of a single remux job.

GET  /api/v1/remux/backups
    List all .bak files under watched media directories.

POST /api/v1/remux/backups/cleanup
    Trigger backup cleanup (honours remux_backup_retention_days).
    Optional body: { "dry_run": true }
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

from ass_utils import get_media_streams
from config import get_settings
from remux import RemuxError, remove_subtitle_stream
from remux.backup_cleanup import cleanup_old_backups, list_backups
from security_utils import is_safe_path

bp = Blueprint("remux", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="remux")
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_video_path(ep_id: int) -> str | None:
    from services.episode_video_path import resolve_episode_video_path

    return resolve_episode_video_path(ep_id)


def _resolve_stream_by_index(streams: list[dict], index: int) -> tuple[int, dict] | None:
    """Match UI track indexes from routes.tracks._build_track_list.

    ffprobe stream IDs are usually contiguous, but they are not guaranteed to be
    equal to the stream list position. The track UI sends the normalized stream
    id, so remux actions must resolve the stream the same way as the list route.
    """
    seen: set[int] = set()
    for position, stream in enumerate(streams):
        stream_index = stream.get("index", position)
        if stream_index in seen:
            stream_index = position
        seen.add(stream_index)
        if stream_index == index:
            return position, stream
    return None


def _update_job(
    job_id: str, status: str, result: dict | None = None, error: str | None = None
) -> None:
    with _jobs_lock:
        _jobs[job_id] = {"status": status, "result": result, "error": error}
    try:
        from app import socketio

        socketio.emit(
            "remux_job_update",
            {"job_id": job_id, "status": status, "result": result, "error": error},
        )
    except Exception as exc:
        logger.debug("SocketIO emit remux_job_update failed: %s", exc)


def _arr_pause(pause: bool) -> None:
    """Signal Sonarr/Radarr to pause/resume folder monitoring if configured."""
    settings = get_settings()
    if not getattr(settings, "remux_arr_pause_enabled", True):
        return
    try:
        from sonarr_client import get_sonarr_client

        client = get_sonarr_client()
        if client and hasattr(client, "set_monitoring"):
            client.set_monitoring(not pause)
    except Exception as exc:
        logger.debug("arr pause/resume skipped: %s", exc)


def _media_paths() -> list[str]:
    """Compat shim — implementation moved to
    :func:`services.trash_locations.media_paths`."""
    from services.trash_locations import media_paths

    return media_paths()


def _trash_paths() -> list[str]:
    """Compat shim — implementation moved to
    :func:`services.trash_locations.remux_trash_paths`.

    Kept because cleanup_scheduler, routes.trash and many tests
    reference/patch ``routes.remux._trash_paths``.
    """
    from services.trash_locations import remux_trash_paths

    return remux_trash_paths()


# ---------------------------------------------------------------------------
# Async job runner
# ---------------------------------------------------------------------------


def _run_remux(job_id: str, video_path: str, stream_index: int, subtitle_track_index: int) -> None:
    settings = get_settings()
    use_reflink = getattr(settings, "remux_use_reflink", True)
    trash_dir = getattr(settings, "remux_trash_dir", ".sublarr")
    _update_job(job_id, "running")
    _arr_pause(True)
    try:
        bak_path = remove_subtitle_stream(
            video_path=video_path,
            stream_index=stream_index,
            subtitle_track_index=subtitle_track_index,
            use_reflink=use_reflink,
            trash_dir=trash_dir,
        )
        _update_job(job_id, "completed", result={"backup_path": bak_path, "video_path": video_path})
        logger.info("Remux job %s completed — backup: %s", job_id, bak_path)
    except RemuxError as exc:
        _update_job(job_id, "failed", error=str(exc))
        logger.error("Remux job %s failed: %s", job_id, exc)
    except Exception as exc:
        _update_job(job_id, "failed", error=f"Unexpected error: {exc}")
        logger.exception("Remux job %s unexpected error", job_id)
    finally:
        _arr_pause(False)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.route(
    "/library/episodes/<int:ep_id>/tracks/<int:index>/remove-from-container", methods=["POST"]
)
def remove_track_from_container(ep_id: int, index: int):
    """Start an async remux job to remove subtitle track `index` from the video container."""
    body = request.get_json(force=True, silent=True) or {}
    subtitle_track_index = body.get("subtitle_track_index")

    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk: " + video_path}), 404

    # Verify that track index is a subtitle stream
    try:
        probe = get_media_streams(video_path)
    except RuntimeError as exc:
        logger.exception("Failed to probe video file: %s", exc)
        return jsonify({"error": "Failed to probe video file"}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500

    streams = probe.get("streams", [])
    resolved = _resolve_stream_by_index(streams, index)
    if resolved is None:
        return jsonify({"error": f"Stream index {index} out of range"}), 400
    stream_position, target = resolved
    if target.get("codec_type") != "subtitle":
        return jsonify({"error": f"Stream {index} is not a subtitle stream"}), 400

    # Derive subtitle_track_index (0-based within subtitle streams) if not supplied
    if subtitle_track_index is None:
        subtitle_track_index = sum(
            1 for s in streams[:stream_position] if s.get("codec_type") == "subtitle"
        )
    stream_index = target.get("index", stream_position)

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "result": None, "error": None}

    _executor.submit(_run_remux, job_id, video_path, stream_index, subtitle_track_index)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@bp.route("/library/episodes/<int:ep_id>/tracks/<int:index>/set-default", methods=["POST"])
def set_track_default(ep_id: int, index: int):
    """Make stream `index` the default track for its type (audio/subtitle).

    Header-only edit via mkvpropedit (no remux): sets flag-default=1 on the
    target and 0 on all other tracks of the same type, so exactly one default
    remains. Fast and preserves the file's permissions.
    """
    import subprocess

    from remux import _safe_arg_path

    video_path = _get_video_path(ep_id)
    if not video_path:
        return jsonify({"error": "Episode has no video file or Sonarr is not configured"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found on disk"}), 404

    try:
        probe = get_media_streams(video_path)
    except Exception:
        return jsonify({"error": "Failed to probe video file"}), 500

    streams = probe.get("streams", [])
    resolved = _resolve_stream_by_index(streams, index)
    if resolved is None:
        return jsonify({"error": f"Stream index {index} out of range"}), 400
    stream_position, target = resolved
    ctype = target.get("codec_type")
    if ctype not in ("audio", "subtitle"):
        return jsonify({"error": "Only audio or subtitle tracks can be set as default"}), 400

    sel = {"audio": "a", "subtitle": "s"}[ctype]
    # mkvpropedit selectors are 1-based per track type.
    edits: list[str] = []
    type_position = 0
    for position, s in enumerate(streams):
        if s.get("codec_type") == ctype:
            type_position += 1
            flag = "1" if position == stream_position else "0"
            edits += ["--edit", f"track:{sel}{type_position}", "--set", f"flag-default={flag}"]

    cmd = ["mkvpropedit", _safe_arg_path(video_path), *edits]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as exc:
        logger.exception("mkvpropedit set-default failed: %s", exc)
        return jsonify({"error": "mkvpropedit invocation failed"}), 500
    if result.returncode != 0:
        logger.error("mkvpropedit set-default rc=%s: %s", result.returncode, result.stderr)
        return jsonify({"error": "mkvpropedit failed"}), 500
    return jsonify({"changed": True, "index": index, "codec_type": ctype}), 200


@bp.route("/remux/jobs", methods=["GET"])
def list_remux_jobs():
    """Return all recent remux jobs."""
    with _jobs_lock:
        jobs = [{"job_id": jid, **info} for jid, info in _jobs.items()]
    return jsonify({"jobs": jobs}), 200


@bp.route("/remux/jobs/<job_id>", methods=["GET"])
def get_remux_job(job_id: str):
    """Return the status of a single remux job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job_id": job_id, **job}), 200


@bp.route("/remux/backups", methods=["GET"])
def list_remux_backups():
    """List all .bak backup files in the configured trash directory."""
    settings = get_settings()
    retention_days = getattr(settings, "remux_backup_retention_days", 7)
    backups = list_backups(_trash_paths(), retention_days=retention_days)
    return jsonify({"backups": backups, "count": len(backups)}), 200


@bp.route("/remux/backups/cleanup", methods=["POST"])
def trigger_backup_cleanup():
    """Delete .bak files older than remux_backup_retention_days."""
    body = request.get_json(force=True, silent=True) or {}
    dry_run = bool(body.get("dry_run", False))
    settings = get_settings()
    retention_days = getattr(settings, "remux_backup_retention_days", 7)

    if dry_run:
        # Just list what would be deleted
        import time

        from remux.backup_cleanup import _iter_bak_files

        cutoff = time.time() - retention_days * 86400
        would_delete = []
        for bak_path in _iter_bak_files(_trash_paths()):
            try:
                if os.path.getmtime(bak_path) < cutoff:
                    would_delete.append(bak_path)
            except OSError:
                pass
        return jsonify(
            {"dry_run": True, "would_delete": would_delete, "count": len(would_delete)}
        ), 200

    result = cleanup_old_backups(_trash_paths(), retention_days)
    return jsonify(result), 200


@bp.route("/remux/backups/restore", methods=["POST"])
def restore_backup():
    """Restore a backup file to its original video path.

    Body: {
        "backup_path": "/path/to/trash/...",
        "video_path": "/path/to/original.mkv",
        "delete_sidecars": false   # optional: also purge sidecar trash batches for this video
    }

    The original video (the remuxed file) is deleted and the backup is moved back.
    Both paths are validated against the configured media/trash directories.
    """
    body = request.get_json(force=True, silent=True) or {}
    backup_path = body.get("backup_path", "")
    video_path = body.get("video_path", "")
    delete_sidecars = bool(body.get("delete_sidecars", False))

    if not backup_path or not video_path:
        return jsonify({"error": "backup_path and video_path are required"}), 400

    # Security: backup must be inside a known trash dir.
    # is_safe_path(file_path, base_dir) — user-supplied path is the candidate,
    # trusted dirs are the base. Reversed args used to silently pass when
    # backup_path was set to "/" or any prefix of a trash dir.
    trash_dirs = _trash_paths()
    if not any(is_safe_path(backup_path, td) for td in trash_dirs):
        return jsonify({"error": "backup_path is outside the configured trash directory"}), 403

    # Security: restore target must be inside a known media path.
    media_dirs = _media_paths()
    if not any(is_safe_path(video_path, md) for md in media_dirs):
        return jsonify({"error": "video_path is outside the configured media directory"}), 403

    if not os.path.exists(backup_path):
        return jsonify({"error": "Backup file not found: " + backup_path}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": "Video file not found (already deleted?): " + video_path}), 404

    try:
        # Replace the remuxed file with the backup (atomic on same filesystem)
        os.replace(backup_path, video_path)
        logger.info("Remux restore: %s → %s", backup_path, video_path)
    except OSError as exc:
        logger.error("Remux restore failed: %s", exc)
        return jsonify({"error": f"Restore failed: {exc}"}), 500

    sidecars_deleted = 0
    if delete_sidecars:
        sidecars_deleted = _purge_sidecars_for_video(video_path)

    return jsonify(
        {
            "restored": video_path,
            "backup_removed": backup_path,
            "sidecars_deleted": sidecars_deleted,
        }
    ), 200


@bp.route("/remux/backups/delete", methods=["POST"])
def delete_backup():
    """Permanently delete a single MKV backup file.

    Body: { "backup_path": "/path/to/trash/..." }
    """
    body = request.get_json(force=True, silent=True) or {}
    backup_path = body.get("backup_path", "")

    if not backup_path:
        return jsonify({"error": "backup_path is required"}), 400

    trash_dirs = _trash_paths()
    if not any(is_safe_path(backup_path, td) for td in trash_dirs):
        return jsonify({"error": "backup_path is outside the configured trash directory"}), 403

    if not os.path.exists(backup_path):
        return jsonify({"error": "Backup file not found"}), 404

    try:
        os.remove(backup_path)
        logger.info("MKV backup deleted: %s", backup_path)
    except OSError as exc:
        logger.error("Failed to delete MKV backup: %s", exc)
        return jsonify({"error": f"Delete failed: {exc}"}), 500

    return jsonify({"deleted": backup_path}), 200


def _purge_sidecars_for_video(video_path: str) -> int:
    """Delete all sidecar trash batches whose files live next to video_path.

    Returns the number of batches deleted.
    """
    import shutil

    video_dir = os.path.dirname(video_path)
    settings = get_settings()
    media_path = getattr(settings, "media_path", "")
    if not media_path:
        return 0

    try:
        from routes.subtitles import _get_trash_root, _read_manifest
    except ImportError:
        logger.warning("Cannot import sidecar helpers for purge")
        return 0

    trash_root = _get_trash_root(media_path)
    if not os.path.isdir(trash_root):
        return 0

    deleted = 0
    for entry in os.scandir(trash_root):
        if not entry.is_dir():
            continue
        manifest = _read_manifest(entry.path)
        if manifest is None:
            continue
        # Check whether any file in the batch originated from the same directory
        files = manifest.get("files", [])
        if any(os.path.dirname(f.get("original", "")) == video_dir for f in files):
            try:
                shutil.rmtree(entry.path)
                logger.info("Purged sidecar batch %s (linked to %s)", entry.name, video_path)
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to purge sidecar batch %s: %s", entry.name, exc)

    return deleted
