"""Subtitle validation routes: validate, parse, health-check, health-fix."""

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

    from db.quality import save_health_result
    from health_checker import run_health_checks

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
                results.append(
                    {
                        "file_path": fp,
                        "error": error,
                        "score": 0,
                        "issues": [],
                        "checks_run": 0,
                    }
                )
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
                results.append(
                    {
                        "file_path": fp,
                        "error": str(exc),
                        "score": 0,
                        "issues": [],
                        "checks_run": 0,
                    }
                )

        valid_count = sum(1 for r in results if "error" not in r)
        avg_score = round(total_score / valid_count, 1) if valid_count > 0 else 0.0

        return jsonify(
            {
                "results": results,
                "summary": {
                    "total": len(results),
                    "avg_score": avg_score,
                    "total_issues": total_issues,
                },
            }
        )

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

    from db.quality import save_health_result
    from health_checker import FIXABLE_CHECKS, apply_fixes, run_health_checks

    data = request.get_json() or {}
    file_path = data.get("file_path", "")
    fixes = data.get("fixes", [])

    if not isinstance(fixes, list) or not fixes:
        return jsonify({"error": "fixes must be a non-empty array of fix names"}), 400

    invalid = set(fixes) - FIXABLE_CHECKS
    if invalid:
        return jsonify(
            {"error": f"Invalid fix names: {invalid}. Valid: {sorted(FIXABLE_CHECKS)}"}
        ), 400

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

        return jsonify(
            {
                "status": "fixed",
                "fixes_applied": fix_result["fixes_applied"],
                "counts": fix_result["counts"],
                "new_score": check_result["score"],
                "remaining_issues": len(check_result["issues"]),
            }
        )

    except Exception as exc:
        logger.error("Health fix failed for %s: %s", abs_path, exc)
        return jsonify({"error": f"Health fix failed: {exc}"}), 500
