"""Sublarr Flask API server with Blueprint-based routing.

Serves the React frontend as SPA and provides /api/v1/ endpoints
for translation management, job tracking, and *arr integrations.
"""

import os
import time
import logging
import threading
from collections import OrderedDict

import requests
from flask import Flask, Blueprint, request, jsonify, send_from_directory
from flask_socketio import SocketIO

from config import get_settings, reload_settings
from auth import init_auth
from database import (
    get_db, create_job, update_job, get_job, get_jobs,
    get_pending_job_count, record_stat, get_stats_summary,
    get_all_config_entries, save_config_entry,
)
from translator import translate_file, scan_directory
from ollama_client import check_ollama_health

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── Flask App Setup ──────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Initialize authentication
init_auth(app)

# Initialize database
get_db()

# ─── API Blueprint ────────────────────────────────────────────────────────────

api = Blueprint("api", __name__, url_prefix="/api/v1")

# Batch state (still in-memory for real-time tracking)
batch_state = {
    "running": False,
    "total": 0,
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "skipped": 0,
    "current_file": None,
    "errors": [],
}
batch_lock = threading.Lock()

# In-memory stats for quick access (synced to DB)
stats_lock = threading.Lock()
_memory_stats = {
    "started_at": time.time(),
    "upgrades": {"srt_to_ass_translated": 0, "srt_to_ass_bazarr": 0, "srt_upgrade_skipped": 0},
    "bazarr_synced": 0,
    "quality_warnings": 0,
}


def _update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                record_stat(success=True, skipped=True)
                reason = s.get("reason", "")
                if "upgrade" in reason.lower() and "bazarr" in reason.lower():
                    _memory_stats["upgrades"]["srt_to_ass_bazarr"] += 1
                elif "no ASS upgrade" in reason:
                    _memory_stats["upgrades"]["srt_upgrade_skipped"] += 1
            else:
                fmt = s.get("format", "")
                source = s.get("source", "")
                record_stat(success=True, skipped=False, fmt=fmt, source=source)
                if s.get("upgrade_from_srt"):
                    _memory_stats["upgrades"]["srt_to_ass_translated"] += 1
                if s.get("quality_warnings"):
                    _memory_stats["quality_warnings"] += len(s["quality_warnings"])
        else:
            record_stat(success=False)


def _run_job(job_data):
    """Execute a translation job in a background thread."""
    job_id = job_data["id"]
    try:
        update_job(job_id, "running")

        result = translate_file(
            job_data["file_path"],
            force=job_data.get("force", False),
            bazarr_context=job_data.get("bazarr_context"),
        )

        status = "completed" if result["success"] else "failed"
        update_job(job_id, status, result=result, error=result.get("error"))
        _update_stats(result)

        # Emit WebSocket event
        socketio.emit("job_update", {
            "id": job_id,
            "status": status,
            "result": result,
        })

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, "failed", error=str(e))
        record_stat(success=False)


def _build_bazarr_context(data):
    """Build bazarr_context from request data if Sonarr IDs are present."""
    series_id = data.get("sonarr_series_id")
    episode_id = data.get("sonarr_episode_id")
    if series_id and episode_id:
        return {
            "sonarr_series_id": series_id,
            "sonarr_episode_id": episode_id,
        }
    return None


# ─── Health & Status Endpoints ────────────────────────────────────────────────


@api.route("/health", methods=["GET"])
def health():
    """Health check endpoint (no auth required)."""
    healthy, message = check_ollama_health()

    # Check all configured services
    service_status = {"ollama": message}

    # Bazarr
    try:
        from bazarr_client import get_bazarr_client
        bazarr = get_bazarr_client()
        if bazarr:
            b_healthy, b_msg = bazarr.health_check()
            service_status["bazarr"] = b_msg if b_healthy else f"unhealthy: {b_msg}"
        else:
            service_status["bazarr"] = "not configured"
    except Exception:
        service_status["bazarr"] = "error"

    # Sonarr
    try:
        from sonarr_client import get_sonarr_client
        sonarr = get_sonarr_client()
        if sonarr:
            s_healthy, s_msg = sonarr.health_check()
            service_status["sonarr"] = s_msg if s_healthy else f"unhealthy: {s_msg}"
        else:
            service_status["sonarr"] = "not configured"
    except Exception:
        service_status["sonarr"] = "error"

    # Radarr
    try:
        from radarr_client import get_radarr_client
        radarr = get_radarr_client()
        if radarr:
            r_healthy, r_msg = radarr.health_check()
            service_status["radarr"] = r_msg if r_healthy else f"unhealthy: {r_msg}"
        else:
            service_status["radarr"] = "not configured"
    except Exception:
        service_status["radarr"] = "error"

    # Jellyfin
    try:
        from jellyfin_client import get_jellyfin_client
        jellyfin = get_jellyfin_client()
        if jellyfin:
            j_healthy, j_msg = jellyfin.health_check()
            service_status["jellyfin"] = j_msg if j_healthy else f"unhealthy: {j_msg}"
        else:
            service_status["jellyfin"] = "not configured"
    except Exception:
        service_status["jellyfin"] = "error"

    status_code = 200 if healthy else 503
    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "version": "0.1.0",
        "services": service_status,
    }), status_code


# ─── Translation Endpoints ────────────────────────────────────────────────────


@api.route("/translate", methods=["POST"])
def translate_async():
    """Start an async translation job."""
    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    bazarr_context = _build_bazarr_context(data)
    job = create_job(file_path, force, bazarr_context)
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job["id"],
        "status": "queued",
        "file_path": file_path,
    }), 202


@api.route("/translate/sync", methods=["POST"])
def translate_sync():
    """Translate a single file synchronously."""
    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    bazarr_context = _build_bazarr_context(data)

    try:
        result = translate_file(file_path, force=force, bazarr_context=bazarr_context)
        _update_stats(result)
        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api.route("/translate/wanted", methods=["POST"])
def translate_wanted():
    """Translate episodes from Bazarr's wanted list (anime only)."""
    data = request.get_json() or {}
    max_episodes = data.get("max_episodes", 5)

    try:
        from bazarr_client import get_bazarr_client
        bazarr = get_bazarr_client()
    except Exception:
        bazarr = None

    if not bazarr:
        return jsonify({"error": "Bazarr not configured or unreachable"}), 503

    episodes = bazarr.get_wanted_anime(limit=max_episodes)
    if not episodes:
        return jsonify({"status": "no_wanted", "message": "No anime episodes in wanted list"}), 200

    job_ids = []
    for ep in episodes[:max_episodes]:
        path = ep.get("path")
        if not path or not os.path.exists(path):
            continue
        bazarr_context = {
            "sonarr_series_id": ep["sonarr_series_id"],
            "sonarr_episode_id": ep["sonarr_episode_id"],
        }
        job = create_job(path, bazarr_context=bazarr_context)
        job_ids.append(job["id"])
        thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
        thread.start()
        time.sleep(0.5)

    return jsonify({
        "status": "started",
        "episodes_queued": len(job_ids),
        "job_ids": job_ids,
        "episodes": [
            {
                "series": ep["series_title"],
                "episode": ep["episode_number"],
                "title": ep["episode_title"],
            }
            for ep in episodes[:max_episodes]
        ],
    }), 202


# ─── Job & Status Endpoints ──────────────────────────────────────────────────


@api.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get the status of a translation job."""
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@api.route("/jobs", methods=["GET"])
def list_jobs():
    """Get paginated job history."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    status_filter = request.args.get("status")
    result = get_jobs(page=page, per_page=per_page, status=status_filter)
    return jsonify(result)


@api.route("/status/bazarr", methods=["GET"])
def bazarr_status():
    """Get Bazarr integration status."""
    try:
        from bazarr_client import get_bazarr_client
        bazarr = get_bazarr_client()
    except Exception:
        bazarr = None

    if not bazarr:
        return jsonify({
            "configured": False,
            "message": "Bazarr not configured",
        })

    healthy, message = bazarr.health_check()
    wanted_count = bazarr.get_wanted_anime_total() if healthy else 0

    with stats_lock:
        synced = _memory_stats.get("bazarr_synced", 0)

    return jsonify({
        "configured": True,
        "reachable": healthy,
        "message": message,
        "wanted_anime_count": wanted_count,
        "translations_synced": synced,
    })


# ─── Batch Endpoints ─────────────────────────────────────────────────────────


@api.route("/batch", methods=["POST"])
def batch_start():
    """Start batch processing of a directory."""
    data = request.get_json() or {}
    directory = data.get("directory")
    force = data.get("force", False)
    dry_run = data.get("dry_run", False)
    page = data.get("page", 1)
    per_page = data.get("per_page", 100)
    callback_url = data.get("callback_url")

    if not directory:
        return jsonify({"error": "directory is required"}), 400

    if not os.path.isdir(directory):
        return jsonify({"error": f"Directory not found: {directory}"}), 404

    files = scan_directory(directory, force=force)

    if dry_run:
        total_files = len(files)
        total_pages = max(1, (total_files + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        end = start + per_page
        page_files = files[start:end]

        return jsonify({
            "dry_run": True,
            "files_found": total_files,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "files": [
                {
                    "path": f["path"],
                    "target_status": f["target_status"],
                    "size_mb": round(f["size_mb"], 1),
                }
                for f in page_files
            ],
        })

    with batch_lock:
        if batch_state["running"]:
            return jsonify({"error": "Batch already running"}), 409

        batch_state.update({
            "running": True,
            "total": len(files),
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "current_file": None,
            "errors": [],
        })

    def _run_batch():
        try:
            for f in files:
                with batch_lock:
                    batch_state["current_file"] = f["path"]

                try:
                    result = translate_file(f["path"], force=force)
                    with batch_lock:
                        batch_state["processed"] += 1
                        if result["success"]:
                            if result["stats"].get("skipped"):
                                batch_state["skipped"] += 1
                            else:
                                batch_state["succeeded"] += 1
                        else:
                            batch_state["failed"] += 1
                            batch_state["errors"].append({
                                "file": f["path"],
                                "error": result.get("error"),
                            })

                    _update_stats(result)

                    # WebSocket notification
                    socketio.emit("batch_progress", {
                        "processed": batch_state["processed"],
                        "total": batch_state["total"],
                        "current_file": f["path"],
                        "success": result["success"],
                    })

                    # Callback notification
                    if callback_url:
                        _send_callback(callback_url, {
                            "event": "file_completed",
                            "file": f["path"],
                            "success": result["success"],
                            "processed": batch_state["processed"],
                            "total": batch_state["total"],
                        })

                except Exception as e:
                    logger.exception("Batch: failed on %s", f["path"])
                    with batch_lock:
                        batch_state["processed"] += 1
                        batch_state["failed"] += 1
                        batch_state["errors"].append({
                            "file": f["path"],
                            "error": str(e),
                        })
        finally:
            with batch_lock:
                batch_state["running"] = False
                batch_state["current_file"] = None

            socketio.emit("batch_completed", dict(batch_state))

            if callback_url:
                _send_callback(callback_url, {
                    "event": "batch_completed",
                    "total": batch_state["total"],
                    "succeeded": batch_state["succeeded"],
                    "failed": batch_state["failed"],
                    "skipped": batch_state["skipped"],
                })

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "total_files": len(files),
    }), 202


def _send_callback(url, data):
    """Send a callback notification (fire-and-forget)."""
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.warning("Callback to %s failed: %s", url, e)


@api.route("/batch/status", methods=["GET"])
def batch_status_endpoint():
    """Get batch processing status."""
    with batch_lock:
        return jsonify(dict(batch_state))


# ─── Stats Endpoint ───────────────────────────────────────────────────────────


@api.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics."""
    db_stats = get_stats_summary()

    with stats_lock:
        uptime = time.time() - _memory_stats["started_at"]
        memory_extras = {
            "upgrades": dict(_memory_stats["upgrades"]),
            "bazarr_synced": _memory_stats["bazarr_synced"],
            "quality_warnings": _memory_stats["quality_warnings"],
        }

    pending = get_pending_job_count()

    return jsonify({
        **db_stats,
        **memory_extras,
        "pending_jobs": pending,
        "uptime_seconds": round(uptime),
        "batch_running": batch_state["running"],
    })


# ─── Config Endpoints ────────────────────────────────────────────────────────


@api.route("/config", methods=["GET"])
def get_config():
    """Get current configuration (without secrets)."""
    s = get_settings()
    return jsonify(s.get_safe_config())


@api.route("/config", methods=["PUT"])
def update_config():
    """Update configuration values."""
    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No config values provided"}), 400

    for key, value in data.items():
        save_config_entry(key, str(value))

    return jsonify({"status": "saved", "updated_keys": list(data.keys())})


# ─── Library Endpoint ─────────────────────────────────────────────────────────


@api.route("/library", methods=["GET"])
def get_library():
    """Get series/movies with subtitle status."""
    result = {"series": [], "movies": []}

    try:
        from sonarr_client import get_sonarr_client
        sonarr = get_sonarr_client()
        if sonarr:
            result["series"] = sonarr.get_library_info()
    except Exception as e:
        logger.warning("Failed to get Sonarr library: %s", e)

    try:
        from radarr_client import get_radarr_client
        radarr = get_radarr_client()
        if radarr:
            result["movies"] = radarr.get_library_info()
    except Exception as e:
        logger.warning("Failed to get Radarr library: %s", e)

    return jsonify(result)


# ─── Webhook Endpoints ───────────────────────────────────────────────────────


@api.route("/webhook/sonarr", methods=["POST"])
def webhook_sonarr():
    """Handle Sonarr webhook (OnDownload event)."""
    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    # Extract file info from Sonarr webhook payload
    episode_file = data.get("episodeFile", {})
    file_path = episode_file.get("path", "")
    series = data.get("series", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    logger.info("Sonarr webhook: %s - %s", series.get("title", "Unknown"), file_path)

    # Delayed processing (wait for Bazarr to handle first)
    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    def _delayed_translate():
        if delay > 0:
            logger.info("Waiting %d minutes before translating (webhook delay)...", s.webhook_delay_minutes)
            time.sleep(delay)
        job = create_job(file_path)
        _run_job(job)

    thread = threading.Thread(target=_delayed_translate, daemon=True)
    thread.start()

    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
    }), 202


@api.route("/webhook/radarr", methods=["POST"])
def webhook_radarr():
    """Handle Radarr webhook (OnDownload event)."""
    data = request.get_json() or {}
    event_type = data.get("eventType", "")

    if event_type == "Test":
        return jsonify({"status": "ok", "message": "Test received"}), 200

    if event_type != "Download":
        return jsonify({"status": "ignored", "event": event_type}), 200

    movie_file = data.get("movieFile", {})
    file_path = movie_file.get("path", "")
    movie = data.get("movie", {})

    if not file_path:
        return jsonify({"error": "No file path in webhook payload"}), 400

    logger.info("Radarr webhook: %s - %s", movie.get("title", "Unknown"), file_path)

    s = get_settings()
    delay = s.webhook_delay_minutes * 60

    def _delayed_translate():
        if delay > 0:
            logger.info("Waiting %d minutes before translating (webhook delay)...", s.webhook_delay_minutes)
            time.sleep(delay)
        job = create_job(file_path)
        _run_job(job)

    thread = threading.Thread(target=_delayed_translate, daemon=True)
    thread.start()

    return jsonify({
        "status": "queued",
        "file_path": file_path,
        "delay_minutes": s.webhook_delay_minutes,
    }), 202


# ─── Logs Endpoint ────────────────────────────────────────────────────────────


@api.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries."""
    # Read from log file if available, otherwise return empty
    log_file = os.environ.get("SUBLARR_LOG_FILE", "/config/sublarr.log")
    lines = request.args.get("lines", 200, type=int)
    level = request.args.get("level", "").upper()

    log_entries = []
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                all_lines = f.readlines()
                recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
                for line in recent:
                    if level and f"[{level}]" not in line:
                        continue
                    log_entries.append(line.strip())
        except Exception as e:
            logger.warning("Failed to read log file: %s", e)

    return jsonify({
        "entries": log_entries,
        "total": len(log_entries),
    })


# ─── WebSocket Events ────────────────────────────────────────────────────────


@socketio.on("connect")
def handle_connect():
    """Handle WebSocket connection."""
    logger.debug("WebSocket client connected")


@socketio.on("disconnect")
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.debug("WebSocket client disconnected")


# ─── Register Blueprint & SPA Fallback ────────────────────────────────────────

app.register_blueprint(api)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    """Serve the React SPA frontend."""
    static_dir = app.static_folder or "static"

    # Try to serve the exact file first
    if path and os.path.exists(os.path.join(static_dir, path)):
        return send_from_directory(static_dir, path)

    # Fallback to index.html for SPA routing
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(static_dir, "index.html")

    # No frontend built yet — return API info
    return jsonify({
        "name": "Sublarr",
        "version": "0.1.0",
        "api": "/api/v1/health",
        "message": "Frontend not built. Run 'npm run build' in frontend/ first.",
    })


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=settings.port, debug=True)
