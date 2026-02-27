"""Whisper routes -- /whisper/transcribe, /whisper/queue, /whisper/backends, /whisper/config, /whisper/stats."""

import logging
import uuid

from flask import Blueprint, jsonify, request

from extensions import socketio

bp = Blueprint("whisper", __name__, url_prefix="/api/v1/whisper")
logger = logging.getLogger(__name__)


# --- WhisperQueue singleton ---

_queue = None


def _get_queue():
    """Get or create the WhisperQueue singleton."""
    global _queue
    if _queue is None:
        from whisper.queue import WhisperQueue

        max_concurrent = int(_get_config("max_concurrent_whisper", "1"))
        _queue = WhisperQueue(max_concurrent=max_concurrent)
    return _queue


def _get_config(key, default=""):
    """Read a config entry with fallback."""
    try:
        from db.config import get_config_entry

        value = get_config_entry(key)
        return value if value is not None else default
    except Exception:
        return default


# --- Transcription Job Endpoints ---


@bp.route("/transcribe", methods=["POST"])
def transcribe():
    """Submit a transcription job.

    Accepts JSON: {"file_path": str, "language": str (optional)}
    Returns 202 with job_id and status.
    ---
    post:
      tags:
        - Whisper
      summary: Submit transcription job
      description: Submits an audio/video file for speech-to-text transcription using the configured Whisper backend. Returns immediately with a job ID.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
              properties:
                file_path:
                  type: string
                  description: Path to audio or video file
                language:
                  type: string
                  description: Source language code (defaults to config source_language)
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
                    enum: [queued]
        400:
          description: Missing file_path
        404:
          description: File not found
    """
    import os

    from whisper import get_whisper_manager

    data = request.get_json() or {}
    file_path = data.get("file_path")

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404

    # Determine language
    from config import get_settings

    settings = get_settings()
    language = data.get("language", settings.source_language or "ja")

    job_id = uuid.uuid4().hex
    manager = get_whisper_manager()
    queue = _get_queue()

    queue.submit(
        job_id=job_id,
        file_path=file_path,
        language=language,
        source_language=language,
        whisper_manager=manager,
        socketio=socketio,
    )

    return jsonify(
        {
            "job_id": job_id,
            "status": "queued",
        }
    ), 202


@bp.route("/queue", methods=["GET"])
def list_queue():
    """List all Whisper jobs with progress.

    Optional query params: status (filter), limit (default 50).
    ---
    get:
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
    from db.whisper import delete_whisper_job, get_whisper_job

    job = get_whisper_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    status = job.get("status", "")

    # If queued, try to cancel via queue
    if status == "queued":
        queue = _get_queue()
        queue.cancel_job(job_id)
        return jsonify({"success": True, "action": "cancelled"})

    # If terminal state, delete from DB
    if status in ("completed", "failed", "cancelled"):
        delete_whisper_job(job_id)
        return jsonify({"success": True, "action": "deleted"})

    # In progress -- cannot cancel active transcription
    return jsonify({"error": "Cannot delete job in progress. Wait for completion or failure."}), 409


# --- Backend Management Endpoints ---


@bp.route("/backends", methods=["GET"])
def list_backends():
    """List available Whisper backends with config.
    ---
    get:
      tags:
        - Whisper
      summary: List Whisper backends
      description: Returns all available Whisper backends with their configuration fields and status.
      responses:
        200:
          description: List of Whisper backends
          content:
            application/json:
              schema:
                type: object
                properties:
                  backends:
                    type: array
                    items:
                      type: object
    """
    from whisper import get_whisper_manager

    manager = get_whisper_manager()
    backends = manager.get_all_backends()
    return jsonify({"backends": backends})


@bp.route("/backends/test/<name>", methods=["POST"])
def test_backend(name):
    """Test a specific Whisper backend.
    ---
    post:
      tags:
        - Whisper
      summary: Test Whisper backend
      description: Tests connectivity and availability of a specific Whisper backend.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        404:
          description: Backend not found
    """
    from whisper import get_whisper_manager

    manager = get_whisper_manager()
    backend = manager.get_backend(name)

    if not backend:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    healthy, message = backend.health_check()
    return jsonify({"healthy": healthy, "message": message})


@bp.route("/backends/config/<name>", methods=["GET"])
def get_backend_config(name):
    """Get backend config.

    Reads from config_entries with whisper.<name>.<key> namespacing.
    Masks password fields.
    ---
    get:
      tags:
        - Whisper
      summary: Get Whisper backend config
      description: Returns the configuration for a specific Whisper backend with password fields masked.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      responses:
        200:
          description: Backend config
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
    from whisper import get_whisper_manager

    # Validate backend exists
    manager = get_whisper_manager()
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
    prefix = f"whisper.{name}."
    config = {}
    for key, value in all_entries.items():
        if key.startswith(prefix):
            short_key = key[len(prefix) :]
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


@bp.route("/backends/config/<name>", methods=["PUT"])
def save_backend_config(name):
    """Save backend config.

    Accepts JSON config dict. Saves to config_entries with whisper.<name>.<key> namespacing.
    Invalidates cached backend instance.
    ---
    put:
      tags:
        - Whisper
      summary: Save Whisper backend config
      description: Saves configuration for a specific Whisper backend and invalidates the cached instance.
      parameters:
        - in: path
          name: name
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              additionalProperties:
                type: string
      responses:
        200:
          description: Config saved
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        400:
          description: No config data provided
        404:
          description: Backend not found
    """
    from db.config import save_config_entry
    from whisper import get_whisper_manager

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    # Validate backend exists
    manager = get_whisper_manager()
    all_backends = manager.get_all_backends()
    known_names = {b["name"] for b in all_backends}
    if name not in known_names:
        return jsonify({"error": f"Backend '{name}' not found"}), 404

    # Store each config entry with namespace prefix
    for key, value in data.items():
        config_key = f"whisper.{name}.{key}"
        save_config_entry(config_key, str(value))

    # Invalidate cached instance so next use picks up new config
    manager.invalidate_backend()

    return jsonify({"success": True})


# --- Global Whisper Config Endpoints ---


@bp.route("/config", methods=["GET"])
def get_whisper_config():
    """Get global Whisper config.
    ---
    get:
      tags:
        - Whisper
      summary: Get global Whisper config
      description: Returns global Whisper configuration including enabled state, active backend, and concurrency limit.
      responses:
        200:
          description: Whisper config
          content:
            application/json:
              schema:
                type: object
                properties:
                  whisper_backend:
                    type: string
                  max_concurrent_whisper:
                    type: integer
                  whisper_enabled:
                    type: boolean
    """
    config = {
        "whisper_backend": _get_config("whisper_backend", "subgen"),
        "max_concurrent_whisper": int(_get_config("max_concurrent_whisper", "1")),
        "whisper_enabled": _get_config("whisper_enabled", "false").lower() in ("true", "1", "yes"),
    }
    return jsonify(config)


@bp.route("/config", methods=["PUT"])
def save_whisper_config():
    """Save global Whisper config.

    Accepts JSON: {"whisper_backend": str, "max_concurrent_whisper": int, "whisper_enabled": bool}
    ---
    put:
      tags:
        - Whisper
      summary: Save global Whisper config
      description: Updates global Whisper configuration. Resets the queue singleton if max_concurrent changes.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                whisper_backend:
                  type: string
                max_concurrent_whisper:
                  type: integer
                whisper_enabled:
                  type: boolean
      responses:
        200:
          description: Config saved
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
        400:
          description: No config data provided
    """
    from db.config import save_config_entry

    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No configuration data provided"}), 400

    allowed_keys = {
        "whisper_backend",
        "max_concurrent_whisper",
        "whisper_enabled",
        "whisper_fallback_min_score",
    }
    for key, value in data.items():
        if key not in allowed_keys:
            continue
        # Convert booleans to string
        if isinstance(value, bool):
            value = "true" if value else "false"
        save_config_entry(key, str(value))

    # Reset queue singleton if max_concurrent changed
    if "max_concurrent_whisper" in data:
        global _queue
        _queue = None

    return jsonify({"success": True})


# --- Stats Endpoint ---


@bp.route("/stats", methods=["GET"])
def whisper_stats():
    """Get Whisper statistics.
    ---
    get:
      tags:
        - Whisper
      summary: Get Whisper statistics
      description: Returns aggregated Whisper transcription statistics including total jobs, status breakdown, and average processing time.
      responses:
        200:
          description: Whisper stats
          content:
            application/json:
              schema:
                type: object
                properties:
                  total:
                    type: integer
                  by_status:
                    type: object
                    additionalProperties:
                      type: integer
                  avg_processing_time:
                    type: number
    """
    from db.whisper import get_whisper_stats

    stats = get_whisper_stats()
    return jsonify(stats)
