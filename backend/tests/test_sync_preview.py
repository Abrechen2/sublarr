"""Sync-compare preview service (V1.6 #4). Runs sync engines WITHOUT
overwriting the sidecar and returns original vs candidate cues so the UI can
show a side-by-side diff and let the user pick which to keep.

The engine subprocess helpers are patched so these tests need neither ffsubsync
nor alass installed.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pysubs2
import pytest

from services import sync_preview
from services.video_sync import SyncSanityThresholdError, SyncUnavailableError


def _write_srt(path: str, cues: list[tuple[int, int, str]]) -> None:
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        ev = pysubs2.SSAEvent(start=start, end=end)
        ev.plaintext = text
        subs.events.append(ev)
    subs.save(path, format_="srt")


def _make_original(tmp_path) -> str:
    p = str(tmp_path / "ep.en.srt")
    _write_srt(p, [(1000, 3000, "Hello"), (4000, 6000, "World")])
    return p


def _fake_synced(shift: int):
    """Return a run-fn that writes a shifted copy to a temp file."""

    def _run(subtitle_path, _ref):
        fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        _write_srt(
            out, [(1000 + shift, 3000 + shift, "Hello"), (4000 + shift, 6000 + shift, "World")]
        )
        return shift, out

    return _run


def test_compare_returns_original_and_candidate_cues(tmp_path, monkeypatch):
    original = _make_original(tmp_path)
    monkeypatch.setattr(sync_preview, "_run_ffsubsync_preview", _fake_synced(500))

    result = sync_preview.sync_compare(original, video_path="/v/ep.mkv")

    assert [c["start"] for c in result["original"]] == [1000, 4000]
    assert result["any_output"] is True
    ff = next(c for c in result["candidates"] if c["engine"] == "ffsubsync")
    assert ff["status"] == "ok"
    assert ff["shift_ms"] == 500
    assert [c["start"] for c in ff["cues"]] == [1500, 4500]


def test_compare_runs_alass_when_reference_given(tmp_path, monkeypatch):
    original = _make_original(tmp_path)
    monkeypatch.setattr(sync_preview, "_run_ffsubsync_preview", _fake_synced(200))
    monkeypatch.setattr(sync_preview, "_run_alass_preview", _fake_synced(-100))

    result = sync_preview.sync_compare(
        original, video_path="/v/ep.mkv", reference_path="/v/ref.srt"
    )
    engines = {c["engine"] for c in result["candidates"]}
    assert engines == {"ffsubsync", "alass"}


def test_compare_surfaces_engine_failure(tmp_path, monkeypatch):
    original = _make_original(tmp_path)

    def _boom(_s, _r):
        raise RuntimeError("ffsubsync failed: bad audio")

    monkeypatch.setattr(sync_preview, "_run_ffsubsync_preview", _boom)

    result = sync_preview.sync_compare(original, video_path="/v/ep.mkv")
    ff = result["candidates"][0]
    assert ff["status"] == "error"
    assert "bad audio" in ff["error"]
    assert result["any_output"] is False


def test_compare_classifies_unavailable_and_rejected(tmp_path, monkeypatch):
    original = _make_original(tmp_path)

    def _unavailable(_s, _r):
        raise SyncUnavailableError("ffsubsync is not installed")

    def _rejected(_s, _r):
        raise SyncSanityThresholdError("shift 90000ms exceeds sanity threshold")

    monkeypatch.setattr(sync_preview, "_run_ffsubsync_preview", _unavailable)
    monkeypatch.setattr(sync_preview, "_run_alass_preview", _rejected)

    result = sync_preview.sync_compare(
        original, video_path="/v/ep.mkv", reference_path="/v/ref.srt"
    )
    by_engine = {c["engine"]: c for c in result["candidates"]}
    assert by_engine["ffsubsync"]["status"] == "unavailable"
    assert by_engine["alass"]["status"] == "rejected"
    assert result["any_output"] is False


def test_compare_no_engine_inputs_returns_no_output(tmp_path):
    original = _make_original(tmp_path)
    result = sync_preview.sync_compare(original)  # no video, no reference
    assert result["candidates"] == []
    assert result["any_output"] is False


def test_compare_cleans_up_temp_candidate_files(tmp_path, monkeypatch):
    original = _make_original(tmp_path)
    created: list[str] = []

    def _run(subtitle_path, _ref):
        fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        _write_srt(out, [(1500, 3500, "Hello")])
        created.append(out)
        return 500, out

    monkeypatch.setattr(sync_preview, "_run_ffsubsync_preview", _run)
    sync_preview.sync_compare(original, video_path="/v/ep.mkv")
    assert created and not any(Path(p).exists() for p in created)
