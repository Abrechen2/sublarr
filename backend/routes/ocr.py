"""OCR routes — /ocr/extract, /ocr/preview, /ocr/batch-extract."""

import logging
import os
import re
import threading
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request, send_file

from config import get_settings, map_path
from extensions import limiter
from security_utils import is_safe_path
from services.ocr_extractor import (
    TESSERACT_AVAILABLE,
    batch_ocr_track,
    ocr_subtitle_stream,
    preview_frame,
)

bp = Blueprint("ocr", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Tesseract language codes are 3-letter ISO 639-2 alpha-3, optionally chained
# with "+" (e.g. "eng+deu"). Reject anything else — the value is passed to a
# subprocess via tesseract --lang and although shell=False blocks injection,
# a stray "../" could still break out of the tessdata search path.
_TESS_LANG_RE = re.compile(r"^[a-z]{3}(\+[a-z]{3})*$")
_TESS_LANG_DEFAULT = "eng"


def _safe_tess_lang(raw: object) -> str:
    if not raw or not isinstance(raw, str):
        return _TESS_LANG_DEFAULT
    raw = raw.strip().lower()
    return raw if _TESS_LANG_RE.match(raw) else _TESS_LANG_DEFAULT


_ocr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="batch-ocr")
# Bounded LRU so a long-running deployment doesn't grow _ocr_jobs without
# bound — every batch job adds an entry and nothing ever evicts.
_OCR_JOB_CAP = 256
_ocr_jobs: OrderedDict[str, dict] = OrderedDict()
_ocr_lock = threading.Lock()


def _record_job(jid: str, payload: dict) -> None:
    with _ocr_lock:
        _ocr_jobs[jid] = payload
        _ocr_jobs.move_to_end(jid)
        while len(_ocr_jobs) > _OCR_JOB_CAP:
            _ocr_jobs.popitem(last=False)


@bp.route("/ocr/extract", methods=["POST"])
@limiter.limit("3 per minute")
def extract_ocr():
    """Extract text from embedded image subtitle stream using OCR.
    ---
    post:
      tags:
        - OCR
      summary: Extract OCR text
      description: Extracts text from embedded image subtitle stream using Tesseract OCR.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                file_path:
                  type: string
                stream_index:
                  type: integer
                language:
                  type: string
                  default: eng
                start_time:
                  type: number
                end_time:
                  type: number
                interval:
                  type: number
                  default: 1.0
      responses:
        200:
          description: OCR extraction results
          content:
            application/json:
              schema:
                type: object
                properties:
                  text:
                    type: string
                  frames:
                    type: integer
                  successful_frames:
                    type: integer
                  quality:
                    type: integer
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Processing error
    """
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    stream_index = data.get("stream_index", 0)
    language = _safe_tess_lang(data.get("language", "eng"))
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    interval = data.get("interval", 1.0)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    # Path mapping via settings.path_mapping (the actual Pydantic field).
    # Earlier this read `settings.media_path_mapping`, which doesn't exist —
    # the mapping never applied and remote-mapped paths returned 403.
    settings = get_settings()
    mapped_path = map_path(file_path)
    if not is_safe_path(mapped_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    if not TESSERACT_AVAILABLE:
        return jsonify(
            {
                "error": "OCR not available (pytesseract not installed)",
                "text": "",
                "frames": 0,
                "successful_frames": 0,
                "quality": 0,
            }
        ), 500

    try:
        result = ocr_subtitle_stream(
            mapped_path,
            stream_index,
            language=language,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
        )

        return jsonify(result), 200
    except RuntimeError as e:
        logger.error("OCR extraction failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error during OCR extraction")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/ocr/preview", methods=["GET"])
@limiter.limit("10 per minute")
def preview_ocr():
    """Preview a frame for OCR extraction.
    ---
    get:
      tags:
        - OCR
      summary: Preview OCR frame
      description: Extracts and previews a single frame from video for OCR testing.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
        - in: query
          name: timestamp
          required: true
          schema:
            type: number
        - in: query
          name: stream_index
          schema:
            type: integer
      responses:
        200:
          description: Frame preview
          content:
            application/json:
              schema:
                type: object
                properties:
                  frame_path:
                    type: string
                  preview_text:
                    type: string
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Processing error
    """
    file_path = request.args.get("file_path")
    timestamp = request.args.get("timestamp", type=float)
    stream_index = request.args.get("stream_index", type=int)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    if timestamp is None:
        return jsonify({"error": "timestamp is required"}), 400

    # Path mapping via settings.path_mapping (the actual Pydantic field).
    # Earlier this read `settings.media_path_mapping`, which doesn't exist —
    # the mapping never applied and remote-mapped paths returned 403.
    settings = get_settings()
    mapped_path = map_path(file_path)
    if not is_safe_path(mapped_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    if not TESSERACT_AVAILABLE:
        return jsonify(
            {
                "error": "OCR not available (pytesseract not installed)",
                "frame_path": "",
                "preview_text": "",
            }
        ), 500

    try:
        result = preview_frame(mapped_path, timestamp, stream_index)

        # Return frame as image if requested
        if request.args.get("download") == "true" and os.path.exists(result["frame_path"]):
            return send_file(
                result["frame_path"],
                mimetype="image/png",
                as_attachment=True,
                download_name="ocr_preview.png",
            )

        return jsonify(result), 200
    except RuntimeError as e:
        logger.error("OCR preview failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error during OCR preview")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/ocr/batch-extract", methods=["POST"])
@limiter.limit("3 per minute")
def batch_extract():
    """Start an async batch OCR job for an entire PGS/VobSub subtitle track.
    ---
    post:
      security:
        - apiKeyAuth: []
      summary: Batch OCR subtitle track
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [video_path, stream_index]
              properties:
                video_path:
                  type: string
                stream_index:
                  type: integer
                language:
                  type: string
                  default: eng
      responses:
        202:
          description: Job accepted
          content:
            application/json:
              schema:
                type: object
                properties:
                  job_id:
                    type: string
        400:
          description: Missing parameters
        404:
          description: Video not found
    """
    data = request.get_json(force=True, silent=True) or {}
    video_path = data.get("video_path", "")
    stream_index = data.get("stream_index")
    language = _safe_tess_lang(data.get("language", "eng"))

    if not video_path or stream_index is None:
        return jsonify({"error": "video_path and stream_index are required"}), 400
    try:
        stream_index = int(stream_index)
    except (TypeError, ValueError):
        return jsonify({"error": "stream_index must be an integer"}), 400
    if stream_index < 0:
        return jsonify({"error": "stream_index must be non-negative"}), 400

    settings = get_settings()
    video_path = map_path(video_path)
    if not is_safe_path(video_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(video_path):
        return jsonify({"error": f"Video not found: {video_path}"}), 404

    if not TESSERACT_AVAILABLE:
        return jsonify({"error": "OCR not available (pytesseract not installed)"}), 500

    job_id = str(uuid.uuid4())
    _record_job(job_id, {"status": "queued"})

    def _run(jid: str, vp: str, si: int, lang: str) -> None:
        _record_job(jid, {"status": "running"})
        try:
            cues = batch_ocr_track(vp, si, lang)
            _record_job(jid, {"status": "completed", "cues": cues})
        except Exception as e:
            logger.error("Batch OCR job %s failed: %s", jid, e)
            _record_job(jid, {"status": "failed", "error": str(e)})

    _ocr_executor.submit(_run, job_id, video_path, stream_index, language)
    return jsonify({"job_id": job_id}), 202


@bp.route("/ocr/batch-extract/<job_id>", methods=["GET"])
def batch_extract_status(job_id: str):
    """Get status of a batch OCR job.
    ---
    get:
      security:
        - apiKeyAuth: []
      summary: Batch OCR job status
      parameters:
        - in: path
          name: job_id
          required: true
          schema:
            type: string
      responses:
        200:
          description: Job status
        404:
          description: Job not found
    """
    with _ocr_lock:
        job = _ocr_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"job_id": job_id, **job})
