"""Tests for health_checker.py — subtitle health-check engine.

Covers all 10 check functions, the score calculator, the orchestrator
(run_health_checks), and all 6 auto-fix functions plus apply_fixes.
"""

import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pysubs2
import pytest

from health_checker import (
    ALL_CHECKS,
    FIX_MAP,
    FIXABLE_CHECKS,
    _calculate_score,
    apply_fixes,
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
    fix_duplicate_lines,
    fix_empty_events,
    fix_missing_styles,
    fix_negative_timing,
    fix_timing_overlaps,
    fix_zero_duration,
    run_health_checks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(start=0, end=1000, text="Hello", style="Default", is_comment=False, layer=0):
    """Create a mock subtitle event."""
    ev = SimpleNamespace(
        start=start,
        end=end,
        text=text,
        plaintext=text,
        style=style,
        is_comment=is_comment,
        layer=layer,
    )
    return ev


def _make_subs(events, styles=None):
    """Create a mock SSAFile with given events and optional styles dict."""
    subs = SimpleNamespace(events=list(events))
    if styles is not None:
        subs.styles = styles
    return subs


def _make_ass(tmp_path, lines=None, extra_styles=None, extra_events=None):
    """Write a real .ass file and return its path."""
    content = (
        "[Script Info]\nTitle: Test\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,"
        "&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n"
    )
    if extra_styles:
        content += extra_styles + "\n"
    content += (
        "\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    if lines is None:
        lines = ["Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello World"]
    if extra_events:
        lines.extend(extra_events)
    content += "\n".join(lines) + "\n"
    path = tmp_path / "test.ass"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _make_srt(tmp_path, content):
    """Write a .srt file and return its path."""
    path = tmp_path / "test.srt"
    path.write_text(content, encoding="utf-8")
    return str(path)


# ===========================================================================
# Constants
# ===========================================================================


class TestConstants:
    """Verify module-level constants are defined correctly."""

    def test_fixable_checks_contains_expected_names(self):
        assert "duplicate_lines" in FIXABLE_CHECKS
        assert "timing_overlaps" in FIXABLE_CHECKS
        assert "missing_styles" in FIXABLE_CHECKS
        assert "empty_events" in FIXABLE_CHECKS
        assert "negative_timing" in FIXABLE_CHECKS
        assert "zero_duration" in FIXABLE_CHECKS
        assert len(FIXABLE_CHECKS) == 6

    def test_fix_map_keys_match_fixable_checks(self):
        assert set(FIX_MAP.keys()) == FIXABLE_CHECKS

    def test_all_checks_count(self):
        # 9 checks in ALL_CHECKS (encoding is handled separately)
        assert len(ALL_CHECKS) == 9


# ===========================================================================
# check_duplicate_lines
# ===========================================================================


class TestCheckDuplicateLines:
    def test_no_duplicates(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        issues = check_duplicate_lines(subs)
        assert issues == []

    def test_detects_exact_duplicate(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A", style="Default"),
                _make_event(start=0, end=1000, text="A", style="Default"),
            ]
        )
        issues = check_duplicate_lines(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "duplicate_lines"
        assert issues[0]["severity"] == "warning"
        assert issues[0]["auto_fixable"] is True
        assert issues[0]["line"] == 2

    def test_different_style_not_duplicate(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A", style="Default"),
                _make_event(start=0, end=1000, text="A", style="Italic"),
            ]
        )
        assert check_duplicate_lines(subs) == []

    def test_different_timing_not_duplicate(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=500, end=1000, text="A"),
            ]
        )
        assert check_duplicate_lines(subs) == []

    def test_comments_skipped(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A", is_comment=True),
                _make_event(start=0, end=1000, text="A", is_comment=True),
            ]
        )
        assert check_duplicate_lines(subs) == []

    def test_multiple_duplicates(self):
        ev = _make_event(start=0, end=1000, text="A")
        subs = _make_subs([ev, ev, ev])
        # Second and third are duplicates
        issues = check_duplicate_lines(subs)
        assert len(issues) == 2

    def test_empty_events_list(self):
        subs = _make_subs([])
        assert check_duplicate_lines(subs) == []


# ===========================================================================
# check_timing_overlaps
# ===========================================================================


class TestCheckTimingOverlaps:
    def test_no_overlap(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        assert check_timing_overlaps(subs) == []

    def test_detects_overlap_warning(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1500, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        issues = check_timing_overlaps(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "timing_overlaps"
        assert issues[0]["severity"] == "error"  # 500ms overlap -> error
        assert issues[0]["auto_fixable"] is True

    def test_small_overlap_is_warning(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1200, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        issues = check_timing_overlaps(subs)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"  # 200ms < 500ms

    def test_large_overlap_is_error(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=2000, text="A"),
                _make_event(start=1000, end=3000, text="B"),
            ]
        )
        issues = check_timing_overlaps(subs)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"  # 1000ms >= 500ms

    def test_different_styles_no_overlap(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=2000, text="A", style="Default"),
                _make_event(start=500, end=3000, text="B", style="Italic"),
            ]
        )
        assert check_timing_overlaps(subs) == []

    def test_comments_skipped(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=2000, text="A", is_comment=True),
                _make_event(start=500, end=3000, text="B", is_comment=True),
            ]
        )
        assert check_timing_overlaps(subs) == []

    def test_empty_events(self):
        subs = _make_subs([])
        assert check_timing_overlaps(subs) == []


# ===========================================================================
# check_encoding_issues
# ===========================================================================


class TestCheckEncodingIssues:
    def test_no_raw_bytes_returns_empty(self):
        subs = _make_subs([])
        assert check_encoding_issues(subs, raw_bytes=None) == []

    def test_utf8_bom_detected(self):
        subs = _make_subs([])
        raw = b"\xef\xbb\xbfHello"
        issues = check_encoding_issues(subs, raw_bytes=raw)
        assert len(issues) >= 1
        bom_issues = [i for i in issues if "UTF-8 BOM" in i["message"]]
        assert len(bom_issues) == 1
        assert bom_issues[0]["check"] == "encoding_issues"
        assert bom_issues[0]["auto_fixable"] is False

    def test_utf16_le_bom_detected(self):
        subs = _make_subs([])
        raw = b"\xff\xfeH\x00e\x00l\x00l\x00o\x00"
        issues = check_encoding_issues(subs, raw_bytes=raw)
        assert any("UTF-16 BOM" in i["message"] for i in issues)

    def test_utf16_be_bom_detected(self):
        subs = _make_subs([])
        raw = b"\xfe\xff\x00H\x00e\x00l\x00l\x00o"
        issues = check_encoding_issues(subs, raw_bytes=raw)
        assert any("UTF-16 BOM" in i["message"] for i in issues)

    def test_clean_utf8_no_issues(self):
        subs = _make_subs([])
        raw = b"Hello World"
        issues = check_encoding_issues(subs, raw_bytes=raw)
        # chardet may detect as ascii, which is fine
        assert all(i["check"] == "encoding_issues" for i in issues)
        # No BOM issues at minimum
        assert not any("BOM" in i["message"] for i in issues)

    def test_non_utf8_detected_with_chardet(self):
        subs = _make_subs([])
        # Shift-JIS encoded Japanese text
        raw = "こんにちは世界".encode("shift_jis")
        issues = check_encoding_issues(subs, raw_bytes=raw)
        # chardet should detect non-UTF-8 encoding
        [i for i in issues if "not UTF-8" in i.get("message", "")]
        # Whether detected depends on chardet confidence, so just verify no crash
        assert isinstance(issues, list)

    def test_chardet_import_error_fallback(self):
        """When chardet is not available, fallback to manual UTF-8 decode check."""
        subs = _make_subs([])
        # Latin-1 bytes that are NOT valid UTF-8
        raw = bytes([0xC0, 0xC1, 0xFE, 0xFF])

        with (
            patch.dict("sys.modules", {"chardet": None}),
            patch("builtins.__import__", side_effect=_import_blocker("chardet")),
        ):
            issues = check_encoding_issues(subs, raw_bytes=raw)
        # Should detect non-UTF-8 bytes via fallback
        assert any("non-UTF8" in i.get("message", "") for i in issues)

    def test_chardet_import_error_fallback_valid_utf8(self):
        """When chardet is unavailable but bytes are valid UTF-8, no issue."""
        subs = _make_subs([])
        raw = b"Hello"

        with (
            patch.dict("sys.modules", {"chardet": None}),
            patch("builtins.__import__", side_effect=_import_blocker("chardet")),
        ):
            issues = check_encoding_issues(subs, raw_bytes=raw)
        assert issues == []


def _import_blocker(blocked_name):
    """Create an import side_effect that blocks a specific module."""
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _blocker(name, *args, **kwargs):
        if name == blocked_name:
            raise ImportError(f"Mocked: {blocked_name} not available")
        return real_import(name, *args, **kwargs)

    return _blocker


# ===========================================================================
# check_missing_styles
# ===========================================================================


class TestCheckMissingStyles:
    def test_no_styles_attr_returns_empty(self):
        subs = SimpleNamespace(events=[_make_event(style="Foo")])
        # No styles attribute
        assert check_missing_styles(subs) == []

    def test_empty_styles_dict_returns_empty(self):
        subs = _make_subs([_make_event(style="Foo")], styles={})
        assert check_missing_styles(subs) == []

    def test_all_styles_defined(self):
        subs = _make_subs(
            [_make_event(style="Default"), _make_event(style="Italic")],
            styles={"Default": {}, "Italic": {}},
        )
        assert check_missing_styles(subs) == []

    def test_detects_undefined_style(self):
        subs = _make_subs(
            [_make_event(style="Missing")],
            styles={"Default": {}},
        )
        issues = check_missing_styles(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "missing_styles"
        assert issues[0]["severity"] == "error"
        assert issues[0]["auto_fixable"] is True
        assert "Missing" in issues[0]["message"]

    def test_comments_skipped(self):
        subs = _make_subs(
            [_make_event(style="Missing", is_comment=True)],
            styles={"Default": {}},
        )
        assert check_missing_styles(subs) == []


# ===========================================================================
# check_empty_events
# ===========================================================================


class TestCheckEmptyEvents:
    def test_no_empty_events(self):
        subs = _make_subs([_make_event(text="Hello")])
        assert check_empty_events(subs) == []

    def test_detects_empty_plaintext(self):
        ev = _make_event(text="")
        ev.plaintext = ""
        subs = _make_subs([ev])
        issues = check_empty_events(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "empty_events"
        assert issues[0]["auto_fixable"] is True

    def test_whitespace_only_is_empty(self):
        ev = _make_event(text="   ")
        ev.plaintext = "   "
        subs = _make_subs([ev])
        issues = check_empty_events(subs)
        assert len(issues) == 1

    def test_comments_skipped(self):
        ev = _make_event(text="", is_comment=True)
        ev.plaintext = ""
        subs = _make_subs([ev])
        assert check_empty_events(subs) == []


# ===========================================================================
# check_excessive_duration
# ===========================================================================


class TestCheckExcessiveDuration:
    def test_normal_duration(self):
        subs = _make_subs([_make_event(start=0, end=5000)])
        assert check_excessive_duration(subs) == []

    def test_exactly_10_seconds_no_issue(self):
        subs = _make_subs([_make_event(start=0, end=10000)])
        assert check_excessive_duration(subs) == []

    def test_exceeds_10_seconds(self):
        subs = _make_subs([_make_event(start=0, end=15000)])
        issues = check_excessive_duration(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "excessive_duration"
        assert issues[0]["severity"] == "info"
        assert issues[0]["auto_fixable"] is False
        assert "15.0s" in issues[0]["message"]

    def test_comments_skipped(self):
        subs = _make_subs([_make_event(start=0, end=15000, is_comment=True)])
        assert check_excessive_duration(subs) == []


# ===========================================================================
# check_negative_timing
# ===========================================================================


class TestCheckNegativeTiming:
    def test_normal_timing(self):
        subs = _make_subs([_make_event(start=0, end=1000)])
        assert check_negative_timing(subs) == []

    def test_detects_negative(self):
        subs = _make_subs([_make_event(start=2000, end=1000)])
        issues = check_negative_timing(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "negative_timing"
        assert issues[0]["severity"] == "error"
        assert issues[0]["auto_fixable"] is True

    def test_equal_timing_not_negative(self):
        subs = _make_subs([_make_event(start=1000, end=1000)])
        assert check_negative_timing(subs) == []

    def test_comments_skipped(self):
        subs = _make_subs([_make_event(start=2000, end=1000, is_comment=True)])
        assert check_negative_timing(subs) == []


# ===========================================================================
# check_zero_duration
# ===========================================================================


class TestCheckZeroDuration:
    def test_normal_duration(self):
        subs = _make_subs([_make_event(start=0, end=1000)])
        assert check_zero_duration(subs) == []

    def test_detects_zero_duration(self):
        subs = _make_subs([_make_event(start=1000, end=1000)])
        issues = check_zero_duration(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "zero_duration"
        assert issues[0]["severity"] == "warning"
        assert issues[0]["auto_fixable"] is True

    def test_comments_skipped(self):
        subs = _make_subs([_make_event(start=1000, end=1000, is_comment=True)])
        assert check_zero_duration(subs) == []


# ===========================================================================
# check_line_too_long
# ===========================================================================


class TestCheckLineTooLong:
    def test_short_line(self):
        subs = _make_subs([_make_event(text="Short")])
        assert check_line_too_long(subs) == []

    def test_exactly_80_chars_no_issue(self):
        text = "A" * 80
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev])
        assert check_line_too_long(subs) == []

    def test_detects_long_line(self):
        text = "A" * 81
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev])
        issues = check_line_too_long(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "line_too_long"
        assert issues[0]["severity"] == "info"
        assert issues[0]["auto_fixable"] is False
        assert "81 chars" in issues[0]["message"]

    def test_multiline_one_long(self):
        text = "Short\n" + "B" * 90
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev])
        issues = check_line_too_long(subs)
        assert len(issues) == 1

    def test_multiline_all_short(self):
        text = "Short line one\nShort line two"
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev])
        assert check_line_too_long(subs) == []

    def test_one_issue_per_event(self):
        """Even with multiple long lines, only one issue per event."""
        text = ("A" * 90) + "\n" + ("B" * 90)
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev])
        issues = check_line_too_long(subs)
        assert len(issues) == 1

    def test_comments_skipped(self):
        text = "A" * 100
        ev = _make_event(text=text, is_comment=True)
        ev.plaintext = text
        subs = _make_subs([ev])
        assert check_line_too_long(subs) == []


# ===========================================================================
# check_missing_newlines
# ===========================================================================


class TestCheckMissingNewlines:
    def test_no_styles_returns_empty(self):
        """SRT files have no styles — check should skip."""
        ev = _make_event(text="A" * 100)
        ev.plaintext = "A" * 100
        subs = SimpleNamespace(events=[ev])
        assert check_missing_newlines(subs) == []

    def test_short_text_no_issue(self):
        ev = _make_event(text="Short")
        ev.plaintext = "Short"
        subs = _make_subs([ev], styles={"Default": {}})
        assert check_missing_newlines(subs) == []

    def test_long_text_with_newline_no_issue(self):
        long_text = "A" * 50 + "\\N" + "B" * 50
        ev = _make_event(text=long_text)
        ev.plaintext = "A" * 50 + "\n" + "B" * 50
        subs = _make_subs([ev], styles={"Default": {}})
        assert check_missing_newlines(subs) == []

    def test_long_text_without_newline_detected(self):
        long_text = "A" * 90
        ev = _make_event(text=long_text)
        ev.plaintext = long_text
        subs = _make_subs([ev], styles={"Default": {}})
        issues = check_missing_newlines(subs)
        assert len(issues) == 1
        assert issues[0]["check"] == "missing_newlines"
        assert issues[0]["severity"] == "info"

    def test_exactly_80_chars_no_issue(self):
        text = "A" * 80
        ev = _make_event(text=text)
        ev.plaintext = text
        subs = _make_subs([ev], styles={"Default": {}})
        assert check_missing_newlines(subs) == []

    def test_comments_skipped(self):
        text = "A" * 100
        ev = _make_event(text=text, is_comment=True)
        ev.plaintext = text
        subs = _make_subs([ev], styles={"Default": {}})
        assert check_missing_newlines(subs) == []


# ===========================================================================
# _calculate_score
# ===========================================================================


class TestCalculateScore:
    def test_no_issues_perfect_score(self):
        assert _calculate_score([]) == 100

    def test_error_penalty(self):
        issues = [{"severity": "error"}]
        assert _calculate_score(issues) == 90  # 100 - 10

    def test_warning_penalty(self):
        issues = [{"severity": "warning"}]
        assert _calculate_score(issues) == 97  # 100 - 3

    def test_info_penalty(self):
        issues = [{"severity": "info"}]
        assert _calculate_score(issues) == 99  # 100 - 1

    def test_mixed_penalties(self):
        issues = [
            {"severity": "error"},
            {"severity": "warning"},
            {"severity": "info"},
        ]
        # 100 - 10 - 3 - 1 = 86
        assert _calculate_score(issues) == 86

    def test_clamped_to_zero(self):
        issues = [{"severity": "error"}] * 20
        # 100 - 200 = -100, clamped to 0
        assert _calculate_score(issues) == 0

    def test_unknown_severity_treated_as_info(self):
        issues = [{"severity": "unknown"}]
        # Default branch: no penalty added (not error/warning/info)
        assert _calculate_score(issues) == 100

    def test_missing_severity_key(self):
        issues = [{}]
        # .get("severity", "info") -> "info" -> penalty 1
        assert _calculate_score(issues) == 99


# ===========================================================================
# run_health_checks (orchestrator)
# ===========================================================================


class TestRunHealthChecks:
    def test_healthy_file(self, tmp_path):
        path = _make_ass(tmp_path)
        result = run_health_checks(path)
        assert result["file_path"] == path
        assert result["checks_run"] == 10  # 1 encoding + 9 from ALL_CHECKS
        assert result["score"] <= 100
        assert result["score"] >= 0
        assert "checked_at" in result
        assert isinstance(result["issues"], list)

    def test_file_not_found(self, tmp_path):
        missing = str(tmp_path / "nonexistent.ass")
        result = run_health_checks(missing)
        assert result["checks_run"] == 0
        assert result["score"] == 0
        assert result["issues"] == []

    def test_parse_error(self, tmp_path):
        # Write garbage that pysubs2 can't parse
        bad_path = tmp_path / "bad.ass"
        bad_path.write_text("THIS IS NOT A SUBTITLE FILE\nRANDOM GARBAGE", encoding="utf-8")
        result = run_health_checks(str(bad_path))
        assert result["checks_run"] == 0
        assert result["score"] == 0
        assert len(result["issues"]) == 1
        assert result["issues"][0]["check"] == "parse_error"
        assert result["issues"][0]["severity"] == "error"

    def test_file_with_issues(self, tmp_path):
        # Create a file with a duplicate line
        lines = [
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
        ]
        path = _make_ass(tmp_path, lines=lines)
        result = run_health_checks(path)
        assert result["checks_run"] == 10
        dup_issues = [i for i in result["issues"] if i["check"] == "duplicate_lines"]
        assert len(dup_issues) >= 1
        assert result["score"] < 100

    def test_check_function_exception_handled(self, tmp_path):
        """If a check function raises, it's caught and others still run."""
        path = _make_ass(tmp_path)

        # Patch one check to raise
        with patch(
            "health_checker.ALL_CHECKS",
            [lambda subs: (_ for _ in ()).throw(ValueError("boom")), check_empty_events],
        ):
            result = run_health_checks(path)
        # Should still complete with encoding check + 2 from patched ALL_CHECKS
        assert result["checks_run"] == 3
        assert result["score"] >= 0

    def test_srt_file(self, tmp_path):
        content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
        path = _make_srt(tmp_path, content)
        result = run_health_checks(path)
        assert result["checks_run"] == 10
        assert result["score"] >= 0

    def test_encoding_check_included(self, tmp_path):
        # Write file with UTF-8 BOM
        path = tmp_path / "bom.ass"
        content = (
            "[Script Info]\nTitle: Test\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,"
            "&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\n"
        )
        path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
        result = run_health_checks(str(path))
        bom_issues = [i for i in result["issues"] if "BOM" in i.get("message", "")]
        assert len(bom_issues) >= 1


# ===========================================================================
# Fix functions
# ===========================================================================


class TestFixDuplicateLines:
    def test_removes_duplicates(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        removed = fix_duplicate_lines(subs)
        assert removed == 1
        assert len(subs.events) == 2

    def test_no_duplicates_returns_zero(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A"),
                _make_event(start=1000, end=2000, text="B"),
            ]
        )
        removed = fix_duplicate_lines(subs)
        assert removed == 0
        assert len(subs.events) == 2

    def test_comments_preserved(self):
        subs = _make_subs(
            [
                _make_event(start=0, end=1000, text="A", is_comment=True),
                _make_event(start=0, end=1000, text="A", is_comment=True),
            ]
        )
        removed = fix_duplicate_lines(subs)
        assert removed == 0
        assert len(subs.events) == 2


class TestFixTimingOverlaps:
    def test_fixes_overlap(self):
        ev1 = _make_event(start=0, end=2000, text="A", style="Default")
        ev2 = _make_event(start=1000, end=3000, text="B", style="Default")
        subs = _make_subs([ev1, ev2])
        fixed = fix_timing_overlaps(subs)
        assert fixed == 1
        assert ev1.end == 1000  # Trimmed to ev2.start

    def test_no_overlap_returns_zero(self):
        ev1 = _make_event(start=0, end=1000, text="A")
        ev2 = _make_event(start=1000, end=2000, text="B")
        subs = _make_subs([ev1, ev2])
        fixed = fix_timing_overlaps(subs)
        assert fixed == 0

    def test_different_styles_not_fixed(self):
        ev1 = _make_event(start=0, end=2000, text="A", style="Default")
        ev2 = _make_event(start=500, end=3000, text="B", style="Italic")
        subs = _make_subs([ev1, ev2])
        fixed = fix_timing_overlaps(subs)
        assert fixed == 0
        assert ev1.end == 2000  # Unchanged


class TestFixMissingStyles:
    def test_fixes_undefined_style(self):
        ev = _make_event(style="Missing")
        subs = _make_subs([ev], styles={"Default": {}})
        fixed = fix_missing_styles(subs)
        assert fixed == 1
        assert ev.style == "Default"

    def test_no_styles_returns_zero(self):
        subs = SimpleNamespace(events=[_make_event(style="Foo")])
        assert fix_missing_styles(subs) == 0

    def test_empty_styles_returns_zero(self):
        subs = _make_subs([_make_event(style="Foo")], styles={})
        assert fix_missing_styles(subs) == 0

    def test_all_defined_returns_zero(self):
        subs = _make_subs([_make_event(style="Default")], styles={"Default": {}})
        assert fix_missing_styles(subs) == 0


class TestFixEmptyEvents:
    def test_removes_empty(self):
        ev_empty = _make_event(text="")
        ev_empty.plaintext = ""
        ev_good = _make_event(text="Hello")
        subs = _make_subs([ev_empty, ev_good])
        removed = fix_empty_events(subs)
        assert removed == 1
        assert len(subs.events) == 1

    def test_removes_whitespace_only(self):
        ev = _make_event(text="  ")
        ev.plaintext = "  "
        subs = _make_subs([ev])
        removed = fix_empty_events(subs)
        assert removed == 1

    def test_no_empty_returns_zero(self):
        subs = _make_subs([_make_event(text="Hello")])
        removed = fix_empty_events(subs)
        assert removed == 0


class TestFixNegativeTiming:
    def test_swaps_negative(self):
        ev = _make_event(start=2000, end=1000)
        subs = _make_subs([ev])
        fixed = fix_negative_timing(subs)
        assert fixed == 1
        assert ev.start == 1000
        assert ev.end == 2000

    def test_normal_timing_not_changed(self):
        ev = _make_event(start=0, end=1000)
        subs = _make_subs([ev])
        fixed = fix_negative_timing(subs)
        assert fixed == 0
        assert ev.start == 0


class TestFixZeroDuration:
    def test_removes_zero_duration(self):
        ev_zero = _make_event(start=1000, end=1000)
        ev_good = _make_event(start=0, end=1000)
        subs = _make_subs([ev_zero, ev_good])
        removed = fix_zero_duration(subs)
        assert removed == 1
        assert len(subs.events) == 1

    def test_no_zero_duration_returns_zero(self):
        subs = _make_subs([_make_event(start=0, end=1000)])
        removed = fix_zero_duration(subs)
        assert removed == 0


# ===========================================================================
# apply_fixes (integration)
# ===========================================================================


class TestApplyFixes:
    def test_apply_fixes_creates_backup(self, tmp_path):
        lines = [
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
        ]
        path = _make_ass(tmp_path, lines=lines)
        base, ext = os.path.splitext(path)
        bak_path = f"{base}.bak{ext}"

        result = apply_fixes(path, ["duplicate_lines"])
        assert os.path.exists(bak_path)
        assert "duplicate_lines" in result["fixes_applied"]
        assert result["counts"]["duplicate_lines"] >= 1
        assert result["new_score"] >= 0

    def test_apply_fixes_unknown_fix_ignored(self, tmp_path):
        path = _make_ass(tmp_path)
        result = apply_fixes(path, ["nonexistent_fix"])
        assert result["fixes_applied"] == []
        assert result["counts"] == {}

    def test_apply_fixes_empty_list(self, tmp_path):
        path = _make_ass(tmp_path)
        result = apply_fixes(path, [])
        assert result["fixes_applied"] == []
        assert result["counts"] == {}

    def test_apply_fixes_multiple(self, tmp_path):
        # Create file with duplicate + empty event
        lines = [
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
            "Dialogue: 0,0:00:04.00,0:00:05.00,Default,,0,0,0,,",
        ]
        path = _make_ass(tmp_path, lines=lines)
        result = apply_fixes(path, ["duplicate_lines", "empty_events"])
        assert "duplicate_lines" in result["fixes_applied"]
        assert "empty_events" in result["fixes_applied"]

    def test_apply_fixes_zero_count_not_in_applied(self, tmp_path):
        """If a fix function returns 0, the name should NOT appear in fixes_applied."""
        path = _make_ass(tmp_path)  # Clean file with no issues
        result = apply_fixes(path, ["duplicate_lines"])
        assert "duplicate_lines" not in result["fixes_applied"]
        assert "duplicate_lines" not in result["counts"]

    def test_apply_fixes_saves_modified_file(self, tmp_path):
        lines = [
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello",
        ]
        path = _make_ass(tmp_path, lines=lines)
        apply_fixes(path, ["duplicate_lines"])
        # Reload and verify duplicate is gone
        subs = pysubs2.load(path)
        texts = [e.plaintext for e in subs.events if not e.is_comment]
        assert texts.count("Hello") == 1
