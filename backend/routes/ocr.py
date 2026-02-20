"""OCR routes — /ocr/extract, /ocr/preview."""

import os
import logging

from flask import Blueprint, request, jsonify, send_file

from config import get_settings
from services.ocr_extractor import (
    ocr_subtitle_stream,
    preview_frame,
    extract_frame,
    TESSERACT_AVAILABLE,
)

bp = Blueprint("ocr", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/ocr/extract", methods=["POST"])
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
    language = data.get("language", "eng")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    interval = data.get("interval", 1.0)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    # Path mapping
    settings = get_settings()
    mapped_path = file_path
    if hasattr(settings, "media_path_mapping") and settings.media_path_mapping:
        for mapping in settings.media_path_mapping:
            if file_path.startswith(mapping.get("from", "")):
                mapped_path = file_path.replace(
                    mapping["from"],
                    mapping.get("to", file_path),
                    1,
                )
                break

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    if not TESSERACT_AVAILABLE:
        return jsonify({
            "error": "OCR not available (pytesseract not installed)",
            "text": "",
            "frames": 0,
            "successful_frames": 0,
            "quality": 0,
        }), 500

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
    except Exception as e:
        logger.exception("Unexpected error during OCR extraction")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/ocr/preview", methods=["GET"])
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

    # Path mapping
    settings = get_settings()
    mapped_path = file_path
    if hasattr(settings, "media_path_mapping") and settings.media_path_mapping:
        for mapping in settings.media_path_mapping:
            if file_path.startswith(mapping.get("from", "")):
                mapped_path = file_path.replace(
                    mapping["from"],
                    mapping.get("to", file_path),
                    1,
                )
                break

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    if not TESSERACT_AVAILABLE:
        return jsonify({
            "error": "OCR not available (pytesseract not installed)",
            "frame_path": "",
            "preview_text": "",
        }), 500

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
    except Exception as e:
        logger.exception("Unexpected error during OCR preview")
        return jsonify({"error": "Internal server error"}), 500
