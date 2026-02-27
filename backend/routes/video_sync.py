"""Video sync routes — async subtitle synchronization against video or reference subtitle.

POST /api/v1/tools/video-sync          → start sync job, returns { job_id }
GET  /api/v1/tools/video-sync/engines  → available engines { ffsubsync, alass }
GET  /api/v1/tools/video-sync/<job_id> → job status
"""

import contextlib
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request

bp = Blueprint("video_sync", __name__, url_prefix="/api/v1/tools")
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-sync")
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _update_job(job_id: str, status: str, result: dict = None, error: str = None) -> None:
    with _jobs_lock:
        _jobs[job_id] = {"status": status, "result": result, "error": error}
    try:
        from app import socketio

        socketio.emit(
            "sync_job_update",
            {
                "job_id": job_id,
                "status": status,
                "result": result,
                "error": error,
            },
        )
    except Exception:
        pass


def _run_sync(
    job_id: str,
    engine: str,
    subtitle_path: str,
    video_path: str | None,
    reference_path: str | None,
    cleanup_ref: str | None,
) -> None:
    _update_job(job_id, "running")
    try:
        from services.video_sync import sync_with_alass, sync_with_ffsubsync

        if engine == "ffsubsync":
            result = sync_with_ffsubsync(subtitle_path, video_path)
        elif engine == "alass":
            result = sync_with_alass(subtitle_path, reference_path)
        else:
            raise ValueError(f"Unknown engine: {engine!r}")
        _update_job(job_id, "completed", result=result)
    except Exception as exc:
        logger.exception("Sync job %s failed", job_id)
        _update_job(job_id, "failed", error=str(exc))
    finally:
        if cleanup_ref:
            with contextlib.suppress(OSError):
                os.unlink(cleanup_ref)


@bp.route("/video-sync/engines", methods=["GET"])
def get_engines():
    """Return which sync engines are available."""
    from services.video_sync import get_available_engines

    return jsonify(get_available_engines())


@bp.route("/video-sync", methods=["POST"])
def start_sync():
    """Start an async video sync job.

    Body:
        file_path (str): subtitle file to sync — required
        engine (str): "ffsubsync" | "alass" — default "ffsubsync"
        video_path (str): required for ffsubsync
        reference_path (str): pre-extracted reference subtitle for alass
        reference_track_index (int): stream index to auto-extract as alass reference
    """
    data = request.get_json(force=True, silent=True) or {}
    subtitle_path = data.get("file_path", "").strip()
    video_path = data.get("video_path", "").strip()
    engine = data.get("engine", "ffsubsync")
    reference_track_index = data.get("reference_track_index")
    reference_path = data.get("reference_path", "").strip()

    if not subtitle_path:
        return jsonify({"error": "file_path is required"}), 400
    if not os.path.exists(subtitle_path):
        return jsonify({"error": f"Subtitle file not found: {subtitle_path}"}), 404

    # Security: ensure paths are under media_path
    from config import get_settings

    _s = get_settings()
    _media_path = os.path.abspath(_s.media_path)
    if not os.path.abspath(subtitle_path).startswith(_media_path + os.sep):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403
    if video_path and not os.path.abspath(video_path).startswith(_media_path + os.sep):
        return jsonify({"error": "video_path must be under the configured media_path"}), 403

    if engine == "ffsubsync":
        if not video_path:
            return jsonify({"error": "video_path is required for ffsubsync"}), 400
    elif engine == "alass":
        if not reference_path and reference_track_index is None:
            return jsonify(
                {"error": "reference_path or reference_track_index required for alass"}
            ), 400
    else:
        return jsonify({"error": f"Unknown engine: {engine!r}"}), 400

    # Auto-extract reference track for alass when index given
    cleanup_ref = None
    if engine == "alass" and reference_track_index is not None and video_path:
        try:
            from ass_utils import extract_subtitle_stream, get_media_streams

            probe = get_media_streams(video_path)
            stream = next(
                (s for s in probe.get("streams", []) if s.get("index") == reference_track_index),
                None,
            )
            if not stream:
                return jsonify({"error": f"Track index {reference_track_index} not found"}), 404
            codec = stream.get("codec_name", "subrip")
            ext = "ass" if codec in ("ass", "ssa") else "srt"
            import tempfile

            fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}")
            os.close(fd)
            extract_subtitle_stream(
                video_path,
                {"sub_index": reference_track_index, "format": codec},
                tmp_path,
            )
            reference_path = tmp_path
            cleanup_ref = tmp_path
        except Exception as exc:
            return jsonify({"error": f"Failed to extract reference track: {exc}"}), 500

    job_id = str(uuid.uuid4())
    _update_job(job_id, "queued")
    _executor.submit(
        _run_sync,
        job_id,
        engine,
        subtitle_path,
        video_path or None,
        reference_path or None,
        cleanup_ref,
    )

    return jsonify({"job_id": job_id}), 202


@bp.route("/video-sync/<job_id>", methods=["GET"])
def sync_status(job_id: str):
    """Return the status of a previously started sync job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job_id": job_id, **job})


@bp.route("/video-sync/install/<engine>", methods=["POST"])
def install_engine(engine: str):
    """Install a sync engine (ffsubsync or alass)."""
    if engine not in ("ffsubsync", "alass"):
        return jsonify({"error": f"Unknown engine: {engine!r}"}), 400
    try:
        from services.video_sync import install_engine as _install

        result = _install(engine)
        return jsonify(result)
    except Exception as exc:
        logger.exception("Engine install failed: %s", engine)
        return jsonify({"success": False, "error": str(exc)}), 500
