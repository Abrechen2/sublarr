"""Subtitle common-fixes route: encoding, whitespace, linebreaks, empty_lines."""

import logging
import os

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)


@bp.route("/common-fixes", methods=["POST"])
def common_fixes():
    """Apply common subtitle fixes (encoding, whitespace, linebreaks, empty_lines).
    ---
    post:
      security:
        - apiKeyAuth: []
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
        # Always detect the source encoding so non-UTF-8 files (Shift_JIS,
        # Latin-1, …) survive a "whitespace only" fix. Without this, the
        # legacy code read every file as UTF-8 with errors=replace and then
        # wrote the result back as UTF-8 — silently mangling the content
        # whenever the user only asked for a non-encoding fix.
        source_encoding = "utf-8"
        try:
            import chardet

            with open(abs_path, "rb") as f:
                raw = f.read()
            detected = chardet.detect(raw)
            source_encoding = detected.get("encoding", "utf-8") or "utf-8"
            content = raw.decode(source_encoding, errors="replace")
        except ImportError:
            with open(abs_path, encoding="utf-8", errors="replace") as f:
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

        # Write back: UTF-8 if the user explicitly asked to fix the encoding,
        # otherwise preserve the source encoding so a non-encoding fix is a
        # genuine no-op for byte-equivalent content.
        write_encoding = "utf-8" if "encoding" in fixes else source_encoding
        try:
            with open(abs_path, "w", encoding=write_encoding, newline="") as f:
                f.write(content)
        except (LookupError, UnicodeEncodeError):
            # Detected encoding can't round-trip the (now-modified) text —
            # fall back to UTF-8 so we never leave the file in a broken state.
            with open(abs_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            if "encoding" not in applied:
                applied.append("encoding")

        logger.info(
            "Common fixes applied to %s: %s (%d -> %d lines)",
            abs_path,
            applied,
            lines_before,
            lines_after,
        )

        return jsonify(
            {
                "status": "fixed",
                "fixes_applied": applied,
                "lines_before": lines_before,
                "lines_after": lines_after,
            }
        )

    except Exception as exc:
        logger.error("Common fixes failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Common fixes failed: {exc}"}), 500
