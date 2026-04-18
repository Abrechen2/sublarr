"""Subtitle validation routes: validate, parse.

health-check + health-fix live in routes/tools/subtitle_health.py (B1V split).
"""

import logging
import os

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _validate_file_path

logger = logging.getLogger(__name__)


# -- Validate Content -----------------------------------------------------------
@bp.route("/validate", methods=["POST"])
def validate_content():
    """Validate subtitle structure via pysubs2.
    ---
    post:
      security:
        - apiKeyAuth: []
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
        return jsonify(
            {
                "error": "Unable to determine format. Provide file_path with extension or format param ('ass' or 'srt')."
            }
        ), 400

    try:
        subs = pysubs2.SSAFile.from_string(content, format_=fmt)

        warnings = []
        event_count = len([e for e in subs.events if not e.is_comment])
        style_count = len(subs.styles) if hasattr(subs, "styles") else 0

        if event_count == 0:
            warnings.append("No subtitle events found")

        return jsonify(
            {
                "valid": True,
                "event_count": event_count,
                "style_count": style_count,
                "warnings": warnings,
            }
        )

    except pysubs2.exceptions.UnknownFPSError as exc:
        return jsonify(
            {
                "valid": False,
                "error": f"FPS error: {exc}",
                "warnings": [],
            }
        )
    except Exception as exc:
        logger.error("Validation failed: %s", exc)
        return jsonify(
            {
                "valid": False,
                "error": str(exc),
                "warnings": [],
            }
        )


# -- Parse Cues (for Timeline) -------------------------------------------------
@bp.route("/parse", methods=["POST"])
def parse_cues():
    """Extract structured cue data for timeline visualization.
    ---
    post:
      security:
        - apiKeyAuth: []
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
            cues.append(
                {
                    "start": start_sec,
                    "end": end_sec,
                    "text": event.plaintext,
                    "style": event.style,
                }
            )

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

                with open(quality_sidecar_path, encoding="utf-8") as _qf:
                    quality_scores = _json.load(_qf)
            except Exception as _qe:
                logger.debug("Failed to load quality sidecar %s: %s", quality_sidecar_path, _qe)

        if quality_scores and len(quality_scores) == len(cues):
            for cue, score in zip(cues, quality_scores):
                cue["quality_score"] = score

        return jsonify(
            {
                "cues": cues,
                "total_duration": max_end,
                "cue_count": len(cues),
                "format": fmt,
                "styles": styles,
                "has_quality_scores": quality_scores is not None
                and len(quality_scores) == len(cues),
            }
        )

    except Exception as exc:
        logger.error("Parse failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Parse failed: {exc}"}), 500
