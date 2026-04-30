"""Whisper job routes: /queue, /jobs/<id> GET+DELETE."""

import logging

from flask import jsonify, request

from routes.whisper import bp

logger = logging.getLogger(__name__)


@bp.route("/queue", methods=["GET"])
def list_queue():
    """List all Whisper jobs with progress.

    Optional query params: status (filter), limit (default 50).
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: List transcription queue
      description: Returns Whisper transcription jobs with optional status filter and limit.
      parameters:
        - in: query
          name: status
          schema:
            type: string
            enum: [queued, extracting, loading, transcribing, saving, completed, failed, cancelled]
          description: Filter by job status
        - in: query
          name: limit
          schema:
            type: integer
            default: 50
            maximum: 200
      responses:
        200:
          description: List of Whisper jobs
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
    """
    from db.whisper import get_whisper_jobs

    status_filter = request.args.get("status")
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 200)

    jobs = get_whisper_jobs(status=status_filter, limit=limit)
    return jsonify(jobs)


@bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    """Get a specific job's status and result.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Get transcription job
      description: Returns the status and result of a specific Whisper transcription job.
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
      responses:
        200:
          description: Job details
          content:
            application/json:
              schema:
                type: object
        404:
          description: Job not found
    """
    from db.whisper import get_whisper_job

    job = get_whisper_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@bp.route("/jobs/<job_id>", methods=["DELETE"])
def delete_job(job_id):
    """Cancel or delete a job.

    If job is queued: mark cancelled.
    If job is completed/failed: delete from DB.
    ---
    delete:
      security:
        - apiKeyAuth: []
      tags:
        - Whisper
      summary: Cancel or delete transcription job
      description: Cancels a queued job or deletes a completed/failed job from the database.
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
      responses:
        200:
          description: Job cancelled or deleted
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  action:
                    type: string
                    enum: [cancelled, deleted]
        404:
          description: Job not found
        409:
          description: Cannot delete job in progress
    """
    # Function-local import: tests monkey-patch routes.whisper._get_queue.
    from db.whisper import delete_whisper_job, get_whisper_job, update_whisper_job
    from routes.whisper import _get_queue

    job = get_whisper_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    status = job.get("status", "")

    # If queued, try to cancel via queue
    if status == "queued":
        queue = _get_queue()
        if queue.cancel_job(job_id):
            return jsonify({"success": True, "action": "cancelled"})
        # Job persists in the DB but the in-memory queue has dropped it
        # (typically after a service restart cleared the worker pool). Treat
        # the DB row as authoritative and mark it cancelled directly so the
        # orphan does not stay "queued" forever.
        update_whisper_job(job_id, status="cancelled")
        return jsonify({"success": True, "action": "cancelled", "orphan": True})

    # If terminal state, delete from DB
    if status in ("completed", "failed", "cancelled"):
        delete_whisper_job(job_id)
        return jsonify({"success": True, "action": "deleted"})

    # In progress -- cannot cancel active transcription
    return jsonify({"error": "Cannot delete job in progress. Wait for completion or failure."}), 409
