"""Audio routes — waveform visualization endpoints."""

import logging
import os

from flask import Blueprint, jsonify, request

from config import get_settings
from security_utils import is_safe_path
from services.audio_visualizer import (
    extract_audio_track,
    generate_waveform_json,
    get_audio_duration,
)

bp = Blueprint("audio", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/audio/waveform", methods=["GET"])
def get_waveform():
    """Generate waveform data for a video file.
    ---
    get:
      tags:
        - Audio
      summary: Get waveform data
      description: Generates waveform visualization data from video file audio track.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to video file
        - in: query
          name: audio_track_index
          schema:
            type: integer
            default: 0
          description: Audio track index (0-based)
        - in: query
          name: width
          schema:
            type: integer
            default: 2000
          description: Waveform width in pixels (affects resolution)
        - in: query
          name: sample_rate
          schema:
            type: integer
            default: 100
          description: Samples per second
      responses:
        200:
          description: Waveform data
          content:
            application/json:
              schema:
                type: object
                properties:
                  duration:
                    type: number
                  sample_rate:
                    type: integer
                  samples:
                    type: integer
                  data:
                    type: array
                    items:
                      type: object
                      properties:
                        time:
                          type: number
                        amplitude:
                          type: number
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Processing error
    """
    file_path = request.args.get("file_path")
    if not file_path:
        return jsonify({"error": "file_path parameter is required"}), 400

    # Path mapping (if media path mapping is configured)
    settings = get_settings()
    mapped_path = file_path
    if hasattr(settings, "media_path_mapping") and settings.media_path_mapping:
        # Apply path mapping if configured
        for mapping in settings.media_path_mapping:
            if file_path.startswith(mapping.get("from", "")):
                mapped_path = file_path.replace(
                    mapping["from"],
                    mapping.get("to", file_path),
                    1,
                )
                break

    if not is_safe_path(mapped_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    try:
        audio_track_index = request.args.get("audio_track_index", type=int)
        width = request.args.get("width", 2000, type=int)
        sample_rate = request.args.get("sample_rate", 100, type=int)

        waveform_data = generate_waveform_json(
            mapped_path,
            audio_track_index=audio_track_index,
            width=width,
            sample_rate=sample_rate,
        )

        return jsonify(waveform_data), 200
    except RuntimeError as e:
        logger.error("Waveform generation failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error generating waveform")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/audio/extract", methods=["POST"])
def extract_audio():
    """Extract audio track from video file.
    ---
    post:
      tags:
        - Audio
      summary: Extract audio track
      description: Extracts audio track from video file and returns path to extracted file.
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
                audio_track_index:
                  type: integer
      responses:
        200:
          description: Audio extracted successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  audio_path:
                    type: string
                  duration:
                    type: number
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Extraction error
    """
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")

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

    if not is_safe_path(mapped_path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.exists(mapped_path):
        return jsonify({"error": "File not found"}), 404

    try:
        audio_track_index = data.get("audio_track_index")
        audio_path = extract_audio_track(mapped_path, audio_track_index)
        duration = get_audio_duration(audio_path)

        return jsonify(
            {
                "audio_path": audio_path,
                "duration": duration,
            }
        ), 200
    except RuntimeError as e:
        logger.error("Audio extraction failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error extracting audio")
        return jsonify({"error": "Internal server error"}), 500
