"""Every ffsubsync run measures a plain shift (--no-fix-framerate).

Prod 2026-10-30: ffsubsync paired the right -2.5 s shift of Slime S02E19 with
a 1000/1001 framerate scale; the scale gate threw the whole result away and
the subtitle stayed 2.5 s late. Without the framerate fix ffsubsync reports
the shift alone, so the sync goes through.
"""

from unittest.mock import MagicMock, patch

SRT = "1\n00:00:05,000 --> 00:00:06,000\nHi\n"
OUTPUT = "INFO offset seconds: -2.540\nframerate scale factor: 1.000"


def _fake_run(calls):
    def run(cmd, **kwargs):
        calls.append(list(cmd))
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write(SRT)
        return MagicMock(returncode=0, stderr=OUTPUT, stdout="")

    return run


def test_the_service_sync_asks_for_a_plain_shift(tmp_path):
    import pysubs2

    from services.video_sync import sync_with_ffsubsync

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    calls = []
    with (
        patch("services.video_sync.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.video_sync.subprocess.run", side_effect=_fake_run(calls)),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=60_000)),
    ):
        result = sync_with_ffsubsync(str(sub), "/video.mkv")

    assert "--no-fix-framerate" in calls[0]
    assert result["shift_ms"] == -2540
    assert pysubs2.load(str(sub)).events[0].start == 2460


def test_the_engine_asks_for_a_plain_shift(tmp_path):
    from services.sync_engines.ffsubsync_engine import FfsubsyncEngine

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    calls = []
    with (
        patch("services.sync_engines.ffsubsync_engine.shutil.which", return_value="ffsubsync"),
        patch(
            "services.sync_engines.ffsubsync_engine.subprocess.run",
            side_effect=_fake_run(calls),
        ),
        patch("services.sync_engines.ffsubsync_engine._fire_after_sync_trigger"),
    ):
        result = FfsubsyncEngine().sync(str(sub), "/video.mkv")

    assert "--no-fix-framerate" in calls[0]
    assert result.ok is True


def test_the_preview_asks_for_a_plain_shift(tmp_path):
    import os

    from services.sync_preview import _run_ffsubsync_preview

    sub = tmp_path / "ep.de.srt"
    sub.write_text(SRT, encoding="utf-8")
    calls = []
    run = _fake_run(calls)
    with (
        patch("services.sync_preview.shutil.which", return_value="/usr/bin/ffsubsync"),
        patch("services.sync_preview._locked_subprocess", side_effect=lambda cmd, t: run(cmd)),
        patch("config.get_settings", return_value=MagicMock(sync_sanity_threshold_ms=60_000)),
    ):
        shift_ms, out_path = _run_ffsubsync_preview(str(sub), "/video.mkv")

    os.remove(out_path)
    assert "--no-fix-framerate" in calls[0]
    assert shift_ms == -2540
