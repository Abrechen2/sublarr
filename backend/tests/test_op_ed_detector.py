# backend/tests/test_op_ed_detector.py
"""Tests for op_ed_detector — OP/ED region detection."""

import pytest

# ─── Helpers ─────────────────────────────────────────────────────────────────

_ASS_HEADER = (
    "[Script Info]\nScriptType: v4.00+\n\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
    "Style: Opening,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n"
    "Style: Ending,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
    "0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1\n\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)


def _ms_to_ass(ms: int) -> str:
    """Convert milliseconds to ASS timestamp h:mm:ss.cc."""
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1_000
    cs = (ms % 1_000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _make_ass_events(events: list[tuple[int, int, str]]) -> str:
    """Build ASS content from list of (start_ms, end_ms, style) tuples."""
    lines = []
    for i, (start, end, style) in enumerate(events):
        lines.append(f"Dialogue: 0,{_ms_to_ass(start)},{_ms_to_ass(end)},{style},,0,0,0,,Line {i}")
    return _ASS_HEADER + "\n".join(lines) + "\n"


def _make_srt_events(events: list[tuple[int, int]]) -> str:
    """Build SRT content from list of (start_ms, end_ms) tuples."""

    def ms_to_srt(ms: int) -> str:
        h = ms // 3_600_000
        ms %= 3_600_000
        m = ms // 60_000
        ms %= 60_000
        s = ms // 1_000
        millis = ms % 1_000
        return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"

    blocks = []
    for i, (start, end) in enumerate(events, 1):
        blocks.append(f"{i}\n{ms_to_srt(start)} --> {ms_to_srt(end)}\nLine {i}")
    return "\n\n".join(blocks)


# ─── Pass 1: Style name detection ─────────────────────────────────────────────


def test_pass1_opening_style_detected_as_op():
    """ASS events with style 'Opening' are detected as OP."""
    from op_ed_detector import detect_op_ed_from_ass

    events = [(5_000, 10_000, "Opening")] * 5 + [(600_000, 605_000, "Default")] * 3
    result = detect_op_ed_from_ass(_make_ass_events(events))
    types = {r["type"] for r in result}
    assert "OP" in types
    op = next(r for r in result if r["type"] == "OP")
    assert op["method"] == "style"
    assert op["event_count"] == 5


def test_pass1_ed_theme_style_detected_as_ed():
    """ASS events with style 'ED Theme' are detected as ED."""
    from op_ed_detector import detect_op_ed_from_ass

    # Use longer file so windows don't overlap
    events = [(1_000, 2_000, "Default")] * 3 + [(1_380_000, 1_385_000, "ED Theme")] * 6
    result = detect_op_ed_from_ass(_make_ass_events(events))
    types = {r["type"] for r in result}
    assert "ED" in types
    ed = next(r for r in result if r["type"] == "ED")
    assert ed["method"] == "style"


def test_pass1_per_type_gating_op_style_ed_duration():
    """Pass 1 finds OP via style; Pass 2 still runs for ED if no ED style exists."""
    from op_ed_detector import detect_op_ed_from_ass

    # OP has 'Opening' style; ED has Default style but is in last 300s and ~110s long
    # File total: ~1700s so windows don't overlap
    op_events = [(5_000, 10_000, "Opening")] * 8
    dialogue = [(300_000, 301_000, "Default")] * 3
    # ED cluster: starts at 1390s, ends at 1500s = 110s duration, within last 300s of 1700s file
    ed_events = [(1_390_000 + i * 5_000, 1_392_000 + i * 5_000, "Default") for i in range(5)]
    all_events = op_events + dialogue + ed_events
    result = detect_op_ed_from_ass(_make_ass_events(all_events))
    types = {r["type"] for r in result}
    assert "OP" in types
    assert "ED" in types
    op = next(r for r in result if r["type"] == "OP")
    ed = next(r for r in result if r["type"] == "ED")
    assert op["method"] == "style"
    assert ed["method"] == "duration"


def test_pass1_skips_pass2_for_found_type():
    """If Pass 1 finds both OP and ED, Pass 2 is not used for either."""
    from op_ed_detector import detect_op_ed_from_ass

    events = (
        [(5_000, 10_000, "Opening")] * 5
        + [(300_000, 301_000, "Default")] * 3
        + [(1_380_000, 1_385_000, "Ending")] * 5
    )
    result = detect_op_ed_from_ass(_make_ass_events(events))
    for r in result:
        assert r["method"] == "style"


# ─── Pass 2: Duration heuristic ───────────────────────────────────────────────


def test_pass2_op_cluster_in_first_window_detected():
    """OP cluster starting within op_window_sec with valid duration is detected."""
    from op_ed_detector import detect_op_ed_from_ass

    # OP: starts at 5s, each event 8s, 12 events → ~96s duration, within first 300s
    # File total: ~1700s (windows don't overlap)
    op_events = [(5_000 + i * 8_000, 12_000 + i * 8_000, "Default") for i in range(12)]
    dialogue = [(300_000 + i * 2_000, 302_000 + i * 2_000, "Default") for i in range(5)]
    ed_events = [(1_390_000 + i * 5_000, 1_395_000 + i * 5_000, "Default") for i in range(5)]
    result = detect_op_ed_from_ass(_make_ass_events(op_events + dialogue + ed_events))
    types = {r["type"] for r in result}
    assert "OP" in types
    op = next(r for r in result if r["type"] == "OP")
    assert op["method"] == "duration"


def test_pass2_ed_cluster_in_last_window_detected():
    """ED cluster starting within last op_window_sec with valid duration is detected."""
    from op_ed_detector import detect_op_ed_from_ass

    dialogue = [(300_000 + i * 2_000, 302_000 + i * 2_000, "Default") for i in range(5)]
    # ED: starts at 1390s, each event 10s, 12 events → ~120s, within last 300s of 1700s file
    ed_events = [(1_390_000 + i * 10_000, 1_400_000 + i * 10_000, "Default") for i in range(12)]
    result = detect_op_ed_from_ass(_make_ass_events(dialogue + ed_events))
    types = {r["type"] for r in result}
    assert "ED" in types


def test_pass2_cluster_too_short_not_op():
    """Cluster shorter than 60s is NOT detected as OP."""
    from op_ed_detector import detect_op_ed_from_ass

    # Only 5 events with 5s each = 25s duration → below 60s minimum
    op_events = [(5_000 + i * 5_000, 10_000 + i * 5_000, "Default") for i in range(5)]
    dialogue = [(600_000 + i * 2_000, 602_000 + i * 2_000, "Default") for i in range(5)]
    result = detect_op_ed_from_ass(_make_ass_events(op_events + dialogue))
    assert not any(r["type"] == "OP" for r in result)


def test_pass2_cluster_outside_window_not_detected():
    """Cluster that starts after op_window_sec is not detected."""
    from op_ed_detector import detect_op_ed_from_ass

    # Cluster starts at 400s (> 300s window), lasts 90s — outside OP window
    # File total: ~2000s
    late_events = [(400_000 + i * 8_000, 408_000 + i * 8_000, "Default") for i in range(12)]
    dialogue = [(1_000_000 + i * 2_000, 1_002_000 + i * 2_000, "Default") for i in range(5)]
    result = detect_op_ed_from_ass(_make_ass_events(late_events + dialogue))
    assert not any(r["type"] == "OP" for r in result)


def test_pass2_cluster_fewer_than_3_events_not_detected():
    """Cluster with fewer than 3 events is not detected."""
    from op_ed_detector import detect_op_ed_from_ass

    # Only 2 events — below minimum cluster size
    op_events = [(5_000, 50_000, "Default"), (55_000, 90_000, "Default")]
    dialogue = [(600_000, 602_000, "Default")] * 5
    result = detect_op_ed_from_ass(_make_ass_events(op_events + dialogue))
    assert not any(r["type"] == "OP" for r in result)


def test_pass2_op_window_sec_setting_respected(monkeypatch):
    """Custom SUBLARR_OP_WINDOW_SEC changes the window boundary."""
    monkeypatch.setenv("SUBLARR_OP_WINDOW_SEC", "60")

    from op_ed_detector import detect_op_ed_from_ass

    # OP cluster starts at 90s — outside a 60s window but inside a 300s window
    op_events = [(90_000 + i * 8_000, 98_000 + i * 8_000, "Default") for i in range(12)]
    dialogue = [(1_000_000 + i * 2_000, 1_002_000 + i * 2_000, "Default") for i in range(5)]
    result = detect_op_ed_from_ass(_make_ass_events(op_events + dialogue))
    # With 60s window: cluster starts at 90s > 60s → not detected
    assert not any(r["type"] == "OP" for r in result)


def test_pass2_overlapping_windows_returns_empty():
    """File shorter than 2 * op_window_sec returns [] for duration-detected regions."""
    from op_ed_detector import detect_op_ed_from_ass

    # File total ~200s, op_window_sec default 300s → windows overlap (200 < 600)
    events = [(i * 5_000, (i + 1) * 5_000, "Default") for i in range(10)]
    result = detect_op_ed_from_ass(_make_ass_events(events))
    # No style-based detection either, so result must be []
    assert result == []


def test_file_with_only_op_returns_op_region():
    """File with only OP events returns a list with just the OP region."""
    from op_ed_detector import detect_op_ed_from_ass

    # OP cluster only
    op_events = [(5_000, 10_000, "Opening")] * 6
    dialogue = [(800_000, 801_000, "Default")] * 3
    result = detect_op_ed_from_ass(_make_ass_events(op_events + dialogue))
    assert len(result) == 1
    assert result[0]["type"] == "OP"


def test_empty_file_returns_empty_list():
    """Empty ASS file returns []."""
    from op_ed_detector import detect_op_ed_from_ass

    result = detect_op_ed_from_ass(_make_ass_events([]))
    assert result == []


def test_ssa_processed_same_as_ass():
    """SSA files (same format as ASS) are handled identically."""
    from op_ed_detector import detect_op_ed_from_ass

    # SSA content is identical in structure to ASS — pysubs2 handles both
    events = [(5_000, 10_000, "Opening")] * 5 + [(800_000, 801_000, "Default")] * 3
    content = _make_ass_events(events)
    result = detect_op_ed_from_ass(content)
    assert any(r["type"] == "OP" for r in result)


def test_srt_op_cluster_detected_via_duration():
    """SRT file with OP cluster in first window is detected via Pass 2."""
    from op_ed_detector import detect_op_ed_from_srt

    # OP: 12 events starting at 5s, each 8s → ~96s duration in first 300s
    # File total: ~1700s
    op_events = [(5_000 + i * 8_000, 12_000 + i * 8_000) for i in range(12)]
    dialogue = [(300_000, 302_000)] * 3
    ed_events = [(1_390_000 + i * 10_000, 1_400_000 + i * 10_000) for i in range(12)]
    result = detect_op_ed_from_srt(_make_srt_events(op_events + dialogue + ed_events))
    assert any(r["type"] == "OP" and r["method"] == "duration" for r in result)
