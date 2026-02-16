"""Subtitle processing tools -- /tools/remove-hi, /tools/adjust-timing, /tools/common-fixes, /tools/preview."""

import os
import re
import shutil
import logging

from flask import Blueprint, request, jsonify

bp = Blueprint("tools", __name__, url_prefix="/api/v1/tools")
logger = logging.getLogger(__name__)


def _validate_file_path(file_path: str) -> tuple:
    """Validate that file_path exists, is a subtitle, and is under media_path.

    Returns:
        (None, None) if valid, otherwise (error_message, status_code).
        On success returns (None, file_path) -- normalized file_path.
    """
    from config import get_settings

    if not file_path:
        return ("file_path is required", 400)

    s = get_settings()
    media_path = os.path.abspath(s.media_path)
    abs_path = os.path.abspath(file_path)

    # Security: ensure file is under media_path
    if not abs_path.startswith(media_path + os.sep) and abs_path != media_path:
        return ("file_path must be under the configured media_path", 403)

    if not os.path.exists(abs_path):
        return (f"File not found: {file_path}", 404)

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in (".srt", ".ass", ".ssa"):
        return ("Only .srt, .ass, and .ssa files are supported", 400)

    return (None, abs_path)


def _create_backup(file_path: str) -> str:
    """Create a .bak backup of a file before modifying it.

    Returns:
        Path to the backup file.
    """
    base, ext = os.path.splitext(file_path)
    bak_path = f"{base}.bak{ext}"
    shutil.copy2(file_path, bak_path)
    return bak_path


# -- Remove HI -----------------------------------------------------------------


@bp.route("/remove-hi", methods=["POST"])
def remove_hi():
    """Remove hearing-impaired markers from a subtitle file.
    ---
    post:
      tags:
        - Tools
      summary: Remove HI markers
      description: Removes hearing-impaired markers (e.g., [music], (laughing)) from a subtitle file. Creates a .bak backup before modifying.
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
          description: HI markers removed
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  original_lines:
                    type: integer
                  cleaned_lines:
                    type: integer
                  removed:
                    type: integer
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    from hi_remover import remove_hi_markers, remove_hi_from_srt

    data = request.get_json() or {}
    file_path = data.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()

        original_lines = len(content.splitlines())

        ext = os.path.splitext(abs_path)[1].lower()
        if ext == ".srt":
            cleaned = remove_hi_from_srt(content)
        else:
            # For ASS: apply line-by-line removal to preserve structure
            cleaned = remove_hi_markers(content)

        cleaned_lines = len(cleaned.splitlines())

        # Create backup before modifying
        _create_backup(abs_path)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        logger.info("HI removal: %s -- %d lines -> %d lines", abs_path, original_lines, cleaned_lines)

        return jsonify({
            "status": "cleaned",
            "original_lines": original_lines,
            "cleaned_lines": cleaned_lines,
            "removed": original_lines - cleaned_lines,
        })

    except Exception as exc:
        logger.error("HI removal failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"HI removal failed: {exc}"}), 500


# -- Adjust Timing --------------------------------------------------------------


_SRT_TIMESTAMP_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")
_ASS_DIALOGUE_RE = re.compile(r"^(Dialogue:\s*\d+,)(\d+):(\d{2}):(\d{2})\.(\d{2}),(\d+):(\d{2}):(\d{2})\.(\d{2}),(.*)$")


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


@bp.route("/adjust-timing", methods=["POST"])
def adjust_timing():
    """Shift subtitle timestamps by offset_ms.
    ---
    post:
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
        with open(abs_path, "r", encoding="utf-8") as f:
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
                    start = _shift_ass_time(int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), offset_ms)
                    end = _shift_ass_time(int(m.group(6)), int(m.group(7)), int(m.group(8)), int(m.group(9)), offset_ms)
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

        logger.info("Timing adjusted: %s -- %d lines shifted by %dms", abs_path, modified_count, offset_ms)

        return jsonify({
            "status": "adjusted",
            "lines_modified": modified_count,
            "offset_ms": offset_ms,
        })

    except Exception as exc:
        logger.error("Timing adjustment failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Timing adjustment failed: {exc}"}), 500


# -- Common Fixes ---------------------------------------------------------------


@bp.route("/common-fixes", methods=["POST"])
def common_fixes():
    """Apply common subtitle fixes (encoding, whitespace, linebreaks, empty_lines).
    ---
    post:
      tags:
        - Tools
      summary: Apply common fixes
      description: Applies one or more common subtitle fixes. Creates a .bak backup before modifying.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - fixes
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                fixes:
                  type: array
                  items:
                    type: string
                    enum: [encoding, whitespace, linebreaks, empty_lines]
                  description: List of fix types to apply
      responses:
        200:
          description: Fixes applied
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  fixes_applied:
                    type: array
                    items:
                      type: string
                  lines_before:
                    type: integer
                  lines_after:
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
    fixes = data.get("fixes", [])

    if not isinstance(fixes, list) or not fixes:
        return jsonify({"error": "fixes must be a non-empty array of fix names"}), 400

    valid_fixes = {"encoding", "whitespace", "linebreaks", "empty_lines"}
    invalid = set(fixes) - valid_fixes
    if invalid:
        return jsonify({"error": f"Invalid fix names: {invalid}. Valid: {valid_fixes}"}), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Read file content
        content = None

        if "encoding" in fixes:
            # Try chardet detection if available
            try:
                import chardet
                with open(abs_path, "rb") as f:
                    raw = f.read()
                detected = chardet.detect(raw)
                encoding = detected.get("encoding", "utf-8") or "utf-8"
                content = raw.decode(encoding, errors="replace")
            except ImportError:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
        else:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

        lines_before = len(content.splitlines())
        applied = []

        if "linebreaks" in fixes:
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            applied.append("linebreaks")

            # For ASS files, also fix ASS-specific line breaks
            ext = os.path.splitext(abs_path)[1].lower()
            if ext in (".ass", ".ssa"):
                try:
                    from ass_utils import fix_line_breaks
                    # Apply fix_line_breaks to Dialogue lines only
                    lines = content.split("\n")
                    new_lines = []
                    for line in lines:
                        if line.startswith("Dialogue:"):
                            # Extract and fix the text portion (last field)
                            parts = line.split(",", 9)
                            if len(parts) >= 10:
                                parts[9] = fix_line_breaks(parts[9])
                                new_lines.append(",".join(parts))
                            else:
                                new_lines.append(line)
                        else:
                            new_lines.append(line)
                    content = "\n".join(new_lines)
                except ImportError:
                    pass

        if "whitespace" in fixes:
            content = "\n".join(line.rstrip() for line in content.split("\n"))
            applied.append("whitespace")

        if "empty_lines" in fixes:
            # Remove consecutive empty lines (keep single blank lines)
            lines = content.split("\n")
            new_lines = []
            prev_empty = False
            for line in lines:
                is_empty = line.strip() == ""
                if is_empty and prev_empty:
                    continue
                new_lines.append(line)
                prev_empty = is_empty
            content = "\n".join(new_lines)
            applied.append("empty_lines")

        if "encoding" in fixes:
            applied.append("encoding")

        lines_after = len(content.splitlines())

        # Create backup before modifying
        _create_backup(abs_path)

        # Always write as UTF-8
        with open(abs_path, "w", encoding="utf-8", newline="") as f:
            f.write(content)

        logger.info("Common fixes applied to %s: %s (%d -> %d lines)", abs_path, applied, lines_before, lines_after)

        return jsonify({
            "status": "fixed",
            "fixes_applied": applied,
            "lines_before": lines_before,
            "lines_after": lines_after,
        })

    except Exception as exc:
        logger.error("Common fixes failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Common fixes failed: {exc}"}), 500


# -- Preview --------------------------------------------------------------------


@bp.route("/preview", methods=["GET"])
def preview_file():
    """Preview the first 100 lines of a subtitle file.
    ---
    get:
      tags:
        - Tools
      summary: Preview subtitle file
      description: Returns the first 100 lines of a subtitle file with encoding detection.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to subtitle file (must be under media_path)
      responses:
        200:
          description: File preview
          content:
            application/json:
              schema:
                type: object
                properties:
                  format:
                    type: string
                    enum: [ass, srt]
                  lines:
                    type: array
                    items:
                      type: string
                  total_lines:
                    type: integer
                  encoding:
                    type: string
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    file_path = request.args.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Detect encoding
        detected_encoding = "utf-8"
        try:
            import chardet
            with open(abs_path, "rb") as f:
                raw = f.read(4096)
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(abs_path, "r", encoding=detected_encoding, errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        preview_lines = [line.rstrip("\n\r") for line in all_lines[:100]]

        ext = os.path.splitext(abs_path)[1].lower()
        fmt = "ass" if ext in (".ass", ".ssa") else "srt"

        return jsonify({
            "format": fmt,
            "lines": preview_lines,
            "total_lines": total_lines,
            "encoding": detected_encoding,
        })

    except Exception as exc:
        logger.error("Preview failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Preview failed: {exc}"}), 500
