"""Core translation endpoints — /translate, /translate/sync, /translate/disable.

Job management endpoints (/status/<id>, /jobs, /jobs/<id>/retry) live in
routes/translate/jobs.py (B1Tc split, 2026-04-18).
"""

import logging
import os

from flask import current_app, jsonify, request

from routes.translate import bp
from routes.translate._helpers import _build_arr_context, _run_job, _update_stats
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


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
    if not is_safe_path(file_path, get_settings().media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    arr_context = _build_arr_context(data)
    job = create_job(file_path, force, arr_context)
    current_app.job_queue.enqueue(_run_job, job, job_id=job["id"])

    return jsonify(
        {
            "job_id": job["id"],
            "status": "queued",
            "file_path": file_path,
        }
    ), 202


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
    if not is_safe_path(file_path, get_settings().media_path):
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
            return jsonify(
                {
                    "job_id": job["id"],
                    "status": "queued",
                    "file_path": file_path,
                }
            ), 202

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


@bp.route("/translate/disable", methods=["POST"])
def disable_translation():
    """Disable the translation feature and cancel all queued jobs.
    ---
    post:
      tags:
        - Translate
      summary: Disable translation feature
      description: Sets translation_enabled=false in config and cancels all queued translation jobs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Translation disabled
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  cancelled_jobs:
                    type: integer
    """
    from cache_response import invalidate_response_cache
    from config import reload_settings
    from db.config import get_all_config_entries, save_config_entry
    from db.jobs import cancel_queued_jobs

    save_config_entry("translation_enabled", "false")
    all_overrides = get_all_config_entries()
    reload_settings(all_overrides)
    invalidate_response_cache()

    cancelled = cancel_queued_jobs()
    return jsonify({"status": "disabled", "cancelled_jobs": cancelled})
