"""Video player routes — HLS streaming, screenshots, subtitle conversion."""

import logging
import os

from flask import Blueprint, jsonify, request, send_file

from config import get_settings
from extensions import limiter
from security_utils import is_safe_path
from services.video_player import (
    convert_subtitle_to_webvtt,
    generate_hls_playlist,
    generate_screenshot,
)

bp = Blueprint("video", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Screenshot generator allocates a frame buffer proportional to width;
# unbounded values can drive multi-GB ffmpeg allocations.
_SCREENSHOT_WIDTH_MAX = 3840


@bp.route("/video/stream", methods=["GET"])
@limiter.limit("10 per minute")
def get_video_stream():
    """Generate HLS playlist for video streaming.
    ---
    get:
      tags:
        - Video
      summary: Get HLS stream
      description: Generates HLS playlist and segments for browser-based video playback.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
        - in: query
          name: format
          schema:
            type: string
            default: hls
        - in: query
          name: quality
          schema:
            type: string
            default: medium
      responses:
        200:
          description: HLS playlist
          content:
            application/vnd.apple.mpegurl:
              schema:
                type: string
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
        quality = request.args.get("quality", "medium")
        cache_dir = os.path.join(getattr(settings, "config_dir", "/config"), "cache", "video")
        os.makedirs(cache_dir, exist_ok=True)

        # Generate HLS playlist
        result = generate_hls_playlist(mapped_path, cache_dir, quality=quality)

        # Return playlist file
        if os.path.exists(result["playlist_path"]):
            return send_file(
                result["playlist_path"],
                mimetype="application/vnd.apple.mpegurl",
            )

        return jsonify({"error": "Playlist generation failed"}), 500
    except RuntimeError as e:
        logger.exception("HLS generation failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    except Exception:
        logger.exception("Unexpected error generating HLS stream")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/video/segment", methods=["GET"])
@limiter.exempt
def get_video_segment():
    """Get HLS segment file.
    ---
    get:
      tags:
        - Video
      summary: Get HLS segment
      description: Returns a specific HLS segment file.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
        - in: query
          name: segment
          required: true
          schema:
            type: string
      responses:
        200:
          description: Segment file
          content:
            video/mp2t:
              schema:
                type: string
        400:
          description: Invalid request
        404:
          description: Segment not found
    """
    file_path = request.args.get("file_path")
    segment = request.args.get("segment")

    if not file_path or not segment:
        return jsonify({"error": "file_path and segment are required"}), 400

    # Defence-in-depth: even though is_safe_path catches a realpath escape,
    # reject path separators in the bare segment name so we never have to
    # reason about edge cases (e.g. NTFS reparse points, alternate streams).
    if "/" in segment or "\\" in segment or segment.startswith("."):
        return jsonify({"error": "Invalid segment name"}), 400

    try:
        settings = get_settings()
        cache_dir = os.path.join(getattr(settings, "config_dir", "/config"), "cache", "video")
        segment_path = os.path.join(cache_dir, segment)

        if not is_safe_path(segment_path, cache_dir):
            return jsonify({"error": "Invalid segment path"}), 400

        if os.path.exists(segment_path):
            return send_file(segment_path, mimetype="video/mp2t")
        return jsonify({"error": "Segment not found"}), 404
    except Exception:
        logger.exception("Error serving segment")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/video/screenshot", methods=["POST"])
@limiter.limit("10 per minute")
def create_screenshot():
    """Generate screenshot from video.
    ---
    post:
      tags:
        - Video
      summary: Generate screenshot
      description: Generates a screenshot from video at specified timestamp.
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
                timestamp:
                  type: number
                width:
                  type: integer
      responses:
        200:
          description: Screenshot image
          content:
            image/jpeg:
              schema:
                type: string
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Processing error
    """
    data = request.get_json(silent=True) or {}
    file_path = data.get("file_path")
    timestamp = data.get("timestamp", 0)
    raw_width = data.get("width", 1920)

    if not file_path:
        return jsonify({"error": "file_path is required"}), 400

    try:
        width = max(160, min(int(raw_width), _SCREENSHOT_WIDTH_MAX))
    except (TypeError, ValueError):
        return jsonify({"error": "width must be an integer"}), 400
    try:
        timestamp = max(0.0, float(timestamp))
    except (TypeError, ValueError):
        return jsonify({"error": "timestamp must be a number"}), 400

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
        screenshot_path = generate_screenshot(mapped_path, timestamp, width=width)

        if os.path.exists(screenshot_path):
            return send_file(
                screenshot_path,
                mimetype="image/jpeg",
                as_attachment=False,
            )

        return jsonify({"error": "Screenshot generation failed"}), 500
    except RuntimeError as e:
        logger.exception("Screenshot generation failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    except Exception:
        logger.exception("Unexpected error generating screenshot")
        return jsonify({"error": "Internal server error"}), 500


@bp.route("/video/subtitles", methods=["GET"])
@limiter.limit("60 per minute")
def get_subtitle_webvtt():
    """Convert subtitle to WebVTT format.
    ---
    get:
      tags:
        - Video
      summary: Get WebVTT subtitle
      description: Converts subtitle file to WebVTT format for browser playback.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
        - in: query
          name: format
          schema:
            type: string
            default: vtt
      responses:
        200:
          description: WebVTT subtitle file
          content:
            text/vtt:
              schema:
                type: string
        400:
          description: Invalid request
        404:
          description: File not found
        500:
          description: Conversion error
    """
    file_path = request.args.get("file_path")
    if not file_path:
        return jsonify({"error": "file_path parameter is required"}), 400

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

    # A directory passes both checks above and then reaches ffmpeg, which
    # fails with "Is a directory" and surfaced as HTTP 500 (found 2026-09-03
    # on the deployed rc.5, file_path=/media). Not a way in — the caller has
    # to be inside the library to get here — but a 500 where a 400 belongs.
    if not os.path.isfile(mapped_path):
        return jsonify({"error": "Not a file"}), 400

    try:
        vtt_path = convert_subtitle_to_webvtt(mapped_path)

        if os.path.exists(vtt_path):
            return send_file(
                vtt_path,
                mimetype="text/vtt",
                as_attachment=False,
            )

        return jsonify({"error": "Subtitle conversion failed"}), 500
    except RuntimeError as e:
        logger.exception("Subtitle conversion failed: %s", e)
        return jsonify({"error": "Internal server error"}), 500
    except Exception:
        logger.exception("Unexpected error converting subtitle")
        return jsonify({"error": "Internal server error"}), 500
