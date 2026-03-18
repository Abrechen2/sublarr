"""Subtitle analysis routes: chapters, compare, quality-trends, overlap-fix, timing-normalize, merge-lines, split-lines."""

import logging

from flask import jsonify, request

from chapters import get_chapters
from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path
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


# -- Quality Fixes -------------------------------------------------------------


@bp.route("/overlap-fix", methods=["POST"])
def overlap_fix():
    """Trim overlapping cue end times so consecutive cues no longer overlap.
    ---
    post:
      summary: Fix subtitle overlaps
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
      responses:
        200:
          description: Overlaps fixed
          content:
            application/json:
              schema:
                type: object
                properties:
                  fixed:
                    type: integer
                  backup_path:
                    type: string
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    bak = _create_backup(abs_path)
    subs = pysubs2.load(abs_path)
    fixed = 0
    for i in range(len(subs) - 1):
        if subs[i].end > subs[i + 1].start:
            subs[i].end = subs[i + 1].start - 1
            fixed += 1
    subs.save(abs_path)
    logger.info("overlap-fix: %d overlaps fixed in %s", fixed, abs_path)
    return jsonify({"fixed": fixed, "backup_path": bak})


@bp.route("/timing-normalize", methods=["POST"])
def timing_normalize():
    """Extend too-short cues and report too-long cues.
    ---
    post:
      summary: Normalize subtitle timing
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                min_ms:
                  type: integer
                  default: 500
                max_ms:
                  type: integer
                  default: 10000
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    min_ms = int(data.get("min_ms", 500))
    max_ms = int(data.get("max_ms", 10000))
    bak = _create_backup(abs_path)
    subs = pysubs2.load(abs_path)
    extended = too_long = 0
    for cue in subs:
        dur = cue.end - cue.start
        if dur < min_ms:
            cue.end = cue.start + min_ms
            extended += 1
        elif dur > max_ms:
            too_long += 1
    subs.save(abs_path)
    logger.info("timing-normalize: extended=%d, too_long=%d in %s", extended, too_long, abs_path)
    return jsonify({"extended": extended, "too_long": too_long, "backup_path": bak})


@bp.route("/merge-lines", methods=["POST"])
def merge_lines():
    """Merge consecutive cues separated by a short gap.
    ---
    post:
      summary: Merge consecutive subtitle lines
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                gap_ms:
                  type: integer
                  default: 200
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    gap_ms = int(data.get("gap_ms", 200))
    bak = _create_backup(abs_path)
    subs = pysubs2.load(abs_path)
    new_subs = pysubs2.SSAFile()
    new_subs.styles = subs.styles
    merged = 0
    i = 0
    while i < len(subs):
        cue = subs[i]
        while i + 1 < len(subs) and subs[i + 1].start - cue.end <= gap_ms:
            cue = pysubs2.SSAEvent(
                start=cue.start,
                end=subs[i + 1].end,
                text=cue.text + r"\N" + subs[i + 1].text,
            )
            i += 1
            merged += 1
        new_subs.append(cue)
        i += 1
    new_subs.save(abs_path)
    logger.info("merge-lines: %d merges in %s", merged, abs_path)
    return jsonify({"merged": merged, "backup_path": bak})


@bp.route("/split-lines", methods=["POST"])
def split_lines():
    r"""Split cues containing \N or exceeding max_chars at natural boundaries.
    ---
    post:
      summary: Split long subtitle lines
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [file_path]
              properties:
                file_path:
                  type: string
                max_chars:
                  type: integer
                  default: 80
    """
    import pysubs2

    data = request.get_json(force=True, silent=True) or {}
    error, result = _validate_file_path(data.get("file_path", ""))
    if error:
        return jsonify({"error": error}), result

    abs_path = result
    max_chars = int(data.get("max_chars", 80))
    bak = _create_backup(abs_path)
    subs = pysubs2.load(abs_path)
    new_subs = pysubs2.SSAFile()
    new_subs.styles = subs.styles
    split_count = 0

    for cue in subs:
        parts = cue.text.split(r"\N")
        if len(parts) <= 1 and len(cue.text) <= max_chars:
            new_subs.append(cue)
            continue
        dur = cue.end - cue.start
        per_part = dur // max(len(parts), 1)
        for idx, part in enumerate(parts):
            new_subs.append(
                pysubs2.SSAEvent(
                    start=cue.start + idx * per_part,
                    end=cue.start + (idx + 1) * per_part,
                    text=part.strip(),
                )
            )
        split_count += 1

    new_subs.save(abs_path)
    logger.info("split-lines: %d splits in %s", split_count, abs_path)
    return jsonify({"split": split_count, "backup_path": bak})
