"""Subtitle health-check detection functions.

Extracted from health_checker.py. Each check_* function inspects a
pysubs2.SSAFile and returns a list of issue dicts — pure functions with
no side effects. ALL_CHECKS groups the fixed-signature checks used by
the orchestrator; encoding_issues is called separately because it needs
raw bytes.
"""


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
            issues.append(
                {
                    "check": "duplicate_lines",
                    "severity": "warning",
                    "message": f"Duplicate line: '{event.plaintext[:50]}' at {event.start}ms-{event.end}ms",
                    "line": idx + 1,
                    "auto_fixable": True,
                    "fix": "Remove duplicate event",
                }
            )
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
                issues.append(
                    {
                        "check": "timing_overlaps",
                        "severity": severity,
                        "message": f"Overlap of {overlap_ms}ms between events {prev_idx + 1} and {curr_idx + 1} (style: {group_key[0]})",
                        "line": curr_idx + 1,
                        "auto_fixable": True,
                        "fix": "Trim previous event end to current event start",
                    }
                )
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
        issues.append(
            {
                "check": "encoding_issues",
                "severity": "warning",
                "message": "File contains UTF-8 BOM (byte order mark)",
                "line": None,
                "auto_fixable": False,
                "fix": None,
            }
        )
    elif raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        issues.append(
            {
                "check": "encoding_issues",
                "severity": "warning",
                "message": "File contains UTF-16 BOM -- may cause compatibility issues",
                "line": None,
                "auto_fixable": False,
                "fix": None,
            }
        )

    # Detect non-UTF8 via chardet
    try:
        import chardet

        det = chardet.detect(raw_bytes[:8192])
        encoding = (det.get("encoding") or "utf-8").lower()
        confidence = det.get("confidence", 0)
        if encoding not in ("utf-8", "ascii") and confidence > 0.7:
            issues.append(
                {
                    "check": "encoding_issues",
                    "severity": "warning",
                    "message": f"File encoding detected as {encoding} (confidence: {confidence:.0%}) -- not UTF-8",
                    "line": None,
                    "auto_fixable": False,
                    "fix": None,
                }
            )
    except ImportError:
        # chardet not available -- try decoding as UTF-8
        try:
            raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(
                {
                    "check": "encoding_issues",
                    "severity": "warning",
                    "message": "File contains non-UTF8 bytes (chardet not installed for detailed detection)",
                    "line": None,
                    "auto_fixable": False,
                    "fix": None,
                }
            )

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
            issues.append(
                {
                    "check": "missing_styles",
                    "severity": "error",
                    "message": f"Event references undefined style '{event.style}'",
                    "line": idx + 1,
                    "auto_fixable": True,
                    "fix": "Change style reference to 'Default'",
                }
            )
    return issues


def check_empty_events(subs) -> list:
    """Detect events with empty plaintext content."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if not event.plaintext.strip():
            issues.append(
                {
                    "check": "empty_events",
                    "severity": "warning",
                    "message": f"Empty event at {event.start}ms-{event.end}ms",
                    "line": idx + 1,
                    "auto_fixable": True,
                    "fix": "Remove empty event",
                }
            )
    return issues


def check_excessive_duration(subs) -> list:
    """Detect events with duration exceeding 10 seconds."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        duration_ms = event.end - event.start
        if duration_ms > 10000:
            issues.append(
                {
                    "check": "excessive_duration",
                    "severity": "info",
                    "message": f"Event duration {duration_ms / 1000:.1f}s exceeds 10s threshold",
                    "line": idx + 1,
                    "auto_fixable": False,
                    "fix": None,
                }
            )
    return issues


def check_negative_timing(subs) -> list:
    """Detect events where end time is before start time."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.end < event.start:
            issues.append(
                {
                    "check": "negative_timing",
                    "severity": "error",
                    "message": f"Negative timing: end ({event.end}ms) < start ({event.start}ms)",
                    "line": idx + 1,
                    "auto_fixable": True,
                    "fix": "Swap start and end times",
                }
            )
    return issues


def check_zero_duration(subs) -> list:
    """Detect events where start equals end (zero duration)."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        if event.start == event.end:
            issues.append(
                {
                    "check": "zero_duration",
                    "severity": "warning",
                    "message": f"Zero duration event at {event.start}ms",
                    "line": idx + 1,
                    "auto_fixable": True,
                    "fix": "Remove zero-duration event",
                }
            )
    return issues


def check_line_too_long(subs) -> list:
    """Detect events with any line exceeding 80 characters."""
    issues = []
    for idx, event in enumerate(subs.events):
        if event.is_comment:
            continue
        for line in event.plaintext.split("\n"):
            if len(line) > 80:
                issues.append(
                    {
                        "check": "line_too_long",
                        "severity": "info",
                        "message": f"Line exceeds 80 chars ({len(line)} chars): '{line[:40]}...'",
                        "line": idx + 1,
                        "auto_fixable": False,
                        "fix": None,
                    }
                )
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
            issues.append(
                {
                    "check": "missing_newlines",
                    "severity": "info",
                    "message": f"Long dialogue ({len(event.plaintext)} chars) with no line break",
                    "line": idx + 1,
                    "auto_fixable": False,
                    "fix": None,
                }
            )
    return issues


# ---------------------------------------------------------------------------
# Orchestrator helpers
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
