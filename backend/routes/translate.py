"""Translation routes — /translate, /batch, /retranslate, /status, /jobs."""

import ipaddress
import logging
import os
import threading
import time
from urllib.parse import urlparse

import requests
from flask import Blueprint, current_app, jsonify, request

from events import emit_event
from extensions import socketio

bp = Blueprint("translate", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


# --- Phase 28-01: LLM Backend Presets ---

BACKEND_TEMPLATES = [
    {
        "name": "deepseek_v3",
        "display_name": "DeepSeek V3",
        "backend_type": "openai_compat",
        "description": "Excellent quality, very low cost (~$0.07/1M tokens). Requires API key.",
        "config_defaults": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "context_window": 64000,
        },
    },
    {
        "name": "gemini_flash",
        "display_name": "Gemini 1.5 Flash",
        "backend_type": "openai_compat",
        "description": "Fast, cheap Google model with huge context window. Requires API key.",
        "config_defaults": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "model": "gemini-1.5-flash",
            "context_window": 128000,
        },
    },
    {
        "name": "claude_haiku",
        "display_name": "Claude 3 Haiku",
        "backend_type": "openai_compat",
        "description": "Fast Anthropic model, good quality/cost ratio. Requires API key.",
        "config_defaults": {
            "base_url": "https://api.anthropic.com/v1",
            "model": "claude-3-haiku-20240307",
            "context_window": 32000,
        },
    },
    {
        "name": "mistral_medium",
        "display_name": "Mistral Medium",
        "backend_type": "openai_compat",
        "description": "Balanced quality and cost from Mistral AI. Requires API key.",
        "config_defaults": {
            "base_url": "https://api.mistral.ai/v1",
            "model": "mistral-medium-latest",
            "context_window": 32000,
        },
    },
    {
        "name": "lm_studio",
        "display_name": "LM Studio (local)",
        "backend_type": "openai_compat",
        "description": "Run any GGUF model locally. No API key needed. Start LM Studio server first.",
        "config_defaults": {
            "base_url": "http://localhost:1234/v1",
            "model": "local-model",
            "context_window": 8000,
        },
    },
    # --- Community / Fine-tuned Models ---
    {
        "name": "anime_translator_v6",
        "display_name": "Anime Translator V6",
        "backend_type": "ollama",
        "category": "community",
        "description": (
            "Gemma-3-12B fine-tuned on 74k anime subtitle pairs (EN→DE). "
            "Matches qwen2.5:14b quality at 7 GB — no API key, runs fully local via Ollama."
        ),
        "config_defaults": {
            "model": "anime-translator-v6",
            "temperature": "0.3",
        },
        "hf_repo": "sublarr/anime-translator-v6-GGUF",
        "hf_tag": "Q4_K_M",
        "ollama_pull": "hf.co/sublarr/anime-translator-v6-GGUF:Q4_K_M",
        "install_hint": (
            "# Pull directly via Ollama (requires Ollama ≥ 0.3):\n"
            "ollama pull hf.co/sublarr/anime-translator-v6-GGUF:Q4_K_M\n\n"
            "# Or use the Install button above — Sublarr pulls it automatically."
        ),
        "tags": ["fine-tuned", "anime", "en→de", "local", "7GB", "beta"],
        "languages": ["en→de"],
        "size_gb": 7.0,
        "benchmark": {
            "bleu1": 0.281,
            "bleu2": 0.111,
            "length_ratio": 1.02,
            "test_set": "JJK S01E01 vs Crunchyroll DE (30 pairs)",
            "vs_baseline": "beats qwen2.5:14b (0.264) and hunyuan-mt-7b (0.141)",
        },
    },
]


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
    from db.jobs import record_stat, update_job
    from translator import translate_file

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
    """Start an async translation job.
    ---
    post:
      tags:
        - Translate
      summary: Start async translation
      description: Queues a file for asynchronous translation. Returns a job_id for tracking progress via /status endpoint or WebSocket.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                  description: Absolute path to the media file
                force:
                  type: boolean
                  default: false
                  description: Force re-translation even if target exists
                sonarr_series_id:
                  type: integer
                  description: Optional Sonarr series ID for context
                sonarr_episode_id:
                  type: integer
                  description: Optional Sonarr episode ID for context
      responses:
        202:
          description: Job queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  job_id:
                    type: string
                  status:
                    type: string
                  file_path:
                    type: string
        400:
          description: Missing file_path
        404:
          description: File not found
    """
    from config import get_settings
    from db.jobs import create_job

    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Security: ensure file_path is under the configured media_path
    _media_path = os.path.abspath(get_settings().media_path)
    _abs_path = os.path.abspath(file_path)
    if not _abs_path.startswith(_media_path + os.sep):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    arr_context = _build_arr_context(data)
    job = create_job(file_path, force, arr_context)
    _app = current_app._get_current_object()

    def _run_with_ctx():
        with _app.app_context():
            _run_job(job)

    thread = threading.Thread(target=_run_with_ctx, daemon=True)
    thread.start()

    return jsonify({
        "job_id": job["id"],
        "status": "queued",
        "file_path": file_path,
    }), 202


@bp.route("/translate/sync", methods=["POST"])
def translate_sync():
    """Translate a single file (sync or queued).
    ---
    post:
      tags:
        - Translate
      summary: Translate file (sync or queued)
      description: |
        When a job queue is configured, the file is enqueued and the endpoint returns
        202 with job_id; poll GET /status/<job_id> or use WebSocket job_update for result.
        When no queue is available, translation runs in the request and returns 200 with the result.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                  description: Absolute path to the media file
                force:
                  type: boolean
                  default: false
                  description: Force re-translation even if target exists
                sonarr_series_id:
                  type: integer
                sonarr_episode_id:
                  type: integer
      responses:
        200:
          description: Translation completed (no queue; ran in request)
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  output_path:
                    type: string
                  stats:
                    type: object
                    additionalProperties: true
        202:
          description: Job queued; poll /status/<job_id> or use WebSocket for result
          content:
            application/json:
              schema:
                type: object
                properties:
                  job_id:
                    type: string
                  status:
                    type: string
                    example: queued
                  file_path:
                    type: string
        400:
          description: Missing file_path
        404:
          description: File not found
        500:
          description: Translation failed
    """
    from config import get_settings
    from db.jobs import create_job
    from error_handler import TranslationError
    from translator import translate_file

    data = request.get_json() or {}
    file_path = data.get("file_path")
    force = data.get("force", False)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Security: ensure file_path is under the configured media_path
    _media_path = os.path.abspath(get_settings().media_path)
    _abs_path = os.path.abspath(file_path)
    if not _abs_path.startswith(_media_path + os.sep):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    arr_context = _build_arr_context(data)
    queue = getattr(current_app, "job_queue", None)

    if queue is not None:
        job = create_job(file_path, force, arr_context)
        try:
            queue.enqueue(_run_job, job, job_id=job["id"])
        except Exception as e:
            logger.warning("Enqueue sync translate failed, running in request: %s", e)
            queue = None
        else:
            return jsonify({
                "job_id": job["id"],
                "status": "queued",
                "file_path": file_path,
            }), 202

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
    """Get the status of a translation job.
    ---
    get:
      tags:
        - Translate
      summary: Get job status
      description: Returns the current status and result of a translation job.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
          description: Translation job ID
      responses:
        200:
          description: Job details
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  status:
                    type: string
                    enum: [queued, running, completed, failed]
                  file_path:
                    type: string
                  result:
                    type: object
                    additionalProperties: true
                  error:
                    type: string
        404:
          description: Job not found
    """
    from db.jobs import get_job
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@bp.route("/jobs", methods=["GET"])
def list_jobs():
    """Get paginated job history.
    ---
    get:
      tags:
        - Translate
      summary: List translation jobs
      description: Returns a paginated list of translation jobs with optional status filter.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: page
          schema:
            type: integer
            default: 1
          description: Page number
        - in: query
          name: per_page
          schema:
            type: integer
            default: 50
            maximum: 200
          description: Items per page
        - in: query
          name: status
          schema:
            type: string
            enum: [queued, running, completed, failed]
          description: Filter by job status
      responses:
        200:
          description: Paginated job list
          content:
            application/json:
              schema:
                type: object
                properties:
                  jobs:
                    type: array
                    items:
                      type: object
                  total:
                    type: integer
                  page:
                    type: integer
                  per_page:
                    type: integer
    """
    from db.jobs import get_jobs
    try:
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 50, type=int), 200)
        status_filter = request.args.get("status")
        result = get_jobs(page=page, per_page=per_page, status=status_filter)
        return jsonify(result)
    except Exception as e:
        logger.exception("GET /jobs failed: %s", e)
        return jsonify({"error": str(e), "detail": "list_jobs_failed"}), 500


@bp.route("/jobs/<job_id>/retry", methods=["POST"])
def retry_job(job_id):
    """Retry a failed job by creating a new translation job.
    ---
    post:
      tags:
        - Translate
      summary: Retry failed job
      description: Creates a new translation job for a previously failed job. Only failed jobs can be retried.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
          description: Failed job ID to retry
      responses:
        202:
          description: Retry job queued
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  job_id:
                    type: string
                  original_job_id:
                    type: string
                  file_path:
                    type: string
        400:
          description: Job is not in failed status
        404:
          description: Job or file not found
    """
    from config import get_settings
    from db.jobs import create_job, get_job

    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job["status"] != "failed":
        return jsonify({"error": "Only failed jobs can be retried"}), 400

    file_path = job["file_path"]
    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Security: ensure file_path is under the configured media_path
    _media_path = os.path.abspath(get_settings().media_path)
    _abs_path = os.path.abspath(file_path)
    if not _abs_path.startswith(_media_path + os.sep):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    new_job = create_job(file_path, force=True, arr_context=job.get("arr_context"))
    _app = current_app._get_current_object()

    def _run_with_ctx():
        with _app.app_context():
            _run_job(new_job)

    thread = threading.Thread(target=_run_with_ctx, daemon=True)
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
    """Start batch processing of a directory.
    ---
    post:
      tags:
        - Translate
      summary: Start batch translation
      description: >
        Scans a directory for media files and translates them asynchronously.
        Supports dry_run mode to preview files. Progress is emitted via WebSocket (batch_progress event).
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [directory]
              properties:
                directory:
                  type: string
                  description: Directory path to scan for media files
                force:
                  type: boolean
                  default: false
                dry_run:
                  type: boolean
                  default: false
                  description: Preview files without processing
                page:
                  type: integer
                  default: 1
                  description: Page number for dry_run results
                per_page:
                  type: integer
                  default: 100
                  maximum: 500
                callback_url:
                  type: string
                  description: URL for progress callbacks (SSRF-validated)
      responses:
        202:
          description: Batch started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  total_files:
                    type: integer
        400:
          description: Missing directory or invalid callback URL
        404:
          description: Directory not found
        409:
          description: Batch already running
    """
    from translator import scan_directory, translate_file

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

    if not dry_run and not files:
        return jsonify({"error": "No items provided"}), 400

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

    _app = current_app._get_current_object()

    def _run_batch():
        with _app.app_context():
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

                emit_event("batch_complete", snapshot)

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
    """Get batch processing status.
    ---
    get:
      tags:
        - Translate
      summary: Get batch status
      description: Returns the current batch processing progress and state.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Batch state
          content:
            application/json:
              schema:
                type: object
                properties:
                  running:
                    type: boolean
                  total:
                    type: integer
                  processed:
                    type: integer
                  succeeded:
                    type: integer
                  failed:
                    type: integer
                  skipped:
                    type: integer
                  current_file:
                    type: string
                    nullable: true
    """
    with batch_lock:
        return jsonify(dict(batch_state))


# ─── Re-Translation Endpoints ────────────────────────────────────────────────


@bp.route("/retranslate/status", methods=["GET"])
def retranslate_status():
    """Get re-translation status: current config hash and outdated file count.
    ---
    get:
      tags:
        - Translate
      summary: Get re-translation status
      description: Returns the current translation config hash and count of files translated with an older config.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Re-translation status
          content:
            application/json:
              schema:
                type: object
                properties:
                  current_hash:
                    type: string
                  outdated_count:
                    type: integer
                  ollama_model:
                    type: string
                  target_language:
                    type: string
    """
    from config import get_settings
    from db.jobs import get_outdated_jobs_count

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
    """Re-translate a single item (deletes old sub, forces re-translation).
    ---
    post:
      tags:
        - Translate
      summary: Re-translate single item
      description: Deletes existing translated subtitle and forces re-translation with current config. Accepts job ID or wanted item ID.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: integer
          description: Job ID or wanted item ID
      responses:
        202:
          description: Re-translation started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  job_id:
                    type: string
                  file_path:
                    type: string
        404:
          description: Item or file not found
    """
    from config import get_settings
    from db.jobs import create_job, get_job
    from db.wanted import get_wanted_item

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

    # Security: ensure file_path is under the configured media_path
    _media_path = os.path.abspath(get_settings().media_path)
    _abs_path = os.path.abspath(file_path)
    if not _abs_path.startswith(_media_path + os.sep):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

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
    _app = current_app._get_current_object()

    def _run():
        with _app.app_context():
            _run_job(new_job)
            emit_event("translation_complete", {
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
    """Re-translate all outdated items (async with WebSocket progress).
    ---
    post:
      tags:
        - Translate
      summary: Batch re-translate outdated items
      description: >
        Re-translates all items that were translated with an older config hash.
        Progress is emitted via WebSocket (retranslation_progress event).
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Nothing to re-translate
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  count:
                    type: integer
        202:
          description: Batch re-translation started
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  total:
                    type: integer
    """
    from config import get_settings
    from db.jobs import get_outdated_jobs
    from translator import translate_file

    s = get_settings()
    current_hash = s.get_translation_config_hash()
    outdated = get_outdated_jobs(current_hash)

    if not outdated:
        return jsonify({"status": "nothing_to_do", "count": 0})

    total = len(outdated)
    _app = current_app._get_current_object()

    def _run_retranslate():
        with _app.app_context():
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

            emit_event("translation_complete", {
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


# ─── Backend Management Endpoints ─────────────────────────────────────────────


@bp.route("/backends", methods=["GET"])
def list_backends():
    """List all registered translation backends with config status.
    ---
    get:
      tags:
        - Translate
      summary: List translation backends
      description: Returns all registered translation backends with their configuration status and capabilities.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Backend list
          content:
            application/json:
              schema:
                type: object
                properties:
                  backends:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                        display_name:
                          type: string
                        configured:
                          type: boolean
                        config_fields:
                          type: array
                          items:
                            type: object
    """
    from translation import get_translation_manager
    manager = get_translation_manager()
    backends = manager.get_all_backends()
    return jsonify({"backends": backends})


@bp.route("/backends/test/<name>", methods=["POST"])
def test_backend(name):
    """Test a specific translation backend's health.
    ---
    post:
      tags:
        - Translate
      summary: Test translation backend
      description: Runs a health check on the specified translation backend and returns status with optional usage info.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name (e.g. ollama, deepl, openai)
      responses:
        200:
          description: Health check result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
                  usage:
                    type: object
                    additionalProperties: true
        404:
          description: Backend not found
    """
    from translation import get_translation_manager
    manager = get_translation_manager()
    backend = manager.get_backend(name)

    if not backend:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    healthy, message = backend.health_check()
    result = {"healthy": healthy, "message": message}

    # Include usage info if available
    usage = backend.get_usage()
    if usage:
        result["usage"] = usage

    return jsonify(result)


@bp.route("/backends/<name>/config", methods=["PUT"])
def save_backend_config(name):
    """Save configuration for a translation backend.
    ---
    put:
      tags:
        - Translate
      summary: Save backend configuration
      description: Stores key-value pairs in config_entries with backend.<name>.<key> prefix and invalidates cached instance.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: string
              description: Key-value config pairs for the backend
      responses:
        200:
          description: Configuration saved
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
        400:
          description: No configuration data provided
        404:
          description: Backend not found
    """
    from db.config import save_config_entry
    from translation import get_translation_manager

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    # Validate backend exists as a registered class
    manager = get_translation_manager()
    all_backends = manager.get_all_backends()
    known_names = {b["name"] for b in all_backends}
    if name not in known_names:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Store each config entry with namespace prefix
    for key, value in data.items():
        config_key = f"backend.{name}.{key}"
        save_config_entry(config_key, str(value))

    # Invalidate cached instance so next use picks up new config
    manager.invalidate_backend(name)

    return jsonify({"status": "saved"})


@bp.route("/backends/<name>/config", methods=["GET"])
def get_backend_config(name):
    """Get configuration for a translation backend.
    ---
    get:
      tags:
        - Translate
      summary: Get backend configuration
      description: Reads config_entries matching backend.<name>.* prefix. Password fields are masked with '***'.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
          description: Backend name
      responses:
        200:
          description: Backend configuration
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: string
        404:
          description: Backend not found
    """
    from db.config import get_all_config_entries
    from translation import get_translation_manager

    # Validate backend exists
    manager = get_translation_manager()
    all_backends = manager.get_all_backends()
    backend_info = None
    for b in all_backends:
        if b["name"] == name:
            backend_info = b
            break

    if not backend_info:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Load config entries with namespace prefix
    all_entries = get_all_config_entries()
    prefix = f"backend.{name}."
    config = {}
    for key, value in all_entries.items():
        if key.startswith(prefix):
            short_key = key[len(prefix):]
            config[short_key] = value

    # Build set of password field keys for masking
    password_keys = set()
    for field_def in backend_info.get("config_fields", []):
        if field_def.get("type") == "password":
            password_keys.add(field_def["key"])

    # Mask password fields
    for key in config:
        if key in password_keys and config[key]:
            config[key] = "***"

    return jsonify(config)


@bp.route("/backends/templates", methods=["GET"])
def get_backend_templates():
    """Return pre-configured LLM backend templates.
    ---
    get:
      tags:
        - Translate
      summary: List LLM backend templates
      description: Returns pre-configured LLM backend templates that users can use to quickly set up known providers.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Template list
          content:
            application/json:
              schema:
                type: object
                properties:
                  templates:
                    type: array
                    items:
                      type: object
    """
    return jsonify({"templates": BACKEND_TEMPLATES})


@bp.route("/backends/ollama/pull", methods=["POST"])
def ollama_pull_model():
    """Pull an Ollama model by name.
    ---
    post:
      tags:
        - Translate
      summary: Pull an Ollama model
      description: >
        Triggers `ollama pull` for the given model name. Useful for installing
        community models (e.g. anime-translator-v6) directly from the UI.
        The Ollama server must be reachable at the configured URL.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [model]
              properties:
                model:
                  type: string
                  example: "anime-translator-v6"
      responses:
        200:
          description: Pull completed
        400:
          description: Missing model name
        502:
          description: Ollama unreachable or pull failed
    """
    from translation import get_translation_manager

    data = request.get_json() or {}
    model = data.get("model", "").strip()
    if not model:
        return jsonify({"error": "model name required"}), 400

    # Get configured Ollama URL from active backend or fall back to settings
    try:
        manager = get_translation_manager()
        backend = manager.get_backend("ollama")
        ollama_url = backend._url if backend else None
    except Exception:
        ollama_url = None

    if not ollama_url:
        try:
            from config import get_settings
            ollama_url = get_settings().ollama_url
        except Exception:
            ollama_url = "http://localhost:11434"

    try:
        resp = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=600,  # pulls can take several minutes
        )
        resp.raise_for_status()
        return jsonify({"ok": True, "model": model, "status": resp.json().get("status", "done")})
    except requests.Timeout:
        return jsonify({"error": f"Pull timed out for '{model}' — try pulling manually via CLI"}), 502
    except requests.ConnectionError:
        return jsonify({"error": f"Cannot connect to Ollama at {ollama_url}"}), 502
    except requests.HTTPError as e:
        return jsonify({"error": f"Ollama pull failed: {e}"}), 502
    except Exception as e:
        logger.exception("ollama_pull_model failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/backends/stats", methods=["GET"])
def backend_stats():
    """Get translation stats for all backends.
    ---
    get:
      tags:
        - Translate
      summary: Get backend statistics
      description: Returns translation statistics (request count, errors, avg duration) for all translation backends.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Backend statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  stats:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
    """
    from db.translation import get_backend_stats
    stats = get_backend_stats()
    return jsonify({"stats": stats})


# ---------------------------------------------------------------------------
# Translation Memory Cache Endpoints
# ---------------------------------------------------------------------------

@bp.route("/translation-memory/stats", methods=["GET"])
def translation_memory_stats():
    """Return statistics for the translation memory cache.
    ---
    get:
      tags:
        - Translate
      summary: Translation memory cache statistics
      description: Returns the number of entries stored in the persistent translation memory cache.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache statistics
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: integer
                    description: Total cached translation entries
    """
    try:
        from db.translation import get_translation_cache_stats
        stats = get_translation_cache_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error("Failed to get translation memory stats: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route("/translation-memory/cache", methods=["DELETE"])
def clear_translation_memory_cache():
    """Clear all entries from the translation memory cache.
    ---
    delete:
      tags:
        - Translate
      summary: Clear translation memory cache
      description: Deletes all cached translations from the persistent translation memory. This does not affect the glossary or any subtitle files.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Cache cleared
          content:
            application/json:
              schema:
                type: object
                properties:
                  cleared:
                    type: boolean
                  deleted:
                    type: integer
                    description: Number of rows deleted
    """
    try:
        from db.translation import clear_translation_cache
        deleted = clear_translation_cache()
        logger.info("Translation memory cache cleared: %d entries deleted", deleted)
        return jsonify({"cleared": True, "deleted": deleted})
    except Exception as e:
        logger.error("Failed to clear translation memory cache: %s", e)
        return jsonify({"error": str(e)}), 500
