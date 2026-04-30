"""POST /api/v1/whisper/transcribe — submit a transcription job."""

import logging
import os
import uuid

from flask import jsonify, request

from extensions import socketio
from routes.whisper import bp
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


@bp.route("/transcribe", methods=["POST"])
def transcribe():
    """Submit a transcription job.

    Accepts JSON: {"file_path": str, "language": str (optional)}
    Returns 202 with job_id and status.
    ---
    post:
      security:
        - apiKeyAuth: []
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
    # Function-local import: tests monkey-patch routes.whisper._get_queue, so look
    # it up on the package namespace at call time rather than binding at import.
    from config import get_settings, map_path
    from routes.whisper import _get_queue
    from translator._helpers import _is_whisper_enabled
    from whisper import get_whisper_manager

    data = request.get_json() or {}
    file_path = data.get("file_path")

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    file_path = map_path(file_path)
    settings = get_settings()

    if not is_safe_path(file_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(file_path):
        return jsonify({"error": f"File not found: {file_path}"}), 404
    language = data.get("language", settings.source_language or "ja")

    audio_track_index = data.get("audio_track_index")
    if audio_track_index is not None:
        if not isinstance(audio_track_index, int) or audio_track_index < 0:
            return jsonify(
                {"error": "audio_track_index must be a non-negative integer or null"}
            ), 400

    # Gate after input validation so a bad request gets the most useful 4xx
    # rather than a generic 503. The translator pipeline's Whisper-as-fallback
    # path already honours this flag — without the gate here, the manual UI
    # transcribe button bypassed the user-facing toggle.
    if not _is_whisper_enabled():
        return jsonify({"error": "Whisper is disabled in configuration"}), 503

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
        audio_track_index=audio_track_index,
    )

    return jsonify(
        {
            "job_id": job_id,
            "status": "queued",
        }
    ), 202
