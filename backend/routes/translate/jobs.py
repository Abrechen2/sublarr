"""Job management endpoints — /status/<id>, /jobs, /jobs/<id>/retry."""

import logging
import os
import threading

from flask import current_app, jsonify, request

from routes.translate import bp
from routes.translate._helpers import _is_translation_enabled, _run_job
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


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
    if not is_safe_path(file_path, get_settings().media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    if not _is_translation_enabled():
        return jsonify({"error": "Translation is disabled in configuration"}), 503

    new_job = create_job(file_path, force=True, arr_context=job.get("arr_context"))
    _app = current_app._get_current_object()

    def _run_with_ctx():
        with _app.app_context():
            _run_job(new_job)

    thread = threading.Thread(target=_run_with_ctx, daemon=True)
    thread.start()

    return jsonify(
        {
            "status": "queued",
            "job_id": new_job["id"],
            "original_job_id": job_id,
            "file_path": file_path,
        }
    ), 202
