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
from config import get_settings, map_path
from remux import RemuxError, remove_subtitle_stream
from remux.backup_cleanup import cleanup_old_backups, list_backups

bp = Blueprint("remux", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="remux")
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_video_path(ep_id: int) -> str | None:
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return None
    path = client.get_episode_file_path(ep_id)
    if not path:
        return None
    return map_path(path)


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
    except Exception:
        pass


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
    settings = get_settings()
    paths = []
    media = getattr(settings, "media_path", "")
    if media:
        paths.append(media)
    extra = getattr(settings, "extra_media_paths", "")
    if extra:
        paths.extend(p.strip() for p in extra.split(",") if p.strip())
    return paths


def _trash_paths() -> list[str]:
    """Return the resolved trash directory paths (one per media root)."""
    settings = get_settings()
    trash_dir = getattr(settings, "remux_trash_dir", ".sublarr")
    result = []
    if os.path.isabs(trash_dir):
        return [os.path.join(trash_dir, "trash")]
    for media_path in _media_paths():
        result.append(os.path.join(media_path, trash_dir, "trash"))
    return result


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
        return jsonify({"error": "Failed to probe video file: " + str(exc)}), 500
    except Exception:
        return jsonify({"error": "Internal server error"}), 500

    streams = probe.get("streams", [])
    if index >= len(streams):
        return jsonify({"error": f"Stream index {index} out of range"}), 400
    target = streams[index]
    if target.get("codec_type") != "subtitle":
        return jsonify({"error": f"Stream {index} is not a subtitle stream"}), 400

    # Derive subtitle_track_index (0-based within subtitle streams) if not supplied
    if subtitle_track_index is None:
        subtitle_track_index = sum(1 for s in streams[:index] if s.get("codec_type") == "subtitle")

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "result": None, "error": None}

    _executor.submit(_run_remux, job_id, video_path, index, subtitle_track_index)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


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
    backups = list_backups(_trash_paths())
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
