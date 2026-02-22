"""Subtitle processing tools -- /tools/remove-hi, /tools/adjust-timing, /tools/common-fixes, /tools/preview, /tools/content, /tools/backup, /tools/validate, /tools/parse, /tools/health-check, /tools/health-fix, /tools/advanced-sync, /tools/compare, /tools/quality-trends."""

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
    from config import get_settings, map_path

    if not file_path:
        return ("file_path is required", 400)

    # Apply path mapping so Sonarr-style remote paths resolve to local container paths.
    file_path = map_path(file_path)

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


# -- Content (Full Read/Write for Editor) --------------------------------------


@bp.route("/content", methods=["GET"])
def get_file_content():
    """Read full subtitle file content for editing.
    ---
    get:
      tags:
        - Tools
      summary: Read full subtitle content
      description: Returns the complete content of a subtitle file with encoding detection and metadata. Used by the subtitle editor for full file loading.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to subtitle file (must be under media_path)
      responses:
        200:
          description: Full file content
          content:
            application/json:
              schema:
                type: object
                properties:
                  format:
                    type: string
                    enum: [ass, srt]
                  content:
                    type: string
                  encoding:
                    type: string
                  size_bytes:
                    type: integer
                  total_lines:
                    type: integer
                  last_modified:
                    type: number
                    description: File modification time (for optimistic concurrency)
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
                raw = f.read()
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(abs_path, "r", encoding=detected_encoding, errors="replace") as f:
            content = f.read()

        ext = os.path.splitext(abs_path)[1].lower()
        fmt = "ass" if ext in (".ass", ".ssa") else "srt"

        return jsonify({
            "format": fmt,
            "content": content,
            "encoding": detected_encoding,
            "size_bytes": os.path.getsize(abs_path),
            "total_lines": len(content.splitlines()),
            "last_modified": os.path.getmtime(abs_path),
        })

    except Exception as exc:
        logger.error("Content read failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Content read failed: {exc}"}), 500


@bp.route("/content", methods=["PUT"])
def save_file_content():
    """Save edited subtitle content with optimistic concurrency check.
    ---
    put:
      tags:
        - Tools
      summary: Save edited subtitle content
      description: Saves edited subtitle content after creating a .bak backup. Checks last_modified for optimistic concurrency -- returns 409 if the file was modified since it was loaded.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - content
                - last_modified
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                content:
                  type: string
                  description: Full edited file content
                last_modified:
                  type: number
                  description: last_modified value from GET /content response
      responses:
        200:
          description: File saved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  backup_path:
                    type: string
                  new_mtime:
                    type: number
        400:
          description: Invalid parameters
        403:
          description: File outside media_path
        404:
          description: File not found
        409:
          description: File modified since loaded (optimistic concurrency conflict)
        500:
          description: Save error
    """
    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    content = data.get("content")
    last_modified = data.get("last_modified")

    if content is None:
        return jsonify({"error": "content is required"}), 400
    if last_modified is None:
        return jsonify({"error": "last_modified is required"}), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Optimistic concurrency: check if file was modified since loaded
        current_mtime = os.path.getmtime(abs_path)
        if abs(current_mtime - float(last_modified)) > 0.01:
            return jsonify({
                "error": "File has been modified since you loaded it",
                "current_mtime": current_mtime,
            }), 409

        # Create backup BEFORE writing (mandatory -- project safety rule)
        bak_path = _create_backup(abs_path)

        # Write content as UTF-8
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        new_mtime = os.path.getmtime(abs_path)

        logger.info("Content saved: %s (backup: %s)", abs_path, bak_path)

        return jsonify({
            "status": "saved",
            "backup_path": bak_path,
            "new_mtime": new_mtime,
        })

    except Exception as exc:
        logger.error("Content save failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Content save failed: {exc}"}), 500


# -- Backup Content (for Diff View) --------------------------------------------


@bp.route("/backup", methods=["GET"])
def get_backup_content():
    """Read backup file content for diff comparison.
    ---
    get:
      tags:
        - Tools
      summary: Read backup file content
      description: Returns the content of the .bak backup file for the given original file path. Used for diff view in the subtitle editor.
      parameters:
        - in: query
          name: file_path
          required: true
          schema:
            type: string
          description: Path to the ORIGINAL subtitle file (not the .bak path)
      responses:
        200:
          description: Backup content
          content:
            application/json:
              schema:
                type: object
                properties:
                  content:
                    type: string
                  encoding:
                    type: string
                  backup_path:
                    type: string
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: Original file or backup not found
        500:
          description: Read error
    """
    file_path = request.args.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        # Compute backup path (same logic as _create_backup)
        base, ext = os.path.splitext(abs_path)
        bak_path = f"{base}.bak{ext}"

        if not os.path.exists(bak_path):
            return jsonify({"error": f"No backup found for {file_path}"}), 404

        # Detect encoding of backup file
        detected_encoding = "utf-8"
        try:
            import chardet
            with open(bak_path, "rb") as f:
                raw = f.read()
            det = chardet.detect(raw)
            detected_encoding = det.get("encoding", "utf-8") or "utf-8"
        except ImportError:
            pass

        with open(bak_path, "r", encoding=detected_encoding, errors="replace") as f:
            content = f.read()

        return jsonify({
            "content": content,
            "encoding": detected_encoding,
            "backup_path": bak_path,
        })

    except Exception as exc:
        logger.error("Backup read failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Backup read failed: {exc}"}), 500


# -- Validate Content -----------------------------------------------------------


@bp.route("/validate", methods=["POST"])
def validate_content():
    """Validate subtitle structure via pysubs2.
    ---
    post:
      tags:
        - Tools
      summary: Validate subtitle content
      description: Validates ASS/SRT subtitle structure using pysubs2 parsing. Accepts raw content string (not read from disk) so unsaved edits can be validated before saving.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - content
              properties:
                file_path:
                  type: string
                  description: Optional -- used for format detection from extension. If omitted, format param is required.
                content:
                  type: string
                  description: Subtitle content to validate
                format:
                  type: string
                  enum: [ass, srt]
                  description: Subtitle format (used if file_path not provided)
      responses:
        200:
          description: Validation result
          content:
            application/json:
              schema:
                type: object
                properties:
                  valid:
                    type: boolean
                  event_count:
                    type: integer
                  style_count:
                    type: integer
                  warnings:
                    type: array
                    items:
                      type: string
                  error:
                    type: string
        400:
          description: Invalid parameters (missing content and format)
        500:
          description: Validation error
    """
    import pysubs2

    data = request.get_json() or {}
    content = data.get("content")
    file_path = data.get("file_path", "")
    fmt = data.get("format", "")

    if content is None:
        return jsonify({"error": "content is required"}), 400

    # Determine format from file extension or explicit param
    if file_path:
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".ass", ".ssa"):
            fmt = "ass"
        elif ext == ".srt":
            fmt = "srt"

    if fmt not in ("ass", "srt"):
        return jsonify({"error": "Unable to determine format. Provide file_path with extension or format param ('ass' or 'srt')."}), 400

    try:
        subs = pysubs2.SSAFile.from_string(content, format_=fmt)

        warnings = []
        event_count = len([e for e in subs.events if not e.is_comment])
        style_count = len(subs.styles) if hasattr(subs, "styles") else 0

        if event_count == 0:
            warnings.append("No subtitle events found")

        return jsonify({
            "valid": True,
            "event_count": event_count,
            "style_count": style_count,
            "warnings": warnings,
        })

    except pysubs2.exceptions.UnknownFPSError as exc:
        return jsonify({
            "valid": False,
            "error": f"FPS error: {exc}",
            "warnings": [],
        })
    except Exception as exc:
        logger.error("Validation failed: %s", exc)
        return jsonify({
            "valid": False,
            "error": str(exc),
            "warnings": [],
        })


# -- Parse Cues (for Timeline) -------------------------------------------------


@bp.route("/parse", methods=["POST"])
def parse_cues():
    """Extract structured cue data for timeline visualization.
    ---
    post:
      tags:
        - Tools
      summary: Parse subtitle cues
      description: Parses a subtitle file using pysubs2 and returns structured cue data (start, end, text, style) for timeline visualization. For ASS files, includes style classification (dialog vs signs/songs).
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
          description: Parsed cue data
          content:
            application/json:
              schema:
                type: object
                properties:
                  cues:
                    type: array
                    items:
                      type: object
                      properties:
                        start:
                          type: number
                          description: Start time in seconds
                        end:
                          type: number
                          description: End time in seconds
                        text:
                          type: string
                        style:
                          type: string
                  total_duration:
                    type: number
                    description: Maximum end time in seconds
                  cue_count:
                    type: integer
                  format:
                    type: string
                    enum: [ass, srt]
                  styles:
                    type: object
                    nullable: true
                    description: Style classification (ASS only) -- maps style name to dialog/signs/songs
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Parse error
    """
    import pysubs2

    data = request.get_json() or {}
    file_path = data.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        subs = pysubs2.load(abs_path)

        cues = []
        max_end = 0.0
        for event in subs.events:
            if event.is_comment:
                continue
            start_sec = event.start / 1000.0
            end_sec = event.end / 1000.0
            if end_sec > max_end:
                max_end = end_sec
            cues.append({
                "start": start_sec,
                "end": end_sec,
                "text": event.plaintext,
                "style": event.style,
            })

        ext = os.path.splitext(abs_path)[1].lower()
        fmt = "ass" if ext in (".ass", ".ssa") else "srt"

        # Style classification for ASS files
        styles = None
        if fmt == "ass":
            try:
                from ass_utils import classify_styles
                dialog_styles, signs_styles = classify_styles(subs)
                styles = {}
                for s in dialog_styles:
                    styles[s] = "dialog"
                for s in signs_styles:
                    styles[s] = "signs"
            except ImportError:
                pass

        logger.info("Parsed %d cues from %s (%.1fs duration)", len(cues), abs_path, max_end)

        # Load quality sidecar if available (written by translator.py per-line scoring)
        quality_sidecar_path = abs_path + ".quality.json"
        quality_scores = None
        if os.path.exists(quality_sidecar_path):
            try:
                import json as _json
                with open(quality_sidecar_path, "r", encoding="utf-8") as _qf:
                    quality_scores = _json.load(_qf)
            except Exception as _qe:
                logger.debug("Failed to load quality sidecar %s: %s", quality_sidecar_path, _qe)

        if quality_scores and len(quality_scores) == len(cues):
            for cue, score in zip(cues, quality_scores):
                cue["quality_score"] = score

        return jsonify({
            "cues": cues,
            "total_duration": max_end,
            "cue_count": len(cues),
            "format": fmt,
            "styles": styles,
            "has_quality_scores": quality_scores is not None and len(quality_scores) == len(cues),
        })

    except Exception as exc:
        logger.error("Parse failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Parse failed: {exc}"}), 500


# -- Health Check ---------------------------------------------------------------


@bp.route("/health-check", methods=["POST"])
def health_check():
    """Run health checks on one or more subtitle files and persist results.
    ---
    post:
      tags:
        - Tools
      summary: Run subtitle health checks
      description: Runs 10 quality checks on subtitle file(s), calculates a 0-100 score, and persists results. Accepts a single file_path or a batch of file_paths (max 50).
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                file_path:
                  type: string
                  description: Single file path to check
                file_paths:
                  type: array
                  items:
                    type: string
                  description: Batch of file paths to check (max 50)
      responses:
        200:
          description: Health check results
          content:
            application/json:
              schema:
                type: object
                properties:
                  file_path:
                    type: string
                  checks_run:
                    type: integer
                  issues:
                    type: array
                    items:
                      type: object
                  score:
                    type: integer
                  checked_at:
                    type: string
        400:
          description: Invalid parameters
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    import json as json_mod
    from health_checker import run_health_checks
    from db.quality import save_health_result

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    file_paths = data.get("file_paths", [])

    # Single file mode
    if file_path and not file_paths:
        error, result = _validate_file_path(file_path)
        if error:
            return jsonify({"error": error}), result

        abs_path = result

        try:
            check_result = run_health_checks(abs_path)

            # Persist result
            try:
                save_health_result(
                    file_path=abs_path,
                    score=check_result["score"],
                    issues_json=json_mod.dumps(check_result["issues"]),
                    checks_run=check_result["checks_run"],
                    checked_at=check_result["checked_at"],
                )
            except Exception as e:
                logger.warning("Failed to persist health result for %s: %s", abs_path, e)

            return jsonify(check_result)

        except Exception as exc:
            logger.error("Health check failed for %s: %s", abs_path, exc)
            return jsonify({"error": f"Health check failed: {exc}"}), 500

    # Batch mode
    if file_paths:
        if len(file_paths) > 50:
            return jsonify({"error": "Maximum 50 files per batch"}), 400

        results = []
        total_issues = 0
        total_score = 0

        for fp in file_paths:
            error, result = _validate_file_path(fp)
            if error:
                results.append({
                    "file_path": fp,
                    "error": error,
                    "score": 0,
                    "issues": [],
                    "checks_run": 0,
                })
                continue

            abs_path = result
            try:
                check_result = run_health_checks(abs_path)

                try:
                    save_health_result(
                        file_path=abs_path,
                        score=check_result["score"],
                        issues_json=json_mod.dumps(check_result["issues"]),
                        checks_run=check_result["checks_run"],
                        checked_at=check_result["checked_at"],
                    )
                except Exception as e:
                    logger.warning("Failed to persist health result for %s: %s", abs_path, e)

                results.append(check_result)
                total_issues += len(check_result["issues"])
                total_score += check_result["score"]

            except Exception as exc:
                logger.error("Health check failed for %s: %s", abs_path, exc)
                results.append({
                    "file_path": fp,
                    "error": str(exc),
                    "score": 0,
                    "issues": [],
                    "checks_run": 0,
                })

        valid_count = sum(1 for r in results if "error" not in r)
        avg_score = round(total_score / valid_count, 1) if valid_count > 0 else 0.0

        return jsonify({
            "results": results,
            "summary": {
                "total": len(results),
                "avg_score": avg_score,
                "total_issues": total_issues,
            },
        })

    return jsonify({"error": "file_path or file_paths is required"}), 400


# -- Health Fix -----------------------------------------------------------------


@bp.route("/health-fix", methods=["POST"])
def health_fix():
    """Apply auto-fixes for detected health issues and re-check quality.
    ---
    post:
      tags:
        - Tools
      summary: Auto-fix subtitle health issues
      description: Applies specified auto-fixes to a subtitle file. Creates a .bak backup before modifying. Re-runs health check after fixes and persists updated result.
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
                    enum: [duplicate_lines, timing_overlaps, missing_styles, empty_events, negative_timing, zero_duration]
                  description: List of fix names to apply
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
                  counts:
                    type: object
                  new_score:
                    type: integer
                  remaining_issues:
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
    import json as json_mod
    from health_checker import apply_fixes, run_health_checks, FIXABLE_CHECKS
    from db.quality import save_health_result

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    fixes = data.get("fixes", [])

    if not isinstance(fixes, list) or not fixes:
        return jsonify({"error": "fixes must be a non-empty array of fix names"}), 400

    invalid = set(fixes) - FIXABLE_CHECKS
    if invalid:
        return jsonify({
            "error": f"Invalid fix names: {invalid}. Valid: {sorted(FIXABLE_CHECKS)}"
        }), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        fix_result = apply_fixes(abs_path, fixes)

        # Re-run health check and persist
        check_result = run_health_checks(abs_path)
        try:
            save_health_result(
                file_path=abs_path,
                score=check_result["score"],
                issues_json=json_mod.dumps(check_result["issues"]),
                checks_run=check_result["checks_run"],
                checked_at=check_result["checked_at"],
            )
        except Exception as e:
            logger.warning("Failed to persist health result for %s: %s", abs_path, e)

        logger.info("Health fix applied to %s: %s", abs_path, fix_result["fixes_applied"])

        return jsonify({
            "status": "fixed",
            "fixes_applied": fix_result["fixes_applied"],
            "counts": fix_result["counts"],
            "new_score": check_result["score"],
            "remaining_issues": len(check_result["issues"]),
        })

    except Exception as exc:
        logger.error("Health fix failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Health fix failed: {exc}"}), 500


# -- Advanced Sync --------------------------------------------------------------


@bp.route("/advanced-sync", methods=["POST"])
def advanced_sync():
    """Apply advanced sync operations (offset, speed, framerate) via pysubs2.
    ---
    post:
      tags:
        - Tools
      summary: Advanced subtitle sync
      description: Applies advanced timing sync operations to a subtitle file using pysubs2. Supports offset (ms shift), speed (playback rate adjustment), and framerate conversion. Creates a .bak backup before modifying. Supports preview mode.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - file_path
                - operation
              properties:
                file_path:
                  type: string
                  description: Path to subtitle file (must be under media_path)
                operation:
                  type: string
                  enum: [offset, speed, framerate]
                  description: Sync operation type
                offset_ms:
                  type: integer
                  description: Offset in milliseconds (for operation=offset)
                speed_factor:
                  type: number
                  description: Speed multiplier 0.5-2.0 (for operation=speed)
                in_fps:
                  type: number
                  description: Source framerate (for operation=framerate)
                out_fps:
                  type: number
                  description: Target framerate (for operation=framerate)
                preview:
                  type: boolean
                  description: If true, return preview of changes without saving
                  default: false
      responses:
        200:
          description: Sync applied or preview returned
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                  operation:
                    type: string
                  events:
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
    import pysubs2

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    operation = data.get("operation", "")
    preview = data.get("preview", False)

    if operation not in ("offset", "speed", "framerate"):
        return jsonify({"error": "operation must be one of: offset, speed, framerate"}), 400

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        subs = pysubs2.load(abs_path)
        event_count = len([e for e in subs.events if not e.is_comment])

        if operation == "offset":
            offset_ms = data.get("offset_ms")
            if offset_ms is None or not isinstance(offset_ms, (int, float)):
                return jsonify({"error": "offset_ms (integer) is required for offset operation"}), 400
            offset_ms = int(offset_ms)

            if preview:
                return _sync_preview(subs, lambda s: s.shift(ms=offset_ms), operation, offset_ms=offset_ms)

            _create_backup(abs_path)
            subs.shift(ms=offset_ms)
            subs.save(abs_path)

            logger.info("Advanced sync (offset %dms) applied to %s", offset_ms, abs_path)
            return jsonify({"status": "synced", "operation": "offset", "events": event_count, "offset_ms": offset_ms})

        elif operation == "speed":
            speed_factor = data.get("speed_factor")
            if speed_factor is None or not isinstance(speed_factor, (int, float)):
                return jsonify({"error": "speed_factor (float) is required for speed operation"}), 400
            speed_factor = float(speed_factor)
            if not (0.5 <= speed_factor <= 2.0):
                return jsonify({"error": "speed_factor must be between 0.5 and 2.0"}), 400

            def apply_speed(s):
                for event in s.events:
                    event.start = round(event.start / speed_factor)
                    event.end = round(event.end / speed_factor)

            if preview:
                return _sync_preview(subs, apply_speed, operation, speed_factor=speed_factor)

            _create_backup(abs_path)
            apply_speed(subs)
            subs.save(abs_path)

            logger.info("Advanced sync (speed %.2fx) applied to %s", speed_factor, abs_path)
            return jsonify({"status": "synced", "operation": "speed", "events": event_count, "speed_factor": speed_factor})

        elif operation == "framerate":
            in_fps = data.get("in_fps")
            out_fps = data.get("out_fps")
            if in_fps is None or out_fps is None:
                return jsonify({"error": "in_fps and out_fps are required for framerate operation"}), 400
            in_fps = float(in_fps)
            out_fps = float(out_fps)
            if in_fps <= 0 or out_fps <= 0:
                return jsonify({"error": "in_fps and out_fps must be positive"}), 400

            if preview:
                return _sync_preview(subs, lambda s: s.transform_framerate(in_fps, out_fps), operation,
                                     in_fps=in_fps, out_fps=out_fps)

            _create_backup(abs_path)
            subs.transform_framerate(in_fps, out_fps)
            subs.save(abs_path)

            logger.info("Advanced sync (framerate %.3f->%.3f) applied to %s", in_fps, out_fps, abs_path)
            return jsonify({"status": "synced", "operation": "framerate", "events": event_count,
                            "in_fps": in_fps, "out_fps": out_fps})

    except Exception as exc:
        logger.error("Advanced sync failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Advanced sync failed: {exc}"}), 500


def _sync_preview(subs, apply_fn, operation, **params):
    """Generate a preview of sync operation on 5 representative events.

    Returns before/after timestamps for first, 25%, 50%, 75%, last events.
    """
    non_comment = [e for e in subs.events if not e.is_comment]
    if not non_comment:
        return jsonify({"status": "preview", "operation": operation, "events": []})

    # Select 5 representative indices
    n = len(non_comment)
    indices = sorted(set([
        0,
        max(0, n // 4),
        max(0, n // 2),
        max(0, 3 * n // 4),
        n - 1,
    ]))

    # Capture before timestamps
    before = []
    for i in indices:
        e = non_comment[i]
        before.append({"index": i, "start": e.start, "end": e.end, "text": e.plaintext[:60]})

    # Apply operation
    apply_fn(subs)

    # Capture after timestamps
    non_comment_after = [e for e in subs.events if not e.is_comment]
    preview_events = []
    for idx, b in enumerate(before):
        i = b["index"]
        if i < len(non_comment_after):
            a = non_comment_after[i]
            preview_events.append({
                "index": i,
                "text": b["text"],
                "before": {"start": b["start"], "end": b["end"]},
                "after": {"start": a.start, "end": a.end},
            })

    return jsonify({
        "status": "preview",
        "operation": operation,
        "events": preview_events,
        **params,
    })


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

            with open(abs_path, "r", encoding=detected_encoding, errors="replace") as f:
                content = f.read()

            ext = os.path.splitext(abs_path)[1].lower()
            fmt = "ass" if ext in (".ass", ".ssa") else "srt"

            panels.append({
                "path": abs_path,
                "content": content,
                "format": fmt,
                "encoding": detected_encoding,
                "total_lines": len(content.splitlines()),
            })

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
