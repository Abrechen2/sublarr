"""Audio routes — waveform visualization endpoints."""

import logging
import os

from flask import Blueprint, jsonify, request

from config import get_settings
from extensions import limiter
from security_utils import is_safe_path
from services.audio_visualizer import (
    extract_audio_track,
    generate_waveform_json,
    get_audio_duration,
    list_audio_tracks,
    list_keyframes,
)
from services.scene_detector import detect_scenes

bp = Blueprint("audio", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Caps for waveform generation parameters. Width drives the per-pixel sample
# count and sample_rate the per-second granularity — both are passed straight
# into ffmpeg/numpy buffers, so an unbounded value can drive a multi-GB
# allocation.
_WAVEFORM_WIDTH_MAX = 8000
_WAVEFORM_SAMPLE_RATE_MAX = 1000


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def _coerce_track_index(raw: object) -> int | None:
    """Reject bool (Python's ``True is 1`` gotcha) and negative values.

    Returns the validated index, or None if the input is missing/invalid
    (callers fall back to "auto-pick").
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if not isinstance(raw, int):
        try:
            raw = int(raw)
        except (TypeError, ValueError):
            return None
    return raw if raw >= 0 else None


@bp.route("/audio/waveform", methods=["GET"])
@limiter.limit("10 per minute")
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
        width = _clamp(request.args.get("width", 2000, type=int) or 2000, 100, _WAVEFORM_WIDTH_MAX)
        sample_rate = _clamp(
            request.args.get("sample_rate", 100, type=int) or 100,
            10,
            _WAVEFORM_SAMPLE_RATE_MAX,
        )

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
@limiter.limit("5 per minute")
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
        audio_track_index = _coerce_track_index(data.get("audio_track_index"))
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


@bp.route("/audio/tracks", methods=["GET"])
@limiter.limit("30 per minute")
def get_audio_tracks():
    """List the audio streams of a video file (WaveformEditor track picker).
    ---
    get:
      tags:
        - Audio
      summary: List audio tracks
      description: Returns the audio streams embedded in a video file with
        their language/title/channel layout, used by the WaveformEditor's
        audio-track picker.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to video file (must be inside media_path)
      responses:
        200:
          description: Audio track list
          content:
            application/json:
              schema:
                type: object
                properties:
                  tracks:
                    type: array
                    items:
                      type: object
                  video_path:
                    type: string
        400:
          description: Missing file_path
        403:
          description: Path outside media root
        404:
          description: File not found
        500:
          description: Probe error
    """
    file_path = request.args.get("file_path")
    if not file_path:
        return jsonify({"error": "file_path parameter is required"}), 400

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
        tracks = list_audio_tracks(mapped_path)
        return jsonify({"tracks": tracks, "video_path": mapped_path}), 200
    except RuntimeError as e:
        logger.error("Audio-track probe failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error probing audio tracks")
        return jsonify({"error": "Internal server error"}), 500


def _resolve_media_path(file_path: str | None):
    """Common media-path-mapping + safety check for B8 audio sub-routes.

    Returns ``(mapped_path, response, status)``. On failure, ``mapped_path``
    is None and ``(response, status)`` is the error to return immediately.
    """
    if not file_path:
        return None, jsonify({"error": "file_path parameter is required"}), 400
    settings = get_settings()
    mapped_path = file_path
    if hasattr(settings, "media_path_mapping") and settings.media_path_mapping:
        for mapping in settings.media_path_mapping:
            if file_path.startswith(mapping.get("from", "")):
                mapped_path = file_path.replace(mapping["from"], mapping.get("to", file_path), 1)
                break
    if not is_safe_path(mapped_path, settings.media_path):
        return None, jsonify({"error": "Access denied"}), 403
    if not os.path.exists(mapped_path):
        return None, jsonify({"error": "File not found"}), 404
    return mapped_path, None, 200


@bp.route("/audio/keyframes", methods=["GET"])
@limiter.limit("10 per minute")
def get_audio_keyframes():
    """Return keyframe timestamps of the first video stream (snap targets).
    ---
    get:
      tags:
        - Audio
      summary: List video keyframes
      description: Returns the keyframe timestamps (seconds) of the first
        video stream — used by the WaveformEditor's snap-to-keyframe
        feature so cue boundaries can land on shot cuts.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
      responses:
        200:
          description: Keyframe list
        400:
          description: Missing file_path
        403:
          description: Path outside media root
        404:
          description: File not found
        500:
          description: ffprobe error
    """
    mapped_path, err, status = _resolve_media_path(request.args.get("file_path"))
    if mapped_path is None:
        return err, status
    try:
        keyframes = list_keyframes(mapped_path)
        return jsonify({"keyframes": keyframes, "video_path": mapped_path}), 200
    except RuntimeError as e:
        logger.error("Keyframe scan failed: %s", e)
        return jsonify({"error": str(e)}), 500
    except Exception:
        logger.exception("Unexpected error scanning keyframes")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/audio/scenes", methods=["GET"])
@limiter.limit("5 per minute")
def get_audio_scenes():
    """Return scene-cut timestamps via PySceneDetect (optional dep).
    ---
    get:
      tags:
        - Audio
      summary: List scene-cut boundaries
      description: PySceneDetect is an optional dependency. When the lib is
        absent the response is ``{"scenes": [], "available": false}`` so
        the WaveformEditor gracefully omits scene markers.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
      responses:
        200:
          description: Scene-boundary list (possibly empty)
        400:
          description: Missing file_path
        403:
          description: Path outside media root
        404:
          description: File not found
    """
    mapped_path, err, status = _resolve_media_path(request.args.get("file_path"))
    if mapped_path is None:
        return err, status
    try:
        scenes = detect_scenes(mapped_path)
    except Exception:
        logger.exception("Unexpected error detecting scenes")
        return jsonify({"error": "Internal server error"}), 500
    available = True
    try:
        from services.scene_detector import _import_scenedetect

        _import_scenedetect()
    except ImportError:
        available = False
    return jsonify({"scenes": scenes, "available": available}), 200
