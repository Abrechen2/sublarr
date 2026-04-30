"""Re-translation endpoints — /retranslate/status, /retranslate/<id>, /retranslate/batch."""

import logging
import os
import threading

from flask import current_app, jsonify

from events import emit_event
from extensions import socketio
from routes.translate import bp
from routes.translate._helpers import _is_translation_enabled, _run_job
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


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

    return jsonify(
        {
            "current_hash": current_hash,
            "outdated_count": outdated,
            "ollama_model": s.ollama_model,
            "target_language": s.target_language,
        }
    )


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
    if not is_safe_path(file_path, get_settings().media_path):
        return jsonify({"error": "file_path must be under the configured media_path"}), 403

    if not _is_translation_enabled():
        return jsonify({"error": "Translation is disabled in configuration"}), 503

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
            emit_event(
                "translation_complete",
                {
                    "file_path": file_path,
                    "job_id": new_job["id"],
                },
            )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify(
        {
            "status": "started",
            "job_id": new_job["id"],
            "file_path": file_path,
        }
    ), 202


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

    if not _is_translation_enabled():
        return jsonify({"error": "Translation is disabled in configuration"}), 503

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

                socketio.emit(
                    "retranslation_progress",
                    {
                        "processed": processed,
                        "total": total,
                        "succeeded": succeeded,
                        "failed": failed,
                        "current_file": file_path,
                    },
                )

            emit_event(
                "translation_complete",
                {
                    "count": processed,
                    "succeeded": succeeded,
                    "failed": failed,
                },
            )

    thread = threading.Thread(target=_run_retranslate, daemon=True)
    thread.start()

    return jsonify(
        {
            "status": "started",
            "total": total,
        }
    ), 202
