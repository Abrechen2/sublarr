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

from flask import Blueprint, current_app, jsonify, request

from extensions import limiter

bp = Blueprint("video_sync", __name__, url_prefix="/api/v1/tools")
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="video-sync")
_jobs: dict = {}
_jobs_lock = threading.Lock()


def _submit_sync(app, *args) -> None:
    """Submit a sync job, wrapping ``_run_sync`` in the Flask app context.

    Worker threads spawned by ``ThreadPoolExecutor`` do NOT inherit the request
    app context. ``sync_with_ffsubsync`` / ``sync_with_alass`` touch the DB via
    ``write_sync_job_run`` and trigger ``post_processing.after_sync`` hooks —
    both require an active app context. Without this wrapper both calls log
    ``Working outside of application context`` and swallow silently, so the
    ``sync_job_runs`` audit table never receives manual-sync rows and no
    after_sync pipeline ever fires (see ``feedback_flask_app_context_in_threads``).
    """

    def _runner() -> None:
        with app.app_context():
            _run_sync(*args)

    _executor.submit(_runner)


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
    except Exception as exc:
        logger.debug("SocketIO emit sync_job_update failed: %s", exc)


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

    # Security: ensure paths are under media_path. Use is_safe_path which
    # resolves symlinks via realpath — manual abspath/startswith does not.
    from config import get_settings
    from security_utils import is_safe_path

    _s = get_settings()
    if not is_safe_path(subtitle_path, _s.media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403
    if video_path and not is_safe_path(video_path, _s.media_path):
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
    _submit_sync(
        current_app._get_current_object(),
        job_id,
        engine,
        subtitle_path,
        video_path or None,
        reference_path or None,
        cleanup_ref,
    )

    return jsonify({"job_id": job_id}), 202


@bp.route("/video-sync/compare", methods=["POST"])
@limiter.limit("6 per minute")
def sync_compare_endpoint():
    """Non-destructively preview sync candidates for a side-by-side compare.

    Body:
        file_path (str): subtitle to preview — required
        video_path (str): reference video for ffsubsync (optional)
        reference_path (str): reference subtitle for alass (optional)

    Runs the applicable engines WITHOUT overwriting the sidecar and returns
    ``{original, candidates, any_output}``. Applying a chosen candidate is the
    existing ``POST /video-sync`` job.
    """
    data = request.get_json(force=True, silent=True) or {}
    subtitle_path = data.get("file_path", "").strip()
    video_path = (data.get("video_path") or "").strip()
    reference_path = (data.get("reference_path") or "").strip()

    if not subtitle_path:
        return jsonify({"error": "file_path is required"}), 400
    if not os.path.exists(subtitle_path):
        return jsonify({"error": f"Subtitle file not found: {subtitle_path}"}), 404
    if not video_path and not reference_path:
        return jsonify({"error": "video_path or reference_path is required"}), 400

    from config import get_settings
    from security_utils import is_safe_path

    _s = get_settings()
    if not is_safe_path(subtitle_path, _s.media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403
    if video_path and not is_safe_path(video_path, _s.media_path):
        return jsonify({"error": "video_path must be under the configured media_path"}), 403
    if reference_path and not is_safe_path(reference_path, _s.media_path):
        return jsonify({"error": "reference_path must be under the configured media_path"}), 403

    from services.sync_preview import sync_compare

    try:
        result = sync_compare(
            subtitle_path,
            video_path=video_path or None,
            reference_path=reference_path or None,
        )
    except Exception as exc:  # pragma: no cover - defensive; per-engine errors are captured inside
        logger.exception("sync compare failed for %s", subtitle_path)
        return jsonify({"error": f"Sync compare failed: {exc}"}), 500

    return jsonify(result), 200


@bp.route("/auto-sync", methods=["POST"])
def auto_sync():
    """Quick one-click auto-sync using ffsubsync (fire-and-forget, no job polling needed).

    Body:
        file_path (str): subtitle file to sync — required
        video_path (str): video file for reference — required
        engine (str): "ffsubsync" (default) | "alass"
    """
    data = request.get_json(force=True, silent=True) or {}
    subtitle_path = data.get("file_path", "").strip()
    video_path = data.get("video_path", "").strip()
    engine = data.get("engine", "ffsubsync")

    if not subtitle_path:
        return jsonify({"error": "file_path is required"}), 400
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    if not os.path.exists(subtitle_path):
        return jsonify({"error": f"Subtitle file not found: {subtitle_path}"}), 404
    if not os.path.exists(video_path):
        return jsonify({"error": f"Video file not found: {video_path}"}), 404

    from config import get_settings
    from security_utils import is_safe_path

    _s = get_settings()
    if not is_safe_path(subtitle_path, _s.media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403
    if not is_safe_path(video_path, _s.media_path):
        return jsonify({"error": "video_path must be under the configured media_path"}), 403

    job_id = str(uuid.uuid4())
    _update_job(job_id, "queued")
    _submit_sync(
        current_app._get_current_object(),
        job_id,
        engine,
        subtitle_path,
        video_path,
        None,
        None,
    )

    return jsonify({"job_id": job_id, "status": "started"}), 202


_BULK_VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv", ".flv", ".webm", ".ts"}


def _bulk_videos_from_sonarr(series_id: int | None) -> list[str]:
    """Return Sonarr-managed video paths (one series or the full library)."""
    from sonarr_client import get_sonarr_client

    client = get_sonarr_client()
    if client is None:
        return []
    if series_id is not None:
        files = client.get_episode_files_by_series(int(series_id)) or {}
    else:
        files = {}
        for s in client.get_series() or []:
            files.update(client.get_episode_files_by_series(s.get("id", 0)) or {})
    return [fi.get("path") for fi in files.values() if fi.get("path")]


def _bulk_videos_from_radarr() -> list[str]:
    """Return Radarr-managed movie video paths for movies with a file on disk."""
    from radarr_client import get_radarr_client

    client = get_radarr_client()
    if client is None:
        return []
    out: list[str] = []
    for movie in client.get_movies() or []:
        if not movie.get("hasFile"):
            continue
        # Radarr's /movie endpoint inlines the movie file; older API versions
        # only carry the file id, so fall back to /moviefile lookup when the
        # path field is missing from the inlined record.
        movie_file = movie.get("movieFile") or {}
        path = movie_file.get("path")
        if not path and movie_file.get("id") and hasattr(client, "get_movie_file"):
            try:
                detail = client.get_movie_file(movie_file["id"]) or {}
                path = detail.get("path")
            except Exception:
                path = None
        if path:
            out.append(path)
    return out


def _bulk_videos_from_standalone() -> list[str]:
    """Walk standalone series + movie folders and yield concrete video files."""
    from db.repositories.standalone import StandaloneRepository

    repo = StandaloneRepository()
    folder_paths: list[str] = []
    for s in repo.get_all_standalone_series() or []:
        if s.get("folder_path"):
            folder_paths.append(s["folder_path"])
    for m in repo.get_all_standalone_movies() or []:
        if m.get("folder_path"):
            folder_paths.append(m["folder_path"])

    videos: list[str] = []
    for folder in folder_paths:
        if not os.path.isdir(folder):
            continue
        for root, _dirs, files in os.walk(folder):
            for name in files:
                if os.path.splitext(name)[1].lower() in _BULK_VIDEO_EXTENSIONS:
                    videos.append(os.path.join(root, name))
    return videos


@bp.route("/auto-sync/bulk", methods=["POST"])
def auto_sync_bulk():
    """Bulk auto-sync: queue ffsubsync jobs for every sidecar of every video in scope.

    Body:
        scope: one of "series" (with series_id), "library" (Sonarr only,
               legacy default), "radarr", "standalone", or "all"
        series_id: integer Sonarr series id, required when scope="series"
        engine: "ffsubsync" (default) or "alass"

    Unlike the previous implementation this queues a job per *sidecar*, not
    per video — a video with `.de.srt` + `.en.srt` queues two jobs, fixing
    the gap where bulk runs only synced whichever sidecar `scan_subtitle_sidecars`
    returned first.
    """
    data = request.get_json(force=True, silent=True) or {}
    scope = data.get("scope", "series")
    series_id = data.get("series_id")
    engine = data.get("engine", "ffsubsync")

    if engine not in ("ffsubsync", "alass"):
        return jsonify({"error": f"Unknown engine: {engine!r}"}), 400

    valid_scopes = {"series", "library", "radarr", "standalone", "all"}
    if scope not in valid_scopes:
        return jsonify({"error": f"scope must be one of {sorted(valid_scopes)}"}), 400
    if scope == "series" and series_id is None:
        return jsonify({"error": "scope='series' requires series_id"}), 400

    from config import get_settings, map_path
    from routes.subtitles import scan_subtitle_sidecars
    from security_utils import is_safe_path

    raw_paths: list[str] = []
    sources: dict[str, int] = {}

    if scope == "series":
        raw_paths.extend(_bulk_videos_from_sonarr(series_id))
        sources["sonarr"] = len(raw_paths)
    if scope in ("library", "all"):
        sonarr_paths = _bulk_videos_from_sonarr(None)
        raw_paths.extend(sonarr_paths)
        sources["sonarr"] = len(sonarr_paths)
    if scope in ("radarr", "all"):
        radarr_paths = _bulk_videos_from_radarr()
        raw_paths.extend(radarr_paths)
        sources["radarr"] = len(radarr_paths)
    if scope in ("standalone", "all"):
        standalone_paths = _bulk_videos_from_standalone()
        raw_paths.extend(standalone_paths)
        sources["standalone"] = len(standalone_paths)

    media_path = get_settings().media_path
    queued = 0
    skipped: dict[str, int] = {"unsafe_path": 0, "missing_file": 0, "no_sidecar": 0}
    seen_subs: set[str] = set()

    for raw in raw_paths:
        video_path = map_path(raw)
        if not is_safe_path(video_path, media_path):
            skipped["unsafe_path"] += 1
            continue
        if not os.path.exists(video_path):
            skipped["missing_file"] += 1
            continue
        sidecars = scan_subtitle_sidecars(video_path)
        if not sidecars:
            skipped["no_sidecar"] += 1
            continue
        for entry in sidecars:
            subtitle_path = entry.get("path")
            if not subtitle_path or subtitle_path in seen_subs:
                continue
            if not is_safe_path(subtitle_path, media_path):
                continue
            seen_subs.add(subtitle_path)
            job_id = str(uuid.uuid4())
            _update_job(job_id, "queued")
            _submit_sync(
                current_app._get_current_object(),
                job_id,
                engine,
                subtitle_path,
                video_path,
                None,
                None,
            )
            queued += 1

    return jsonify(
        {
            "queued": queued,
            "engine": engine,
            "scope": scope,
            "videos_considered": sources,
            "skipped": skipped,
        }
    ), 202


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
    except Exception:
        logger.exception("Engine install failed: %s", engine)
        return jsonify({"success": False, "error": "Internal server error"}), 500
