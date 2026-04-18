"""Subtitle analysis routes (read-only): chapters, compare, quality-trends.

Cue-modifying operations (overlap-fix, timing-normalize, merge-lines, split-lines)
live in routes/tools/line_fixes.py (B1Ta split, 2026-04-18).
"""

import logging

from flask import jsonify, request

from chapters import get_chapters
from routes.tools import bp
from routes.tools._helpers import _validate_file_path
from security_utils import is_safe_path

logger = logging.getLogger(__name__)


# -- Chapters ------------------------------------------------------------------


@bp.route("/chapters", methods=["GET"])
def get_video_chapters():
    """Return chapter list for a video file.

    Query params:
        video_path (str, required): Absolute path to the video file.
    """
    from config import get_settings

    video_path = request.args.get("video_path", "")
    if not video_path:
        return jsonify({"error": "video_path query parameter is required"}), 400

    settings = get_settings()
    if not is_safe_path(video_path, settings.media_path):
        return jsonify({"error": "video_path is outside media directory"}), 403

    chapters = get_chapters(video_path)
    return jsonify({"video_path": video_path, "chapters": chapters})


# -- Compare -------------------------------------------------------------------


@bp.route("/compare", methods=["POST"])
def compare_files():
    """Compare 2-4 subtitle files side by side.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Tools
      summary: Compare subtitle files
      description: Returns the content of 2-4 subtitle files in a single response for side-by-side comparison. Detects encoding and format for each file.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_paths
              properties:
                file_paths:
                  type: array
                  items:
                    type: string
                  minItems: 2
                  maxItems: 4
                  description: 2-4 subtitle file paths to compare
      responses:
        200:
          description: File contents for comparison
          content:
            application/json:
              schema:
                type: object
                properties:
                  panels:
                    type: array
                    items:
                      type: object
                      properties:
                        path:
                          type: string
                        content:
                          type: string
                        format:
                          type: string
                          enum: [ass, srt]
                        encoding:
                          type: string
                        total_lines:
                          type: integer
        400:
          description: Invalid parameters
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    import os

    data = request.get_json() or {}
    file_paths = data.get("file_paths", [])

    if not isinstance(file_paths, list) or len(file_paths) < 2 or len(file_paths) > 4:
        return jsonify({"error": "file_paths must be an array of 2-4 paths"}), 400

    panels = []
    for fp in file_paths:
        error, result = _validate_file_path(fp)
        if error:
            return jsonify({"error": f"File '{fp}': {error}"}), result

        abs_path = result

        try:
            # Detect encoding
            detected_encoding = "utf-8"
            try:
                import chardet

                with open(abs_path, "rb") as f:
                    raw = f.read()
                det = chardet.detect(raw)
                detected_encoding = det.get("encoding", "utf-8") or "utf-8"
            except ImportError:
                pass

            with open(abs_path, encoding=detected_encoding, errors="replace") as f:
                content = f.read()

            ext = os.path.splitext(abs_path)[1].lower()
            fmt = "ass" if ext in (".ass", ".ssa") else "srt"

            panels.append(
                {
                    "path": abs_path,
                    "content": content,
                    "format": fmt,
                    "encoding": detected_encoding,
                    "total_lines": len(content.splitlines()),
                }
            )

        except Exception as exc:
            logger.error("Compare read failed for %s: %s", abs_path, exc)
            return jsonify({"error": f"Failed to read {fp}: {exc}"}), 500

    return jsonify({"panels": panels})


# -- Quality Trends -------------------------------------------------------------


@bp.route("/quality-trends", methods=["GET"])
def quality_trends():
    """Get quality score trends over time.
    ---
    get:
      security:
        - apiKeyAuth: []
      tags:
        - Tools
      summary: Get quality trends
      description: Returns daily average quality scores and check counts for the specified number of days.
      parameters:
        - in: query
          name: days
          schema:
            type: integer
            default: 30
          description: Number of days to look back
      responses:
        200:
          description: Quality trends
          content:
            application/json:
              schema:
                type: object
                properties:
                  trends:
                    type: array
                    items:
                      type: object
                      properties:
                        date:
                          type: string
                        avg_score:
                          type: number
                        check_count:
                          type: integer
                  days:
                    type: integer
        500:
          description: Processing error
    """
    from db.quality import get_quality_trends

    days = request.args.get("days", 30, type=int)
    days = max(1, min(365, days))  # Clamp to reasonable range

    try:
        trends = get_quality_trends(days)
        return jsonify({"trends": trends, "days": days})
    except Exception as exc:
        logger.error("Quality trends failed: %s", exc)
        return jsonify({"error": f"Quality trends failed: {exc}"}), 500
