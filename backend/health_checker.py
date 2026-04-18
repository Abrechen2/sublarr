"""Subtitle health-check engine: orchestration, scoring, and auto-fix.

The detection rules live in health_checks.py, the repair routines in
health_fixes.py. This module wires them together:

- run_health_checks(path) loads the subtitle, runs every check and
  returns a scored report.
- apply_fixes(path, names) backs the file up, runs the requested fixers
  and re-scores.

The check/fix functions and registries are re-exported below so existing
imports (`from health_checker import check_duplicate_lines`, etc.) keep
working unchanged.
"""

import logging
import os
import shutil
from datetime import UTC, datetime

from health_checks import (
    ALL_CHECKS,
    _calculate_score,
    check_duplicate_lines,
    check_empty_events,
    check_encoding_issues,
    check_excessive_duration,
    check_line_too_long,
    check_missing_newlines,
    check_missing_styles,
    check_negative_timing,
    check_timing_overlaps,
    check_zero_duration,
)
from health_fixes import (
    FIX_MAP,
    fix_duplicate_lines,
    fix_empty_events,
    fix_missing_styles,
    fix_negative_timing,
    fix_timing_overlaps,
    fix_zero_duration,
)

logger = logging.getLogger(__name__)

# Known auto-fixable check names
FIXABLE_CHECKS = {
    "duplicate_lines",
    "timing_overlaps",
    "missing_styles",
    "empty_events",
    "negative_timing",
    "zero_duration",
}

__all__ = [
    "ALL_CHECKS",
    "FIXABLE_CHECKS",
    "FIX_MAP",
    "_calculate_score",
    "apply_fixes",
    "check_duplicate_lines",
    "check_empty_events",
    "check_encoding_issues",
    "check_excessive_duration",
    "check_line_too_long",
    "check_missing_newlines",
    "check_missing_styles",
    "check_negative_timing",
    "check_timing_overlaps",
    "check_zero_duration",
    "fix_duplicate_lines",
    "fix_empty_events",
    "fix_missing_styles",
    "fix_negative_timing",
    "fix_timing_overlaps",
    "fix_zero_duration",
    "run_health_checks",
]


def run_health_checks(file_path: str) -> dict:
    """Run all health checks on a subtitle file.

    Args:
        file_path: Absolute path to a subtitle file (.ass, .srt, .ssa).

    Returns:
        Dict with file_path, checks_run, issues, score, checked_at.
    """
    import pysubs2

    all_issues = []
    checks_run = 0

    # Read raw bytes for encoding check
    raw_bytes = None
    try:
        with open(file_path, "rb") as f:
            raw_bytes = f.read()
    except OSError as e:
        logger.error("Cannot read file %s: %s", file_path, e)
        return {
            "file_path": file_path,
            "checks_run": 0,
            "issues": [],
            "score": 0,
            "checked_at": datetime.now(UTC),
        }

    # Parse subtitle
    try:
        subs = pysubs2.load(file_path)
    except Exception as e:
        logger.error("Cannot parse subtitle %s: %s", file_path, e)
        return {
            "file_path": file_path,
            "checks_run": 0,
            "issues": [
                {
                    "check": "parse_error",
                    "severity": "error",
                    "message": f"Failed to parse subtitle file: {e}",
                    "line": None,
                    "auto_fixable": False,
                    "fix": None,
                }
            ],
            "score": 0,
            "checked_at": datetime.now(UTC),
        }

    # Run encoding check (needs raw_bytes)
    encoding_issues = check_encoding_issues(subs, raw_bytes)
    all_issues.extend(encoding_issues)
    checks_run += 1

    # Run all other checks
    for check_fn in ALL_CHECKS:
        try:
            issues = check_fn(subs)
            all_issues.extend(issues)
        except Exception as e:
            logger.warning("Check %s failed for %s: %s", check_fn.__name__, file_path, e)
        checks_run += 1

    score = _calculate_score(all_issues)

    return {
        "file_path": file_path,
        "checks_run": checks_run,
        "issues": all_issues,
        "score": score,
        "checked_at": datetime.now(UTC),
    }


def apply_fixes(file_path: str, fix_names: list) -> dict:
    """Apply requested fixes to a subtitle file.

    Creates a .bak backup before saving. Re-runs health check after fixes
    to return the updated score.

    Args:
        file_path: Absolute path to subtitle file.
        fix_names: List of check names to fix (e.g., ["duplicate_lines"]).

    Returns:
        Dict with fixes_applied, counts, new_score.
    """
    import pysubs2

    # Create backup using same .bak pattern as tools.py
    base, ext = os.path.splitext(file_path)
    bak_path = f"{base}.bak{ext}"
    shutil.copy2(file_path, bak_path)

    subs = pysubs2.load(file_path)

    fixes_applied = []
    counts = {}

    for name in fix_names:
        fix_fn = FIX_MAP.get(name)
        if fix_fn is None:
            logger.warning("Unknown fix: %s", name)
            continue
        count = fix_fn(subs)
        if count > 0:
            fixes_applied.append(name)
            counts[name] = count

    # Save modified subtitle
    subs.save(file_path)

    # Re-run health check for updated score
    result = run_health_checks(file_path)

    return {
        "fixes_applied": fixes_applied,
        "counts": counts,
        "new_score": result["score"],
    }
