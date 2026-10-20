"""One ffsubsync shift parser, and no silent 0 ms on unparseable output.

The legacy wrapper (``services.video_sync``) and the engine class
(``services.sync_engines.ffsubsync_engine``) each had their own parser with
different patterns, and both returned 0 when no offset line was found. A run
whose output carried no offset then "succeeded" with no shift: the sidecar
was rewritten unchanged and booked as synced.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.sync_engines.ffsubsync_output import parse_ffsubsync_shift

REAL_LINE = "[13:51:53] INFO     offset seconds: 22.960                      ffsubsync.py:189"


class TestParser:
    @pytest.mark.parametrize(
        ("output", "expected"),
        [
            ("INFO     offset seconds: 22.960", 22960),
            (REAL_LINE, 22960),
            ("           INFO     offset seconds: -0.990    ffsubsync.py:189", -990),
            ("offset seconds: 0.000", 0),
            ("offset: 1.234 s applied", 1234),
            ("Offset: -0.5 s", -500),
            ("estimated shift: 0.42s", 420),
            ("offset -1.2s detected", -1200),
            ("offset seconds: 1.001", 1001),
        ],
    )
    def test_known_formats(self, output, expected):
        assert parse_ffsubsync_shift(output) == expected

    @pytest.mark.parametrize(
        "output",
        ["", "no offset info", "INFO     extracting speech segments...", "max_offset_seconds: 60"],
    )
    def test_no_offset_line_is_none_not_zero(self, output):
        assert parse_ffsubsync_shift(output) is None

    def test_both_modules_use_the_shared_parser(self):
        from services import video_sync
        from services.sync_engines import ffsubsync_engine

        assert video_sync._parse_ffsubsync_shift is parse_ffsubsync_shift
        assert ffsubsync_engine._parse_ffsubsync_shift is parse_ffsubsync_shift


ORIGINAL = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def test_legacy_wrapper_fails_without_an_offset_line(tmp_path):
    from services.video_sync import sync_with_ffsubsync

    sub = tmp_path / "ep.srt"
    sub.write_text(ORIGINAL)
    fake = MagicMock(returncode=0, stderr="INFO     computing alignments...", stdout="")
    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", return_value=fake),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        pytest.raises(RuntimeError, match="no offset"),
    ):
        sync_with_ffsubsync(str(sub), "/video.mkv")
    assert sub.read_text() == ORIGINAL


def test_legacy_wrapper_keeps_a_real_zero_offset(tmp_path):
    from services.video_sync import sync_with_ffsubsync

    sub = tmp_path / "ep.srt"
    sub.write_text(ORIGINAL)
    fake = MagicMock(returncode=0, stderr="INFO     offset seconds: 0.000", stdout="")
    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", return_value=fake),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
    ):
        result = sync_with_ffsubsync(str(sub), "/video.mkv")
    assert result["shift_ms"] == 0


def test_engine_reports_failure_without_an_offset_line(tmp_path):
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    sub = tmp_path / "ep.srt"
    sub.write_text(ORIGINAL)
    fake = MagicMock(returncode=0, stderr="INFO     computing alignments...", stdout="")
    with (
        patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="ffsubsync"),
        patch("services.sync_engines.ffsubsync_engine.subprocess.run", return_value=fake),
        patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger") as trigger,
    ):
        result = FfsubsyncEngine().sync(str(sub), "/v.mkv")
    assert result.ok is False
    assert "no offset" in result.reason
    assert sub.read_text() == ORIGINAL
    trigger.assert_not_called()


def test_preview_fails_without_an_offset_line(tmp_path):
    from services import sync_preview

    sub = tmp_path / "ep.srt"
    sub.write_text(ORIGINAL)
    fake = MagicMock(returncode=0, stderr="nothing useful", stdout="")
    with (
        patch("services.sync_preview.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch.object(sync_preview, "_locked_subprocess", return_value=fake),
        pytest.raises(RuntimeError, match="no offset"),
    ):
        sync_preview._run_ffsubsync_preview(str(sub), "/v.mkv")
