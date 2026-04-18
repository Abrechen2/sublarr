"""Subtitle editing routes: remove-hi, remove-credits."""

import logging
import os

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _create_backup, _validate_file_path

logger = logging.getLogger(__name__)


@bp.route("/remove-hi", methods=["POST"])
def remove_hi():
    """Remove hearing-impaired markers from a subtitle file.
    ---
    post:
      security:
        - apiKeyAuth: []
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
    from hi_remover import remove_hi_from_srt, remove_hi_markers

    data = request.get_json() or {}
    file_path = data.get("file_path", "")

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        with open(abs_path, encoding="utf-8") as f:
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

        logger.info(
            "HI removal: %s -- %d lines -> %d lines", abs_path, original_lines, cleaned_lines
        )

        return jsonify(
            {
                "status": "cleaned",
                "original_lines": original_lines,
                "cleaned_lines": cleaned_lines,
                "removed": original_lines - cleaned_lines,
            }
        )

    except Exception as exc:
        logger.error("HI removal failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"HI removal failed: {exc}"}), 500


@bp.route("/remove-credits", methods=["POST"])
def remove_credits():
    """Remove staff credit lines from a subtitle file.
    ---
    post:
      security:
        - apiKeyAuth: []
      tags:
        - Tools
      summary: Remove credit lines
      description: Detects and removes staff credit lines (role markers, credit prefixes,
        duration heuristic, isolated names) from .srt/.ass/.ssa files. Creates a .bak
        backup before modifying. Supports dry_run preview without modification.
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
                dry_run:
                  type: boolean
                  description: If true, return preview without modifying file
      responses:
        200:
          description: Credits removed (or dry_run preview)
        400:
          description: Invalid file path or unsupported format
        403:
          description: File outside media_path
        404:
          description: File not found
        500:
          description: Processing error
    """
    from credit_remover import remove_credits_from_ass, remove_credits_from_srt

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    dry_run = bool(data.get("dry_run", False))

    error, result = _validate_file_path(file_path)
    if error:
        return jsonify({"error": error}), result

    abs_path = result

    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()

        original_lines = len(content.splitlines())
        ext = os.path.splitext(abs_path)[1].lower()

        if ext == ".srt":
            cleaned, removed = remove_credits_from_srt(content)
        else:  # .ass / .ssa
            cleaned, removed = remove_credits_from_ass(content)

        if dry_run:
            # For SRT: extract preview text via block diff.
            # For ASS/SSA: pysubs2 serialises to a continuous string — block-diffing
            # is not reliable, so return an empty preview list.
            if ext == ".srt":
                original_blocks = content.strip().split("\n\n")
                cleaned_blocks = set(cleaned.strip().split("\n\n"))
                removed_texts = [
                    b.split("\n", 2)[-1].strip() for b in original_blocks if b not in cleaned_blocks
                ][:50]
            else:
                removed_texts = []
            return jsonify(
                {
                    "status": "dry_run",
                    "original_lines": original_lines,
                    "would_remove": removed,
                    "preview": removed_texts,
                }
            )

        cleaned_lines = len(cleaned.splitlines())
        bak_path = _create_backup(abs_path)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        logger.info(
            "Credit removal: %s -- %d lines -> %d lines (%d removed)",
            abs_path,
            original_lines,
            cleaned_lines,
            removed,
        )

        return jsonify(
            {
                "status": "cleaned",
                "original_lines": original_lines,
                "cleaned_lines": cleaned_lines,
                "removed": removed,
                "backed_up": bak_path,
            }
        )

    except Exception as exc:
        logger.error("Credit removal failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Credit removal failed: {exc}"}), 500
