"""Subtitle health routes: health-check (scan + persist), health-fix (apply auto-fixes)."""

import logging

from flask import jsonify, request

from routes.tools import bp
from routes.tools._helpers import _validate_file_path

logger = logging.getLogger(__name__)


@bp.route("/health-check", methods=["POST"])
def health_check():
    """Run health checks on one or more subtitle files and persist results.
    ---
    post:
      security:
        - apiKeyAuth: []
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

            # Serialize datetime to ISO string for JSON response
            response_result = {
                **check_result,
                "checked_at": (
                    check_result["checked_at"].isoformat()
                    if hasattr(check_result["checked_at"], "isoformat")
                    else check_result["checked_at"]
                ),
            }
            return jsonify(response_result)

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

                # Serialize datetime to ISO string for JSON response
                results.append(
                    {
                        **check_result,
                        "checked_at": (
                            check_result["checked_at"].isoformat()
                            if hasattr(check_result["checked_at"], "isoformat")
                            else check_result["checked_at"]
                        ),
                    }
                )
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


@bp.route("/health-fix", methods=["POST"])
def health_fix():
    """Apply auto-fixes for detected health issues and re-check quality.
    ---
    post:
      security:
        - apiKeyAuth: []
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
