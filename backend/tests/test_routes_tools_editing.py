"""Tests for routes/tools/editing.py -- remove-hi, remove-credits, detect-opening-ending, adjust-timing, common-fixes."""

import os
import sys
import tempfile
from unittest.mock import MagicMock, mock_open, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Resolve once — avoids 8.3 short-name vs long-name mismatch on Windows
_TEMP_DIR = os.path.realpath(tempfile.gettempdir())


def _make_srt(path: str, content: str | None = None) -> str:
    """Write an SRT file under the media_path temp dir and return its absolute path."""
    abs_path = os.path.join(_TEMP_DIR, path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    if content is None:
        content = (
            "1\n00:00:01,000 --> 00:00:03,000\nHello World\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nGoodbye World\n"
        )
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return abs_path


def _make_ass(path: str, content: str | None = None) -> str:
    """Write an ASS file under the media_path temp dir and return its absolute path."""
    abs_path = os.path.join(_TEMP_DIR, path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    if content is None:
        content = (
            "[Script Info]\nTitle: Test\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
            "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello World\n"
            "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,Goodbye World\n"
        )
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return abs_path


def _cleanup(path: str) -> None:
    """Remove a file and its .bak sibling if they exist."""
    for p in (path, path.replace(".srt", ".bak.srt"), path.replace(".ass", ".bak.ass")):
        try:
            if os.path.exists(p):
                os.unlink(p)
        except OSError:
            pass


# ==============================================================================
# Remove HI
# ==============================================================================


class TestRemoveHI:
    """POST /api/v1/tools/remove-hi"""

    def test_remove_hi_missing_file_path(self, client):
        rv = client.post("/api/v1/tools/remove-hi", json={})
        assert rv.status_code == 400
        assert "file_path" in rv.get_json()["error"]

    def test_remove_hi_file_outside_media_path(self, client):
        rv = client.post("/api/v1/tools/remove-hi", json={"file_path": "/etc/passwd"})
        assert rv.status_code == 403
        assert "media_path" in rv.get_json()["error"]

    def test_remove_hi_file_not_found(self, client):
        missing = os.path.join(_TEMP_DIR, "nonexistent_hi_test.srt")
        rv = client.post("/api/v1/tools/remove-hi", json={"file_path": missing})
        assert rv.status_code == 404

    def test_remove_hi_unsupported_format(self, client):
        txt_path = os.path.join(_TEMP_DIR, "test_hi.txt")
        with open(txt_path, "w") as f:
            f.write("not a subtitle")
        try:
            rv = client.post("/api/v1/tools/remove-hi", json={"file_path": txt_path})
            assert rv.status_code == 400
            assert "supported" in rv.get_json()["error"].lower()
        finally:
            _cleanup(txt_path)

    def test_remove_hi_srt_success(self, client):
        srt = _make_srt("test_remove_hi.srt")
        try:
            with patch(
                "hi_remover.remove_hi_from_srt",
                return_value="1\n00:00:01,000 --> 00:00:03,000\nHello World\n",
            ):
                rv = client.post("/api/v1/tools/remove-hi", json={"file_path": srt})

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "cleaned"
            assert "original_lines" in data
            assert "cleaned_lines" in data
            assert "removed" in data
        finally:
            _cleanup(srt)

    def test_remove_hi_ass_uses_remove_hi_markers(self, client):
        ass_path = _make_ass("test_remove_hi.ass")
        try:
            mock_result = "cleaned ass content"
            with patch("hi_remover.remove_hi_markers", return_value=mock_result) as mock_fn:
                rv = client.post("/api/v1/tools/remove-hi", json={"file_path": ass_path})

            assert rv.status_code == 200
            mock_fn.assert_called_once()
            data = rv.get_json()
            assert data["status"] == "cleaned"
        finally:
            _cleanup(ass_path)

    def test_remove_hi_creates_backup(self, client):
        srt = _make_srt("test_remove_hi_backup.srt")
        bak = srt.replace(".srt", ".bak.srt")
        try:
            with patch("hi_remover.remove_hi_from_srt", return_value="cleaned"):
                rv = client.post("/api/v1/tools/remove-hi", json={"file_path": srt})

            assert rv.status_code == 200
            assert os.path.exists(bak)
        finally:
            _cleanup(srt)

    def test_remove_hi_internal_error(self, client):
        srt = _make_srt("test_remove_hi_error.srt")
        try:
            with patch("hi_remover.remove_hi_from_srt", side_effect=RuntimeError("boom")):
                rv = client.post("/api/v1/tools/remove-hi", json={"file_path": srt})

            assert rv.status_code == 500
            assert "error" in rv.get_json()
        finally:
            _cleanup(srt)


# ==============================================================================
# Remove Credits
# ==============================================================================


class TestRemoveCredits:
    """POST /api/v1/tools/remove-credits"""

    def test_remove_credits_missing_file_path(self, client):
        rv = client.post("/api/v1/tools/remove-credits", json={})
        assert rv.status_code == 400

    def test_remove_credits_file_outside_media_path(self, client):
        rv = client.post("/api/v1/tools/remove-credits", json={"file_path": "/etc/shadow"})
        assert rv.status_code == 403

    def test_remove_credits_file_not_found(self, client):
        missing = os.path.join(_TEMP_DIR, "nonexistent_credits_test.srt")
        rv = client.post("/api/v1/tools/remove-credits", json={"file_path": missing})
        assert rv.status_code == 404

    def test_remove_credits_srt_success(self, client):
        srt = _make_srt("test_remove_credits.srt")
        try:
            cleaned = "1\n00:00:01,000 --> 00:00:03,000\nHello World\n"
            with patch("credit_remover.remove_credits_from_srt", return_value=(cleaned, 1)):
                rv = client.post("/api/v1/tools/remove-credits", json={"file_path": srt})

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "cleaned"
            assert data["removed"] == 1
            assert "backed_up" in data
            assert "original_lines" in data
            assert "cleaned_lines" in data
        finally:
            _cleanup(srt)

    def test_remove_credits_ass_success(self, client):
        ass_path = _make_ass("test_remove_credits.ass")
        try:
            cleaned_content = "cleaned ass"
            with patch("credit_remover.remove_credits_from_ass", return_value=(cleaned_content, 2)):
                rv = client.post("/api/v1/tools/remove-credits", json={"file_path": ass_path})

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "cleaned"
            assert data["removed"] == 2
        finally:
            _cleanup(ass_path)

    def test_remove_credits_dry_run_srt(self, client):
        srt_content = (
            "1\n00:00:01,000 --> 00:00:03,000\nHello World\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nTranslated by SomeGroup\n"
        )
        srt = _make_srt("test_credits_dryrun.srt", content=srt_content)
        try:
            cleaned = "1\n00:00:01,000 --> 00:00:03,000\nHello World\n"
            with patch("credit_remover.remove_credits_from_srt", return_value=(cleaned, 1)):
                rv = client.post(
                    "/api/v1/tools/remove-credits",
                    json={"file_path": srt, "dry_run": True},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "dry_run"
            assert data["would_remove"] == 1
            assert "preview" in data
            assert isinstance(data["preview"], list)
        finally:
            _cleanup(srt)

    def test_remove_credits_dry_run_ass_returns_empty_preview(self, client):
        ass_path = _make_ass("test_credits_dryrun.ass")
        try:
            with patch("credit_remover.remove_credits_from_ass", return_value=("cleaned", 1)):
                rv = client.post(
                    "/api/v1/tools/remove-credits",
                    json={"file_path": ass_path, "dry_run": True},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "dry_run"
            assert data["preview"] == []
        finally:
            _cleanup(ass_path)

    def test_remove_credits_creates_backup(self, client):
        srt = _make_srt("test_credits_backup.srt")
        bak = srt.replace(".srt", ".bak.srt")
        try:
            with patch("credit_remover.remove_credits_from_srt", return_value=("cleaned", 0)):
                rv = client.post("/api/v1/tools/remove-credits", json={"file_path": srt})

            assert rv.status_code == 200
            assert os.path.exists(bak)
        finally:
            _cleanup(srt)

    def test_remove_credits_internal_error(self, client):
        srt = _make_srt("test_credits_error.srt")
        try:
            with patch("credit_remover.remove_credits_from_srt", side_effect=RuntimeError("fail")):
                rv = client.post("/api/v1/tools/remove-credits", json={"file_path": srt})

            assert rv.status_code == 500
            assert "error" in rv.get_json()
        finally:
            _cleanup(srt)


# ==============================================================================
# Detect Opening / Ending
# ==============================================================================


class TestDetectOpeningEnding:
    """POST /api/v1/tools/detect-opening-ending"""

    def test_detect_missing_file_path(self, client):
        rv = client.post("/api/v1/tools/detect-opening-ending", json={})
        assert rv.status_code == 400

    def test_detect_file_outside_media_path(self, client):
        rv = client.post("/api/v1/tools/detect-opening-ending", json={"file_path": "/etc/hosts"})
        assert rv.status_code == 403

    def test_detect_file_not_found(self, client):
        missing = os.path.join(_TEMP_DIR, "nonexistent_oped_test.srt")
        rv = client.post("/api/v1/tools/detect-opening-ending", json={"file_path": missing})
        assert rv.status_code == 404

    def test_detect_srt_success(self, client):
        srt = _make_srt("test_detect_oped.srt")
        try:
            detected = [{"type": "OP", "start": "00:00:30", "end": "00:02:00"}]
            with patch("op_ed_detector.detect_op_ed_from_srt", return_value=detected):
                rv = client.post(
                    "/api/v1/tools/detect-opening-ending",
                    json={"file_path": srt},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "detected"
            assert len(data["detected"]) == 1
            assert data["detected"][0]["type"] == "OP"
        finally:
            _cleanup(srt)

    def test_detect_ass_success(self, client):
        ass_path = _make_ass("test_detect_oped.ass")
        try:
            detected = [
                {"type": "OP", "start": "0:00:30.00", "end": "0:02:00.00"},
                {"type": "ED", "start": "0:21:00.00", "end": "0:22:30.00"},
            ]
            with patch("op_ed_detector.detect_op_ed_from_ass", return_value=detected):
                rv = client.post(
                    "/api/v1/tools/detect-opening-ending",
                    json={"file_path": ass_path},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "detected"
            assert len(data["detected"]) == 2
        finally:
            _cleanup(ass_path)

    def test_detect_empty_result(self, client):
        srt = _make_srt("test_detect_empty.srt")
        try:
            with patch("op_ed_detector.detect_op_ed_from_srt", return_value=[]):
                rv = client.post(
                    "/api/v1/tools/detect-opening-ending",
                    json={"file_path": srt},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["detected"] == []
        finally:
            _cleanup(srt)

    def test_detect_internal_error(self, client):
        srt = _make_srt("test_detect_error.srt")
        try:
            with patch("op_ed_detector.detect_op_ed_from_srt", side_effect=ValueError("bad")):
                rv = client.post(
                    "/api/v1/tools/detect-opening-ending",
                    json={"file_path": srt},
                )

            assert rv.status_code == 500
            assert "error" in rv.get_json()
        finally:
            _cleanup(srt)


# ==============================================================================
# Adjust Timing
# ==============================================================================


class TestAdjustTiming:
    """POST /api/v1/tools/adjust-timing"""

    def test_adjust_missing_file_path(self, client):
        rv = client.post("/api/v1/tools/adjust-timing", json={"offset_ms": 500})
        assert rv.status_code == 400

    def test_adjust_invalid_offset_type(self, client):
        rv = client.post(
            "/api/v1/tools/adjust-timing",
            json={"file_path": "some.srt", "offset_ms": "not_a_number"},
        )
        assert rv.status_code == 400
        assert "offset_ms" in rv.get_json()["error"]

    def test_adjust_file_outside_media_path(self, client):
        rv = client.post(
            "/api/v1/tools/adjust-timing",
            json={"file_path": "/etc/passwd", "offset_ms": 500},
        )
        assert rv.status_code == 403

    def test_adjust_file_not_found(self, client):
        missing = os.path.join(_TEMP_DIR, "nonexistent_timing.srt")
        rv = client.post(
            "/api/v1/tools/adjust-timing",
            json={"file_path": missing, "offset_ms": 500},
        )
        assert rv.status_code == 404

    def test_adjust_srt_positive_offset(self, client):
        srt_content = (
            "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n2\n00:00:04,000 --> 00:00:06,000\nWorld\n"
        )
        srt = _make_srt("test_adjust_pos.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": srt, "offset_ms": 2000},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "adjusted"
            assert data["lines_modified"] == 2
            assert data["offset_ms"] == 2000

            # Verify content was shifted
            with open(srt, encoding="utf-8") as f:
                content = f.read()
            assert "00:00:03,000" in content  # 01,000 + 2s = 03,000
            assert "00:00:05,000" in content  # 03,000 + 2s = 05,000
        finally:
            _cleanup(srt)

    def test_adjust_srt_negative_offset_clamps_to_zero(self, client):
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n"
        srt = _make_srt("test_adjust_neg.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": srt, "offset_ms": -5000},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["lines_modified"] == 1

            with open(srt, encoding="utf-8") as f:
                content = f.read()
            # 01,000 - 5000 = negative => clamped to 00:00:00,000
            assert "00:00:00,000" in content
        finally:
            _cleanup(srt)

    def test_adjust_ass_positive_offset(self, client):
        ass_content = (
            "[Script Info]\nTitle: Test\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\n"
            "Dialogue: 0,0:00:04.00,0:00:06.00,Default,,0,0,0,,World\n"
        )
        ass_path = _make_ass("test_adjust_pos.ass", content=ass_content)
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": ass_path, "offset_ms": 1000},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "adjusted"
            assert data["lines_modified"] == 2
            assert data["offset_ms"] == 1000

            with open(ass_path, encoding="utf-8") as f:
                content = f.read()
            # 0:00:01.00 + 1s = 0:00:02.00
            assert "0:00:02.00" in content
        finally:
            _cleanup(ass_path)

    def test_adjust_ass_negative_offset_clamps(self, client):
        ass_content = (
            "[Script Info]\nTitle: Test\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:00.50,0:00:01.00,Default,,0,0,0,,Short\n"
        )
        ass_path = _make_ass("test_adjust_neg.ass", content=ass_content)
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": ass_path, "offset_ms": -10000},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["lines_modified"] == 1

            with open(ass_path, encoding="utf-8") as f:
                content = f.read()
            assert "0:00:00.00" in content
        finally:
            _cleanup(ass_path)

    def test_adjust_creates_backup(self, client):
        srt = _make_srt("test_adjust_backup.srt")
        bak = srt.replace(".srt", ".bak.srt")
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": srt, "offset_ms": 100},
            )
            assert rv.status_code == 200
            assert os.path.exists(bak)
        finally:
            _cleanup(srt)

    def test_adjust_float_offset_converted_to_int(self, client):
        srt = _make_srt("test_adjust_float.srt")
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": srt, "offset_ms": 500.7},
            )
            assert rv.status_code == 200
            data = rv.get_json()
            assert data["offset_ms"] == 500
        finally:
            _cleanup(srt)

    def test_adjust_zero_offset(self, client):
        srt_content = "1\n00:00:05,000 --> 00:00:07,000\nStatic\n"
        srt = _make_srt("test_adjust_zero.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/adjust-timing",
                json={"file_path": srt, "offset_ms": 0},
            )
            assert rv.status_code == 200
            data = rv.get_json()
            assert data["offset_ms"] == 0
            # Timestamps should be unchanged
            with open(srt, encoding="utf-8") as f:
                content = f.read()
            assert "00:00:05,000" in content
            assert "00:00:07,000" in content
        finally:
            _cleanup(srt)

    def test_adjust_internal_error(self, client):
        srt = _make_srt("test_adjust_error.srt")
        try:
            with patch("builtins.open", side_effect=PermissionError("locked")):
                rv = client.post(
                    "/api/v1/tools/adjust-timing",
                    json={"file_path": srt, "offset_ms": 100},
                )
            assert rv.status_code == 500
            assert "error" in rv.get_json()
        finally:
            _cleanup(srt)


# ==============================================================================
# Common Fixes
# ==============================================================================


class TestCommonFixes:
    """POST /api/v1/tools/common-fixes"""

    def test_common_fixes_missing_file_path(self, client):
        rv = client.post("/api/v1/tools/common-fixes", json={"fixes": ["whitespace"]})
        assert rv.status_code == 400

    def test_common_fixes_empty_fixes_list(self, client):
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": "some.srt", "fixes": []},
        )
        assert rv.status_code == 400
        assert "non-empty" in rv.get_json()["error"]

    def test_common_fixes_invalid_fix_name(self, client):
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": "some.srt", "fixes": ["nonexistent_fix"]},
        )
        assert rv.status_code == 400
        assert "Invalid" in rv.get_json()["error"]

    def test_common_fixes_fixes_not_array(self, client):
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": "some.srt", "fixes": "whitespace"},
        )
        assert rv.status_code == 400
        assert "non-empty array" in rv.get_json()["error"]

    def test_common_fixes_file_outside_media_path(self, client):
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": "/etc/passwd", "fixes": ["whitespace"]},
        )
        assert rv.status_code == 403

    def test_common_fixes_file_not_found(self, client):
        missing = os.path.join(_TEMP_DIR, "nonexistent_fixes.srt")
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": missing, "fixes": ["whitespace"]},
        )
        assert rv.status_code == 404

    def test_common_fixes_whitespace(self, client):
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello   \n\n"
        srt = _make_srt("test_fixes_ws.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt, "fixes": ["whitespace"]},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "fixed"
            assert "whitespace" in data["fixes_applied"]
            assert "lines_before" in data
            assert "lines_after" in data

            with open(srt, encoding="utf-8") as f:
                content = f.read()
            # Trailing spaces should be gone
            for line in content.split("\n"):
                assert line == line.rstrip()
        finally:
            _cleanup(srt)

    def test_common_fixes_linebreaks(self, client):
        srt_content = "1\r\n00:00:01,000 --> 00:00:03,000\r\nHello\r\n\r\n"
        srt = _make_srt("test_fixes_lb.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt, "fixes": ["linebreaks"]},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "linebreaks" in data["fixes_applied"]
        finally:
            _cleanup(srt)

    def test_common_fixes_empty_lines(self, client):
        srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n\n\n2\n00:00:04,000 --> 00:00:06,000\nWorld\n"
        srt = _make_srt("test_fixes_empty.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt, "fixes": ["empty_lines"]},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "empty_lines" in data["fixes_applied"]
            # Consecutive empty lines should be collapsed
            assert data["lines_after"] < data["lines_before"]
        finally:
            _cleanup(srt)

    def test_common_fixes_encoding_with_chardet(self, client):
        srt = _make_srt("test_fixes_enc.srt")
        try:
            mock_chardet = MagicMock()
            mock_chardet.detect.return_value = {"encoding": "utf-8", "confidence": 0.99}
            with patch.dict("sys.modules", {"chardet": mock_chardet}):
                rv = client.post(
                    "/api/v1/tools/common-fixes",
                    json={"file_path": srt, "fixes": ["encoding"]},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "encoding" in data["fixes_applied"]
        finally:
            _cleanup(srt)

    def test_common_fixes_encoding_without_chardet(self, client):
        srt = _make_srt("test_fixes_enc_nochd.srt")
        try:
            # Simulate chardet not installed
            import importlib

            with patch.dict("sys.modules", {"chardet": None}):
                rv = client.post(
                    "/api/v1/tools/common-fixes",
                    json={"file_path": srt, "fixes": ["encoding"]},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "encoding" in data["fixes_applied"]
        finally:
            _cleanup(srt)

    def test_common_fixes_multiple_fixes(self, client):
        srt_content = "1\r\n00:00:01,000 --> 00:00:03,000\r\nHello   \r\n\r\n\r\n"
        srt = _make_srt("test_fixes_multi.srt", content=srt_content)
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt, "fixes": ["linebreaks", "whitespace", "empty_lines"]},
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["status"] == "fixed"
            assert "linebreaks" in data["fixes_applied"]
            assert "whitespace" in data["fixes_applied"]
            assert "empty_lines" in data["fixes_applied"]
        finally:
            _cleanup(srt)

    def test_common_fixes_creates_backup(self, client):
        srt = _make_srt("test_fixes_backup.srt")
        bak = srt.replace(".srt", ".bak.srt")
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt, "fixes": ["whitespace"]},
            )
            assert rv.status_code == 200
            assert os.path.exists(bak)
        finally:
            _cleanup(srt)

    def test_common_fixes_linebreaks_ass_with_ass_utils(self, client):
        ass_content = (
            "[Script Info]\nTitle: Test\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\\nWorld\n"
        )
        ass_path = _make_ass("test_fixes_lb_ass.ass", content=ass_content)
        try:
            with patch("ass_utils.fix_line_breaks", side_effect=lambda t: t.replace("\\n", "\\N")):
                rv = client.post(
                    "/api/v1/tools/common-fixes",
                    json={"file_path": ass_path, "fixes": ["linebreaks"]},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "linebreaks" in data["fixes_applied"]
        finally:
            _cleanup(ass_path)

    def test_common_fixes_linebreaks_ass_without_ass_utils(self, client):
        """When ass_utils is not available, linebreaks fix still works for basic CRLF."""
        ass_content = (
            "[Script Info]\r\nTitle: Test\r\n\r\n[Events]\r\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\r\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello\r\n"
        )
        ass_path = _make_ass("test_fixes_lb_ass_noutil.ass", content=ass_content)
        try:
            with patch.dict("sys.modules", {"ass_utils": None}):
                rv = client.post(
                    "/api/v1/tools/common-fixes",
                    json={"file_path": ass_path, "fixes": ["linebreaks"]},
                )

            assert rv.status_code == 200
            data = rv.get_json()
            assert "linebreaks" in data["fixes_applied"]
        finally:
            _cleanup(ass_path)

    def test_common_fixes_internal_error(self, client):
        srt = _make_srt("test_fixes_error.srt")
        try:
            with patch("builtins.open", side_effect=PermissionError("locked")):
                rv = client.post(
                    "/api/v1/tools/common-fixes",
                    json={"file_path": srt, "fixes": ["whitespace"]},
                )
            assert rv.status_code == 500
            assert "error" in rv.get_json()
        finally:
            _cleanup(srt)

    def test_common_fixes_partial_invalid_fix_names(self, client):
        """Mixing valid and invalid fix names returns 400."""
        rv = client.post(
            "/api/v1/tools/common-fixes",
            json={"file_path": "some.srt", "fixes": ["whitespace", "bogus"]},
        )
        assert rv.status_code == 400
        assert "Invalid" in rv.get_json()["error"]

    def test_common_fixes_whitespace_only_preserves_non_utf8_bytes(self, client):
        """Regression: a Latin-1 file run through whitespace-only fix used to be
        re-written as UTF-8 with errors=replace, silently mangling every non-ASCII
        byte. Source encoding is now detected via chardet and preserved for
        non-encoding fixes."""
        srt_path = os.path.join(_TEMP_DIR, "test_fixes_latin1.srt")
        # Latin-1 content with characters that are NOT valid UTF-8 when the
        # round-trip is broken: ä=0xE4, ö=0xF6, ü=0xFC, ß=0xDF
        latin1_text = (
            "1\r\n00:00:01,000 --> 00:00:03,000\r\nGrüß Gott   \r\n\r\n"
            "2\r\n00:00:04,000 --> 00:00:06,000\r\nKräuter und Rösti   \r\n"
        )
        with open(srt_path, "w", encoding="latin-1", newline="") as f:
            f.write(latin1_text)
        try:
            rv = client.post(
                "/api/v1/tools/common-fixes",
                json={"file_path": srt_path, "fixes": ["whitespace"]},
            )
            assert rv.status_code == 200

            # File must still decode as Latin-1; UTF-8 decode would either fail
            # or produce mojibake on the bytes 0xE4/0xF6/0xFC/0xDF.
            with open(srt_path, "rb") as f:
                raw = f.read()
            decoded = raw.decode("latin-1")
            assert "Grüß Gott" in decoded
            assert "Kräuter und Rösti" in decoded
            # Trailing whitespace per line is gone (the fix that was requested)
            for line in decoded.split("\n"):
                assert line == line.rstrip()
        finally:
            _cleanup(srt_path)


# ==============================================================================
# Backup helper idempotence (regression for _create_backup)
# ==============================================================================


class TestBackupIdempotence:
    """Regression tests for routes/tools/_helpers.py::_create_backup."""

    def test_two_remove_hi_runs_keep_original_in_backup(self, client):
        """If a user runs a tool twice, the .bak must still hold the ORIGINAL
        file content, not the result of the first run. Otherwise the user can
        no longer recover the source via GET /tools/backup."""
        srt = _make_srt(
            "test_backup_idempotence.srt",
            content="1\n00:00:01,000 --> 00:00:03,000\n[music] Hello\n",
        )
        bak = srt.replace(".srt", ".bak.srt")
        try:
            with patch("hi_remover.remove_hi_from_srt", return_value="FIRST_RUN_OUTPUT"):
                rv1 = client.post("/api/v1/tools/remove-hi", json={"file_path": srt})
            assert rv1.status_code == 200
            assert os.path.exists(bak)
            with open(bak, encoding="utf-8") as f:
                bak_after_first = f.read()
            assert "[music] Hello" in bak_after_first

            with patch("hi_remover.remove_hi_from_srt", return_value="SECOND_RUN_OUTPUT"):
                rv2 = client.post("/api/v1/tools/remove-hi", json={"file_path": srt})
            assert rv2.status_code == 200

            with open(bak, encoding="utf-8") as f:
                bak_after_second = f.read()
            # Backup must STILL be the pre-first-run content, not "FIRST_RUN_OUTPUT".
            assert bak_after_second == bak_after_first
            assert "FIRST_RUN_OUTPUT" not in bak_after_second
        finally:
            _cleanup(srt)


# ==============================================================================
# Helper function unit tests
# ==============================================================================


class TestShiftSrtTimestamp:
    """Unit tests for _shift_srt_timestamp."""

    def test_positive_shift(self):
        from routes.tools.timing import _SRT_TIMESTAMP_RE, _shift_srt_timestamp

        line = "00:00:01,000"
        result = _SRT_TIMESTAMP_RE.sub(lambda m: _shift_srt_timestamp(m, 2000), line)
        assert result == "00:00:03,000"

    def test_negative_shift_clamps(self):
        from routes.tools.timing import _SRT_TIMESTAMP_RE, _shift_srt_timestamp

        line = "00:00:01,000"
        result = _SRT_TIMESTAMP_RE.sub(lambda m: _shift_srt_timestamp(m, -5000), line)
        assert result == "00:00:00,000"

    def test_large_shift_wraps_hours(self):
        from routes.tools.timing import _SRT_TIMESTAMP_RE, _shift_srt_timestamp

        line = "00:59:59,500"
        result = _SRT_TIMESTAMP_RE.sub(lambda m: _shift_srt_timestamp(m, 1000), line)
        assert result == "01:00:00,500"

    def test_millisecond_precision(self):
        from routes.tools.timing import _SRT_TIMESTAMP_RE, _shift_srt_timestamp

        line = "00:00:00,000"
        result = _SRT_TIMESTAMP_RE.sub(lambda m: _shift_srt_timestamp(m, 123), line)
        assert result == "00:00:00,123"


class TestShiftAssTime:
    """Unit tests for _shift_ass_time."""

    def test_positive_shift(self):
        from routes.tools.timing import _shift_ass_time

        result = _shift_ass_time(0, 0, 1, 0, 2000)
        assert result == "0:00:03.00"

    def test_negative_shift_clamps(self):
        from routes.tools.timing import _shift_ass_time

        result = _shift_ass_time(0, 0, 1, 0, -5000)
        assert result == "0:00:00.00"

    def test_centisecond_precision(self):
        from routes.tools.timing import _shift_ass_time

        result = _shift_ass_time(0, 0, 0, 0, 1050)
        assert result == "0:00:01.05"

    def test_hour_rollover(self):
        from routes.tools.timing import _shift_ass_time

        result = _shift_ass_time(0, 59, 59, 50, 1000)
        assert result == "1:00:00.50"
