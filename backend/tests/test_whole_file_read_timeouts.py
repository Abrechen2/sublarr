"""Reading a whole video gets a timeout that grows with the file.

Prod 2026-11-08: two 7 GB Bluray remuxes of The Irregular at Magic High
School S03 never got translated. Pulling the ASS track out means ffmpeg reads
the whole file, and the fixed 120 s ``ffmpeg_timeout`` (~60 MB/s) killed it
while the array served other media work. A Pi or a slow NAS fails every remux.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

GB = 1024**3


def _video(tmp_path, size_gb: float):
    path = tmp_path / "episode.mkv"
    with open(path, "wb") as fh:
        fh.truncate(int(size_gb * GB))  # sparse: no disk space used
    return str(path)


class _StopError(Exception):
    pass


def _capture_timeout(monkeypatch, target: str) -> dict:
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise _StopError

    monkeypatch.setattr(target, fake_run)
    return seen


def _extract(tmp_path, monkeypatch, size_gb: float) -> int:
    from ass_probe import extract_subtitle_stream

    seen = _capture_timeout(monkeypatch, "ass_probe.subprocess.run")
    monkeypatch.setattr(
        "ass_probe.get_settings",
        lambda: MagicMock(ffmpeg_timeout=120, embedded_extract_ass_stream_copy=False),
    )
    with pytest.raises(_StopError):
        extract_subtitle_stream(
            _video(tmp_path, size_gb), {"sub_index": 0, "format": "ass"},
            str(tmp_path / "episode.en.ass"),
        )  # fmt: skip
    return seen["timeout"]


def test_extracting_from_a_7_gb_remux_outlasts_the_fixed_limit(tmp_path, app_ctx, monkeypatch):
    # 7 GB at 120 s needs 60 MB/s; the scaled limit allows ~17 MB/s.
    assert _extract(tmp_path, monkeypatch, 7) >= 7 * 60


def test_extracting_from_a_small_file_keeps_the_configured_limit(tmp_path, app_ctx, monkeypatch):
    assert _extract(tmp_path, monkeypatch, 1) == 120


def test_reading_embedded_cue_starts_scales_with_the_file(tmp_path, monkeypatch):
    import subtitle_timing

    seen = _capture_timeout(monkeypatch, "subprocess.run")
    monkeypatch.setattr(
        "services.subtitle_health.raw_io.list_subtitle_streams",
        lambda _path: [{"codec": "ass", "forced": False, "sub_index": 0}],
    )
    assert subtitle_timing._embedded_starts(_video(tmp_path, 12)) is None  # never raises
    assert seen["timeout"] >= 12 * 60


def test_ffsubsync_against_a_large_video_scales_with_the_file(tmp_path, monkeypatch):
    from services import video_sync

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr("services.video_sync.subprocess.run", fake_run)
    monkeypatch.setattr("services.video_sync.shutil.which", lambda _name: "/usr/bin/ffsubsync")
    subtitle = tmp_path / "episode.de.srt"
    subtitle.write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n", encoding="utf-8")
    try:
        video_sync.sync_with_ffsubsync(str(subtitle), _video(tmp_path, 25))
    except Exception:
        pass
    assert seen["timeout"] >= 25 * 60


def test_ocr_frame_dump_scales_with_the_file(tmp_path, monkeypatch):
    from services import ocr_extractor

    seen = _capture_timeout(monkeypatch, "services.ocr_extractor.subprocess.run")
    monkeypatch.setattr(ocr_extractor, "TESSERACT_AVAILABLE", True)
    with pytest.raises(_StopError):
        ocr_extractor.batch_ocr_track(_video(tmp_path, 12), 3)
    assert seen["timeout"] >= 12 * 60
