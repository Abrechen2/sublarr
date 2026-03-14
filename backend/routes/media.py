"""
Media streaming endpoint.
GET /api/v1/media/stream?path=<abs_path>
Serves video files with HTTP 206 range support.
"""

import os

from flask import Blueprint, Response, jsonify, request, send_file

from auth import require_api_key
from config import get_settings
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


@bp.route("/media/stream")
@require_api_key
def stream_media():
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
