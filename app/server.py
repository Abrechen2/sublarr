"""Flask API server for anime subtitle translation."""

import os
import uuid
import time
import logging
import threading
from collections import OrderedDict

import requests
from flask import Flask, request, jsonify

from translator import translate_file, scan_directory
from ollama_client import check_ollama_health

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Job tracking
jobs = OrderedDict()  # job_id -> job_info
jobs_lock = threading.Lock()
MAX_JOBS_HISTORY = 500

# Batch state
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

# Stats (thread-safe via stats_lock)
stats = {
    "total_translated": 0,
    "total_failed": 0,
    "total_skipped": 0,
    "started_at": time.time(),
    "by_format": {"ass": 0, "srt": 0},
    "by_source": {},
    "upgrades": {"srt_to_ass_translated": 0, "srt_to_ass_bazarr": 0, "srt_upgrade_skipped": 0},
    "bazarr_synced": 0,
    "quality_warnings": 0,
}
stats_lock = threading.Lock()


def _update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                stats["total_skipped"] += 1
                reason = s.get("reason", "")
                if "upgrade" in reason.lower() and "bazarr" in reason.lower():
                    stats["upgrades"]["srt_to_ass_bazarr"] += 1
                elif "no ASS upgrade" in reason:
                    stats["upgrades"]["srt_upgrade_skipped"] += 1
            else:
                stats["total_translated"] += 1
                fmt = s.get("format", "")
                if fmt in stats["by_format"]:
                    stats["by_format"][fmt] += 1
                source = s.get("source", "")
                if source:
                    stats["by_source"][source] = stats["by_source"].get(source, 0) + 1
                if s.get("upgrade_from_srt"):
                    stats["upgrades"]["srt_to_ass_translated"] += 1
                if s.get("quality_warnings"):
                    stats["quality_warnings"] += len(s["quality_warnings"])
        else:
            stats["total_failed"] += 1


def _create_job(file_path, force=False, bazarr_context=None):
    """Create a new translation job."""
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "file_path": file_path,
        "force": force,
        "bazarr_context": bazarr_context,
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": time.time(),
        "completed_at": None,
    }
    with jobs_lock:
        jobs[job_id] = job
        while len(jobs) > MAX_JOBS_HISTORY:
            jobs.popitem(last=False)
    return job


def _run_job(job):
    """Execute a translation job in a background thread."""
    job_id = job["id"]
    try:
        with jobs_lock:
            jobs[job_id]["status"] = "running"

        result = translate_file(
            job["file_path"],
            force=job["force"],
            bazarr_context=job.get("bazarr_context"),
        )

        with jobs_lock:
            jobs[job_id]["status"] = "completed" if result["success"] else "failed"
            jobs[job_id]["result"] = result
            jobs[job_id]["error"] = result.get("error")
            jobs[job_id]["completed_at"] = time.time()

        _update_stats(result)

    except Exception as e:
        logger.exception("Job %s failed", job_id)
        with jobs_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["completed_at"] = time.time()
        with stats_lock:
            stats["total_failed"] += 1


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


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    healthy, message = check_ollama_health()

    # Also check Bazarr if configured
    bazarr_status = "not configured"
    try:
        from bazarr_client import get_bazarr_client
        bazarr = get_bazarr_client()
        if bazarr:
            b_healthy, b_msg = bazarr.health_check()
            bazarr_status = b_msg if b_healthy else f"unhealthy: {b_msg}"
    except Exception:
        bazarr_status = "error"

    status_code = 200 if healthy else 503
    return jsonify({
        "status": "healthy" if healthy else "unhealthy",
        "ollama": message,
        "bazarr": bazarr_status,
    }), status_code


@app.route("/translate", methods=["POST"])
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
    job = _create_job(file_path, force, bazarr_context)
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job["id"],
        "status": "queued",
        "file_path": file_path,
    }), 202


@app.route("/translate/sync", methods=["POST"])
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


@app.route("/translate/wanted", methods=["POST"])
def translate_wanted():
    """Translate episodes from Bazarr's wanted list (anime only).

    Fetches wanted anime episodes from Bazarr and starts sequential translation.
    """
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

    # Start background processing
    job_ids = []
    for ep in episodes[:max_episodes]:
        path = ep.get("path")
        if not path or not os.path.exists(path):
            continue
        bazarr_context = {
            "sonarr_series_id": ep["sonarr_series_id"],
            "sonarr_episode_id": ep["sonarr_episode_id"],
        }
        job = _create_job(path, bazarr_context=bazarr_context)
        job_ids.append(job["id"])
        thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
        thread.start()
        # Small delay to avoid hammering Ollama
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


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get the status of a translation job."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job)


@app.route("/status/bazarr", methods=["GET"])
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
            "message": "Bazarr not configured (BAZARR_URL or BAZARR_API_KEY missing)",
        })

    healthy, message = bazarr.health_check()
    wanted_count = bazarr.get_wanted_anime_total() if healthy else 0

    with stats_lock:
        synced = stats.get("bazarr_synced", 0)

    return jsonify({
        "configured": True,
        "reachable": healthy,
        "message": message,
        "wanted_anime_count": wanted_count,
        "translations_synced": synced,
    })


@app.route("/batch", methods=["POST"])
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
                    "german_status": f["german_status"],
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


@app.route("/batch/status", methods=["GET"])
def batch_status_endpoint():
    """Get batch processing status."""
    with batch_lock:
        return jsonify(dict(batch_state))


@app.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics."""
    with stats_lock:
        uptime = time.time() - stats["started_at"]
        snapshot = {
            "total_translated": stats["total_translated"],
            "total_failed": stats["total_failed"],
            "total_skipped": stats["total_skipped"],
            "by_format": dict(stats["by_format"]),
            "by_source": dict(stats["by_source"]),
            "upgrades": dict(stats["upgrades"]),
            "bazarr_synced": stats["bazarr_synced"],
            "quality_warnings": stats["quality_warnings"],
        }

    with jobs_lock:
        pending_jobs = sum(
            1 for j in jobs.values() if j["status"] in ("queued", "running")
        )

    snapshot["pending_jobs"] = pending_jobs
    snapshot["uptime_seconds"] = round(uptime)
    snapshot["batch_running"] = batch_state["running"]

    return jsonify(snapshot)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5765, debug=True)
