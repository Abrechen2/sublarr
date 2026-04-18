"""Subtitle timing routes: detect-opening-ending, adjust-timing (+ SRT/ASS time-shift helpers)."""

import logging
import os
import re

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)

_SRT_TIMESTAMP_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")
_ASS_DIALOGUE_RE = re.compile(
    r"^(Dialogue:\s*\d+,)(\d+):(\d{2}):(\d{2})\.(\d{2}),(\d+):(\d{2}):(\d{2})\.(\d{2}),(.*)$"
)


def _shift_srt_timestamp(match, offset_ms: int) -> str:
    """Shift an SRT timestamp by offset_ms milliseconds."""
    h, m, s, ms = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
    total_ms = h * 3600000 + m * 60000 + s * 1000 + ms + offset_ms
    total_ms = max(0, total_ms)  # Clamp to 00:00:00,000
    new_h = total_ms // 3600000
    total_ms %= 3600000
    new_m = total_ms // 60000
    total_ms %= 60000
    new_s = total_ms // 1000
    new_ms = total_ms % 1000
    return f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"


def _shift_ass_time(h: int, m: int, s: int, cs: int, offset_ms: int) -> str:
    """Shift an ASS timestamp (H:MM:SS.cc) by offset_ms milliseconds."""
    total_ms = h * 3600000 + m * 60000 + s * 1000 + cs * 10 + offset_ms
    total_ms = max(0, total_ms)
    new_h = total_ms // 3600000
    total_ms %= 3600000
    new_m = total_ms // 60000
    total_ms %= 60000
    new_s = total_ms // 1000
    new_cs = (total_ms % 1000) // 10
    return f"{new_h}:{new_m:02d}:{new_s:02d}.{new_cs:02d}"


@bp.route("/detect-opening-ending", methods=["POST"])
def detect_opening_ending():
    """Detect OP/ED cue regions in a subtitle file.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Tools
      summary: Detect OP/ED regions
      description: Detects Opening (OP) and Ending (ED) cue regions in .srt/.ass/.ssa
        files using style name matching and duration heuristics. Read-only — no file
        modification. Returns empty detected list when nothing is found.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
      responses:
        200:
          description: Detection complete (detected may be empty)
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    from op_ed_detector import detect_op_ed_from_ass, detect_op_ed_from_srt

    data = request.get_json() or {}
    file_path = data.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()

        ext = os.path.splitext(abs_path)[1].lower()

        if ext == ".srt":
            detected = detect_op_ed_from_srt(content)
        else:  # .ass / .ssa
            detected = detect_op_ed_from_ass(content)

        return jsonify({"status": "detected", "detected": detected})

    except Exception as exc:
        logger.error("OP/ED detection failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"OP/ED detection failed: {exc}"}), 500


@bp.route("/adjust-timing", methods=["POST"])
def adjust_timing():
    """Shift subtitle timestamps by offset_ms.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Tools
      summary: Adjust subtitle timing
      description: Shifts all subtitle timestamps by the specified offset in milliseconds. Creates a .bak backup before modifying.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - offset_ms
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                offset_ms:
                  type: integer
                  description: Offset in milliseconds (positive = delay, negative = advance)
      responses:
        200:
          description: Timing adjusted
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  lines_modified:
                    type: integer
                  offset_ms:
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
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    offset_ms = data.get("offset_ms", 0)

    if not isinstance(offset_ms, (int, float)):
        return jsonify({"error": "offset_ms must be a number"}), 400
    offset_ms = int(offset_ms)

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()

        ext = os.path.splitext(abs_path)[1].lower()
        lines = content.splitlines()
        modified_count = 0

        if ext == ".srt":
            new_lines = []
            for line in lines:
                new_line, subs = _SRT_TIMESTAMP_RE.subn(
                    lambda m: _shift_srt_timestamp(m, offset_ms), line
                )
                if subs > 0:
                    modified_count += 1
                new_lines.append(new_line)
            result_content = "\n".join(new_lines)
        else:
            # ASS format
            new_lines = []
            for line in lines:
                m = _ASS_DIALOGUE_RE.match(line)
                if m:
                    prefix = m.group(1)
                    start = _shift_ass_time(
                        int(m.group(2)),
                        int(m.group(3)),
                        int(m.group(4)),
                        int(m.group(5)),
                        offset_ms,
                    )
                    end = _shift_ass_time(
                        int(m.group(6)),
                        int(m.group(7)),
                        int(m.group(8)),
                        int(m.group(9)),
                        offset_ms,
                    )
                    rest = m.group(10)
                    new_lines.append(f"{prefix}{start},{end},{rest}")
                    modified_count += 1
                else:
                    new_lines.append(line)
            result_content = "\n".join(new_lines)

        # Create backup before modifying
        _create_backup(abs_path)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(result_content)

        logger.info(
            "Timing adjusted: %s -- %d lines shifted by %dms", abs_path, modified_count, offset_ms
        )

        return jsonify(
            {
                "status": "adjusted",
                "lines_modified": modified_count,
                "offset_ms": offset_ms,
            }
        )

    except Exception as exc:
        logger.error("Timing adjustment failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Timing adjustment failed: {exc}"}), 500
