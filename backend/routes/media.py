"""
Media streaming endpoint.
GET /api/v1/media/stream?path=<abs_path>
Serves video files with HTTP 206 range support.
"""

import os

from flask import Blueprint, Response, jsonify, request, send_file

from auth import require_api_key
from config import get_settings
from extensions import limiter
from security_utils import is_safe_path

bp = Blueprint("media", __name__, url_prefix="/api/v1")

_CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".m4v": "video/x-m4v",
}


def _get_content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


def _stream_range(
    path: str, start: int, end: int, file_size: int, chunk: int = 1 << 20
) -> Response:
    """Stream file bytes [start, end] inclusive as 206 Partial Content."""
    length = end - start + 1
    content_type = _get_content_type(path)

    def generate():
        remaining = length
        with open(path, "rb") as f:
            f.seek(start)
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    resp = Response(
        generate(),
        status=206,
        mimetype=content_type,
        direct_passthrough=True,
    )
    resp.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    resp.headers["Content-Length"] = str(length)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


@bp.route("/media/stream-token", methods=["POST"])
@require_api_key
def stream_token():
    """Mint a short-lived, path-scoped token for browser-native streaming.
    ---
    post:
      tags:
        - Media
      summary: Create a stream token
      description: >
        Returns an HMAC token bound to a specific media file path, valid for a
        few hours. The browser passes this token (not the API key) in the
        /media/stream URL so the raw API key never appears in access logs.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Token issued
        400:
          description: Missing path parameter
        403:
          description: Path outside media_path
        404:
          description: File not found
        503:
          description: Streaming is disabled in settings
    """
    settings = get_settings()
    if not settings.streaming_enabled:
        return jsonify({"error": "Streaming is disabled"}), 503

    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path:
        return jsonify({"error": "path parameter required"}), 400
    if not is_safe_path(path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    from media_token import generate_stream_token

    token, expires_at = generate_stream_token(path)
    return jsonify({"token": token, "expires_at": expires_at})


@bp.route("/media/stream")
@limiter.limit("600/minute")
def stream_media():
    """Stream a video file with HTTP 206 Range support.
    ---
    get:
      tags:
        - Media
      summary: Stream video file
      description: >
        Serves a local video file with RFC 7233 Range request support (HTTP 206).
        Requires the streaming_enabled setting to be active.
        Path must be within the configured media_path (path traversal protection).
      security:
        - apiKeyAuth: []
      parameters:
        - name: path
          in: query
          required: true
          schema:
            type: string
          description: Absolute path to the video file
      responses:
        200:
          description: Full file content (no Range header supplied)
        206:
          description: Partial content (Range header present)
          headers:
            Content-Range:
              schema:
                type: string
              example: "bytes 0-1048575/52428800"
            Accept-Ranges:
              schema:
                type: string
              example: "bytes"
        400:
          description: Missing path parameter
        403:
          description: Path outside media_path (access denied)
        404:
          description: File not found
        416:
          description: Invalid Range header
        503:
          description: Streaming is disabled in settings
    """
    # Auth is enforced by the global before_request hooks: a normal API
    # key / UI session, OR a valid path-scoped stream token (see media_token).
    # No @require_api_key decorator here — the <video> element can't send the
    # X-Api-Key header, so token-authenticated requests must be able to reach
    # this handler without the decorator rejecting them.
    settings = get_settings()

    if not settings.streaming_enabled:
        return jsonify({"error": "Streaming is disabled"}), 503

    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path parameter required"}), 400

    if not is_safe_path(path, settings.media_path):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.isfile(path):
        return jsonify({"error": "File not found"}), 404

    file_size = os.path.getsize(path)
    range_header = request.headers.get("Range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            byte_range = range_header.strip().replace("bytes=", "")
            parts = byte_range.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
        except (ValueError, IndexError):
            return jsonify({"error": "Invalid Range header"}), 416

        # RFC 7233 compliance: reject invalid ranges
        if start < 0 or start > end:
            return jsonify({"error": "Invalid Range header"}), 416

        end = min(end, file_size - 1)
        return _stream_range(path, start, end, file_size)

    # No Range header — serve full file as 200
    return send_file(path, mimetype=_get_content_type(path), conditional=True)
