"""Subtitle health-check engine: detection, scoring, and auto-fix.

Provides 10 check functions that detect issues in subtitle files,
a quality scoring system (0-100), and 6 auto-fix functions for
common problems. Uses pysubs2 for subtitle parsing.
"""

import os
import shutil
import logging
from datetime import datetime, timezone

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


# ---------------------------------------------------------------------------
# 10 Check Functions
# ---------------------------------------------------------------------------


def check_duplicate_lines(subs) -> list:
    """Detect exact duplicate events (same start, end, text, style).

    Uses set-based O(n) detection for efficiency.
    """
    issues = []
    seen = set()
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.start, event.end, event.text, event.style)
        if key in seen:
            issues.append({
                "check": "duplicate_lines",
                "severity": "warning",
                "message": f"Duplicate line: '{event.plaintext[:50]}' at {event.start}ms-{event.end}ms",
                "line": idx + 1,
                "auto_fixable": True,
                "fix": "Remove duplicate event",
            })
        else:
            seen.add(key)
    return issues


def check_timing_overlaps(subs) -> list:
    """Detect overlapping events within the same style and layer.

    Groups events by (style, layer), sorts by start time, and checks
    if current event starts before previous event ends.
    """
    issues = []
    groups = {}
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.style, getattr(event, "layer", 0))
        if key not in groups:
            groups[key] = []
        groups[key].append((idx, event))

    for group_key, events in groups.items():
        sorted_events = sorted(events, key=lambda x: x[1].start)
        for i in range(1, len(sorted_events)):
            prev_idx, prev = sorted_events[i - 1]
            curr_idx, curr = sorted_events[i]
            if curr.start < prev.end:
                overlap_ms = prev.end - curr.start
                severity = "error" if overlap_ms >= 500 else "warning"
                issues.append({
                    "check": "timing_overlaps",
                    "severity": severity,
                    "message": f"Overlap of {overlap_ms}ms between events {prev_idx + 1} and {curr_idx + 1} (style: {group_key[0]})",
                    "line": curr_idx + 1,
                    "auto_fixable": True,
                    "fix": "Trim previous event end to current event start",
                })
    return issues


def check_encoding_issues(subs, raw_bytes=None) -> list:
    """Detect encoding issues: BOM presence and non-UTF8 content.

    Args:
        subs: pysubs2.SSAFile (unused but kept for consistent signature).
        raw_bytes: Raw file bytes for encoding detection.
    """
    issues = []
    if raw_bytes is None:
        return issues

    # Check for BOM
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        issues.append({
            "check": "encoding_issues",
            "severity": "warning",
            "message": "File contains UTF-8 BOM (byte order mark)",
            "line": None,
            "auto_fixable": False,
            "fix": None,
        })
    elif raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        issues.append({
            "check": "encoding_issues",
            "severity": "warning",
            "message": "File contains UTF-16 BOM -- may cause compatibility issues",
            "line": None,
            "auto_fixable": False,
            "fix": None,
        })

    # Detect non-UTF8 via chardet
    try:
        import chardet
        det = chardet.detect(raw_bytes[:8192])
        encoding = (det.get("encoding") or "utf-8").lower()
        confidence = det.get("confidence", 0)
        if encoding not in ("utf-8", "ascii") and confidence > 0.7:
            issues.append({
                "check": "encoding_issues",
                "severity": "warning",
                "message": f"File encoding detected as {encoding} (confidence: {confidence:.0%}) -- not UTF-8",
                "line": None,
                "auto_fixable": False,
                "fix": None,
            })
    except ImportError:
        # chardet not available -- try decoding as UTF-8
        try:
            raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            issues.append({
                "check": "encoding_issues",
                "severity": "warning",
                "message": "File contains non-UTF8 bytes (chardet not installed for detailed detection)",
                "line": None,
                "auto_fixable": False,
                "fix": None,
            })

    return issues


def check_missing_styles(subs) -> list:
    """Detect events referencing styles not defined in the file.

    Only applies to ASS/SSA format (skipped for SRT).
    """
    issues = []
    if not hasattr(subs, "styles") or not subs.styles:
        return issues

    defined_styles = set(subs.styles.keys())
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.style not in defined_styles:
            issues.append({
                "check": "missing_styles",
                "severity": "error",
                "message": f"Event references undefined style '{event.style}'",
                "line": idx + 1,
                "auto_fixable": True,
                "fix": "Change style reference to 'Default'",
            })
    return issues


def check_empty_events(subs) -> list:
    """Detect events with empty plaintext content."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if not event.plaintext.strip():
            issues.append({
                "check": "empty_events",
                "severity": "warning",
                "message": f"Empty event at {event.start}ms-{event.end}ms",
                "line": idx + 1,
                "auto_fixable": True,
                "fix": "Remove empty event",
            })
    return issues


def check_excessive_duration(subs) -> list:
    """Detect events with duration exceeding 10 seconds."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        duration_ms = event.end - event.start
        if duration_ms > 10000:
            issues.append({
                "check": "excessive_duration",
                "severity": "info",
                "message": f"Event duration {duration_ms / 1000:.1f}s exceeds 10s threshold",
                "line": idx + 1,
                "auto_fixable": False,
                "fix": None,
            })
    return issues


def check_negative_timing(subs) -> list:
    """Detect events where end time is before start time."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.end < event.start:
            issues.append({
                "check": "negative_timing",
                "severity": "error",
                "message": f"Negative timing: end ({event.end}ms) < start ({event.start}ms)",
                "line": idx + 1,
                "auto_fixable": True,
                "fix": "Swap start and end times",
            })
    return issues


def check_zero_duration(subs) -> list:
    """Detect events where start equals end (zero duration)."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.start == event.end:
            issues.append({
                "check": "zero_duration",
                "severity": "warning",
                "message": f"Zero duration event at {event.start}ms",
                "line": idx + 1,
                "auto_fixable": True,
                "fix": "Remove zero-duration event",
            })
    return issues


def check_line_too_long(subs) -> list:
    """Detect events with any line exceeding 80 characters."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        for line in event.plaintext.split("\n"):
            if len(line) > 80:
                issues.append({
                    "check": "line_too_long",
                    "severity": "info",
                    "message": f"Line exceeds 80 chars ({len(line)} chars): '{line[:40]}...'",
                    "line": idx + 1,
                    "auto_fixable": False,
                    "fix": None,
                })
                break  # One issue per event is enough
    return issues


def check_missing_newlines(subs) -> list:
    """Detect ASS dialogue text with >80 chars and no line break.

    Only applies to ASS/SSA format (skipped for SRT).
    """
    issues = []
    # Only meaningful for ASS where \N is the line break
    if not hasattr(subs, "styles") or not subs.styles:
        return issues

    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        # Check if the raw text has no \N break and plaintext is >80 chars
        if "\\N" not in event.text and len(event.plaintext) > 80:
            issues.append({
                "check": "missing_newlines",
                "severity": "info",
                "message": f"Long dialogue ({len(event.plaintext)} chars) with no line break",
                "line": idx + 1,
                "auto_fixable": False,
                "fix": None,
            })
    return issues


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_duplicate_lines,
    check_timing_overlaps,
    # check_encoding_issues handled separately (needs raw_bytes)
    check_missing_styles,
    check_empty_events,
    check_excessive_duration,
    check_negative_timing,
    check_zero_duration,
    check_line_too_long,
    check_missing_newlines,
]


def _calculate_score(issues: list) -> int:
    """Calculate quality score: 100 minus penalties, clamped to 0.

    Penalty: 10 per error, 3 per warning, 1 per info.
    """
    penalty = 0
    for issue in issues:
        sev = issue.get("severity", "info")
        if sev == "error":
            penalty += 10
        elif sev == "warning":
            penalty += 3
        elif sev == "info":
            penalty += 1
    return max(0, 100 - penalty)


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
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # Parse subtitle
    try:
        subs = pysubs2.load(file_path)
    except Exception as e:
        logger.error("Cannot parse subtitle %s: %s", file_path, e)
        return {
            "file_path": file_path,
            "checks_run": 0,
            "issues": [{
                "check": "parse_error",
                "severity": "error",
                "message": f"Failed to parse subtitle file: {e}",
                "line": None,
                "auto_fixable": False,
                "fix": None,
            }],
            "score": 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
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
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Auto-fix Functions
# ---------------------------------------------------------------------------


def fix_duplicate_lines(subs) -> int:
    """Remove exact duplicate events. Returns count removed."""
    seen = set()
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.start, event.end, event.text, event.style)
        if key in seen:
            to_remove.append(idx)
        else:
            seen.add(key)
    # Remove in reverse order to preserve indices
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


def fix_timing_overlaps(subs) -> int:
    """Trim previous event end to current event start for same-style overlaps.

    Returns count of overlaps fixed.
    """
    groups = {}
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        key = (event.style, getattr(event, "layer", 0))
        if key not in groups:
            groups[key] = []
        groups[key].append((idx, event))

    fixed = 0
    for group_key, events in groups.items():
        sorted_events = sorted(events, key=lambda x: x[1].start)
        for i in range(1, len(sorted_events)):
            prev_idx, prev = sorted_events[i - 1]
            curr_idx, curr = sorted_events[i]
            if curr.start < prev.end:
                prev.end = curr.start
                fixed += 1
    return fixed


def fix_missing_styles(subs) -> int:
    """Change undefined style references to 'Default'. Returns count fixed."""
    if not hasattr(subs, "styles") or not subs.styles:
        return 0

    defined_styles = set(subs.styles.keys())
    fixed = 0
    for event in subs.events:
        if event.is_comment:
            continue
        if event.style not in defined_styles:
            event.style = "Default"
            fixed += 1
    return fixed


def fix_empty_events(subs) -> int:
    """Remove events with empty plaintext. Returns count removed."""
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if not event.plaintext.strip():
            to_remove.append(idx)
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


def fix_negative_timing(subs) -> int:
    """Swap start and end when end < start. Returns count fixed."""
    fixed = 0
    for event in subs.events:
        if event.is_comment:
            continue
        if event.end < event.start:
            event.start, event.end = event.end, event.start
            fixed += 1
    return fixed


def fix_zero_duration(subs) -> int:
    """Remove zero-duration events. Returns count removed."""
    to_remove = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.start == event.end:
            to_remove.append(idx)
    for idx in reversed(to_remove):
        del subs.events[idx]
    return len(to_remove)


# Map check names to fix functions
FIX_MAP = {
    "duplicate_lines": fix_duplicate_lines,
    "timing_overlaps": fix_timing_overlaps,
    "missing_styles": fix_missing_styles,
    "empty_events": fix_empty_events,
    "negative_timing": fix_negative_timing,
    "zero_duration": fix_zero_duration,
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
