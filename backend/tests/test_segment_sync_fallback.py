"""A rejected framerate scale falls back to one shift per stretch.

ffsubsync answers a subtitle timed to another edit with a framerate scale.
Before 1.18.3 the scale gate rejected it and the file stayed out of step
(prod 2026-10-30: Slime S02E19 2.5-4 s late). Now every ffsubsync caller tries
a segment plan first; only without one does the rejection stand.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.segment_sync import SegmentPlan

SRT = "1\n00:00:05,000 --> 00:00:06,000\nHi\n\n2\n00:00:50,000 --> 00:00:51,000\nThere\n"
SCALED = "INFO offset seconds: -2.520\nframerate scale factor: 0.999"
PLAN = SegmentPlan(stretches=((0, 0), (30_000, -2540)), end_ms=1_400_000)


def _ffsubsync(cmd, **kwargs):
    with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
        fh.write(SRT)
    return MagicMock(returncode=0, stderr=SCALED, stdout="")


def _starts(path):
    import pysubs2

    return [e.start for e in pysubs2.load(str(path)).events]


@pytest.fixture
def speech():
    """Any speech; the plan itself comes from ``plan_segments``, patched per test."""
    with patch("services.segment_sync.load_speech", return_value=[1, 0, 1]) as stub:
        yield stub


def test_the_service_sync_writes_the_segment_plan(tmp_path, speech):
    from services.video_sync import sync_with_ffsubsync

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", side_effect=_ffsubsync),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        patch("services.segment_sync.plan_segments", return_value=PLAN),
        patch("services.sync_engines.events.write_sync_job_run") as audit,
    ):
        result = sync_with_ffsubsync(str(sub), "/video.mkv")

    assert _starts(sub) == [5_000, 47_460]
    assert result["shift_ms"] == -2540
    assert audit.call_args.kwargs["status"] == "ok"
    assert audit.call_args.kwargs["reason"] == "segments:0,-2540"


def test_without_a_plan_the_rejection_stands(tmp_path, speech):
    from services.video_sync import SyncSanityThresholdError, sync_with_ffsubsync

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", side_effect=_ffsubsync),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        patch("services.segment_sync.plan_segments", return_value=None),
        pytest.raises(SyncSanityThresholdError, match="framerate scale factor 0.999"),
    ):
        sync_with_ffsubsync(str(sub), "/video.mkv")

    assert sub.read_text(encoding="utf-8") == SRT


def test_the_engine_writes_the_segment_plan(tmp_path, speech):
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with (
        patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="ffsubsync"),
        patch("services.sync_engines.ffsubsync_engine.subprocess.run", side_effect=_ffsubsync),
        patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger"),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        patch("services.segment_sync.plan_segments", return_value=PLAN),
    ):
        result = FfsubsyncEngine().sync(str(sub), "/video.mkv")

    assert result.ok is True
    assert result.offset_ms == -2540
    assert result.reason == "segments:0,-2540"
    assert _starts(sub) == [5_000, 47_460]


def test_the_engine_without_a_plan_still_fails(tmp_path, speech):
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with (
        patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="ffsubsync"),
        patch("services.sync_engines.ffsubsync_engine.subprocess.run", side_effect=_ffsubsync),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        patch("services.segment_sync.plan_segments", return_value=None),
    ):
        result = FfsubsyncEngine().sync(str(sub), "/video.mkv")

    assert result.ok is False
    assert "framerate scale factor 0.999" in result.reason
    assert sub.read_text(encoding="utf-8") == SRT


def test_the_preview_shows_the_segment_plan(tmp_path, speech):
    import os

    from services.sync_preview import _run_ffsubsync_preview

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with (
        patch("services.sync_preview.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch(
            "services.sync_preview._locked_subprocess",
            side_effect=lambda cmd, timeout: _ffsubsync(cmd),
        ),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=45_000)),
        patch("services.segment_sync.plan_segments", return_value=PLAN),
    ):
        shift_ms, out_path = _run_ffsubsync_preview(str(sub), "/video.mkv")

    try:
        assert shift_ms == -2540
        assert _starts(out_path) == [5_000, 47_460]
        assert sub.read_text(encoding="utf-8") == SRT
    finally:
        os.remove(out_path)


def test_a_pal_speed_up_is_not_cut_into_stretches(tmp_path, speech):
    """25/24 is a real speed change; prod dry run 2026-10-30 planned -45 s for one."""
    from services.video_sync import segment_sync_fallback

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    with patch("services.segment_sync.plan_segments", return_value=PLAN) as planner:
        plan = segment_sync_fallback(
            str(sub), "/video.mkv", str(tmp_path / "o.srt"), 45_000, 1.042, 0
        )

    assert plan is None
    planner.assert_not_called()
