"""Translation routes — /translate, /batch, /retranslate, /status, /jobs."""

import os
import time
import logging
import threading
import ipaddress
from urllib.parse import urlparse

import requests
from flask import Blueprint, request, jsonify

from extensions import socketio

bp = Blueprint("translate", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


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
    "upgrades": {"srt_to_ass_translated": 0, "srt_upgrade_skipped": 0},
    "quality_warnings": 0,
}


def _update_stats(result):
    """Update stats from a translation result (thread-safe)."""
    from db.jobs import record_stat

    with stats_lock:
        if result["success"]:
            s = result.get("stats", {})
            if s.get("skipped"):
                record_stat(success=True, skipped=True)
                reason = s.get("reason", "")
                if "no ASS upgrade" in reason:
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
    from translator import translate_file
    from db.jobs import update_job, record_stat

    job_id = job_data["id"]
    try:
        update_job(job_id, "running")

        result = translate_file(
            job_data["file_path"],
            force=job_data.get("force", False),
            arr_context=job_data.get("arr_context"),
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


def _build_arr_context(data):
    """Build arr_context from request data if Sonarr IDs are present."""
    series_id = data.get("sonarr_series_id")
    episode_id = data.get("sonarr_episode_id")
    if series_id and episode_id:
        return {
            "sonarr_series_id": series_id,
            "sonarr_episode_id": episode_id,
        }
    return None


def _validate_callback_url(url):
    """Validate callback URL to prevent SSRF attacks.

    Blocks private IPs, localhost, and non-HTTP schemes.

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "No hostname in URL"

    # Block localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return False, "Localhost callbacks are not allowed"

    # Block private/reserved IP ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
            return False, f"Private/reserved IP not allowed: {hostname}"
    except ValueError:
        # hostname is not an IP — that's fine (it's a domain name)
        pass

    return True, None


def _send_callback(url, data):
    """Send a callback notification (fire-and-forget)."""
    try:
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        logger.warning("Callback to %s failed: %s", url, e)


# ─── Translation Endpoints ────────────────────────────────────────────────────


@bp.route("/translate", methods=["POST"])
def translate_async():
    """Start an async translation job."""
    from db.jobs import create_job
    from error_handler import TranslationError

    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    arr_context = _build_arr_context(data)
    job = create_job(file_path, force, arr_context)
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job["id"],
        "status": "queued",
        "file_path": file_path,
    }), 202


@bp.route("/translate/sync", methods=["POST"])
def translate_sync():
    """Translate a single file synchronously."""
    from translator import translate_file
    from error_handler import TranslationError

    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    arr_context = _build_arr_context(data)

    try:
        result = translate_file(file_path, force=force, arr_context=arr_context)
        _update_stats(result)
        status_code = 200 if result["success"] else 500
        return jsonify(result), status_code
    except Exception as e:
        raise TranslationError(
            str(e),
            context={"file_path": file_path},
            troubleshooting="Check that Ollama is running and the file is accessible.",
        ) from e


# ─── Job & Status Endpoints ──────────────────────────────────────────────────


@bp.route("/status/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get the status of a translation job."""
    from db.jobs import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@bp.route("/jobs", methods=["GET"])
def list_jobs():
    """Get paginated job history."""
    from db.jobs import get_jobs
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    status_filter = request.args.get("status")
    result = get_jobs(page=page, per_page=per_page, status=status_filter)
    return jsonify(result)


@bp.route("/jobs/<job_id>/retry", methods=["POST"])
def retry_job(job_id):
    """Retry a failed job by creating a new translation job."""
    from db.jobs import get_job, create_job

    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] != "failed":
        return jsonify({"error": "Only failed jobs can be retried"}), 400

    file_path = job["file_path"]
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    new_job = create_job(file_path, force=True, arr_context=job.get("arr_context"))
    thread = threading.Thread(target=_run_job, args=(new_job,), daemon=True)
    thread.start()

    return jsonify({
        "status": "queued",
        "job_id": new_job["id"],
        "original_job_id": job_id,
        "file_path": file_path,
    }), 202


# ─── Batch Endpoints ─────────────────────────────────────────────────────────


@bp.route("/batch", methods=["POST"])
def batch_start():
    """Start batch processing of a directory."""
    from translator import translate_file, scan_directory

    data = request.get_json() or {}
    directory = data.get("directory")
    force = data.get("force", False)
    dry_run = data.get("dry_run", False)
    page = data.get("page", 1)
    per_page = min(data.get("per_page", 100), 500)
    callback_url = data.get("callback_url")

    if not directory:
        return jsonify({"error": "directory is required"}), 400

    if callback_url:
        valid, err = _validate_callback_url(callback_url)
        if not valid:
            return jsonify({"error": f"Invalid callback_url: {err}"}), 400

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
                snapshot = dict(batch_state)

            socketio.emit("batch_completed", snapshot)

            try:
                from notifier import send_notification
                send_notification(
                    title="Sublarr: Batch Complete",
                    body=f"Batch finished: {snapshot['succeeded']} succeeded, {snapshot['failed']} failed, {snapshot['skipped']} skipped",
                    event_type="batch_complete",
                )
            except Exception:
                pass

            if callback_url:
                _send_callback(callback_url, {
                    "event": "batch_completed",
                    "total": snapshot["total"],
                    "succeeded": snapshot["succeeded"],
                    "failed": snapshot["failed"],
                    "skipped": snapshot["skipped"],
                })

    thread = threading.Thread(target=_run_batch, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "total_files": len(files),
    }), 202


@bp.route("/batch/status", methods=["GET"])
def batch_status_endpoint():
    """Get batch processing status."""
    with batch_lock:
        return jsonify(dict(batch_state))


# ─── Re-Translation Endpoints ────────────────────────────────────────────────


@bp.route("/retranslate/status", methods=["GET"])
def retranslate_status():
    """Get re-translation status: current config hash and outdated file count."""
    from db.jobs import get_outdated_jobs_count
    from config import get_settings

    s = get_settings()
    current_hash = s.get_translation_config_hash()
    outdated = get_outdated_jobs_count(current_hash)

    return jsonify({
        "current_hash": current_hash,
        "outdated_count": outdated,
        "ollama_model": s.ollama_model,
        "target_language": s.target_language,
    })


@bp.route("/retranslate/<int:job_id>", methods=["POST"])
def retranslate_single(job_id):
    """Re-translate a single item (deletes old sub, forces re-translation)."""
    from db.jobs import get_job, create_job
    from db.wanted import get_wanted_item
    from config import get_settings

    job = get_job(str(job_id))
    if not job:
        # Try as wanted item ID
        item = get_wanted_item(job_id)
        if not item:
            return jsonify({"error": "Item not found"}), 404
        file_path = item["file_path"]
    else:
        file_path = job["file_path"]

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Delete existing translated subtitle
    s = get_settings()
    base = os.path.splitext(file_path)[0]
    for fmt in ["ass", "srt"]:
        for pattern in s.get_target_patterns(fmt):
            target = base + pattern
            if os.path.exists(target):
                os.remove(target)
                logger.info("Re-translate: removed %s", target)

    # Re-translate with force
    new_job = create_job(file_path, force=True)

    def _run():
        _run_job(new_job)
        socketio.emit("retranslation_completed", {
            "file_path": file_path,
            "job_id": new_job["id"],
        })

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "job_id": new_job["id"],
        "file_path": file_path,
    }), 202


@bp.route("/retranslate/batch", methods=["POST"])
def retranslate_batch():
    """Re-translate all outdated items (async with WebSocket progress)."""
    from db.jobs import get_outdated_jobs
    from translator import translate_file
    from config import get_settings

    s = get_settings()
    current_hash = s.get_translation_config_hash()
    outdated = get_outdated_jobs(current_hash)

    if not outdated:
        return jsonify({"status": "nothing_to_do", "count": 0})

    total = len(outdated)

    def _run_retranslate():
        processed = 0
        succeeded = 0
        failed = 0

        for job in outdated:
            file_path = job["file_path"]
            if not os.path.exists(file_path):
                processed += 1
                failed += 1
                continue

            # Remove existing target subs
            base = os.path.splitext(file_path)[0]
            for fmt in ["ass", "srt"]:
                for pattern in s.get_target_patterns(fmt):
                    target = base + pattern
                    if os.path.exists(target):
                        os.remove(target)

            try:
                result = translate_file(file_path, force=True)
                processed += 1
                if result["success"]:
                    succeeded += 1
                else:
                    failed += 1
            except Exception as e:
                processed += 1
                failed += 1
                logger.warning("Re-translate batch: error on %s: %s", file_path, e)

            socketio.emit("retranslation_progress", {
                "processed": processed,
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "current_file": file_path,
            })

        socketio.emit("retranslation_completed", {
            "count": processed,
            "succeeded": succeeded,
            "failed": failed,
        })

    thread = threading.Thread(target=_run_retranslate, daemon=True)
    thread.start()

    return jsonify({
        "status": "started",
        "total": total,
    }), 202
