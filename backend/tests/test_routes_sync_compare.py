"""HTTP tests for POST /api/v1/tools/video-sync/compare (V1.6 #4)."""

import os
from pathlib import Path

import pysubs2


def _write_srt(path, cues):
    subs = pysubs2.SSAFile()
    for start, end, text in cues:
        ev = pysubs2.SSAEvent(start=start, end=end)
        ev.plaintext = text
        subs.events.append(ev)
    subs.save(str(path), format_="srt")


def test_compare_requires_file_path(client):
    resp = client.post("/api/v1/tools/video-sync/compare", json={})
    assert resp.status_code == 400


def test_compare_missing_file_404(client, temp_dir):
    resp = client.post(
        "/api/v1/tools/video-sync/compare",
        json={"file_path": os.path.join(temp_dir, "nope.srt"), "video_path": "/v.mkv"},
    )
    assert resp.status_code == 404


def test_compare_requires_a_reference(client, temp_dir):
    sub = os.path.join(temp_dir, "ep.en.srt")
    _write_srt(sub, [(1000, 2000, "Hi")])
    resp = client.post("/api/v1/tools/video-sync/compare", json={"file_path": sub})
    assert resp.status_code == 400  # no video_path and no reference_path


def test_compare_returns_candidates(client, temp_dir, monkeypatch):
    sub = os.path.join(temp_dir, "ep.en.srt")
    _write_srt(sub, [(1000, 3000, "Hello")])
    video = os.path.join(temp_dir, "ep.mkv")
    Path(video).touch()

    def _fake_run(subtitle_path, _video):
        import tempfile

        fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(fd)
        _write_srt(out, [(1500, 3500, "Hello")])
        return 500, out

    monkeypatch.setattr("services.sync_preview._run_ffsubsync_preview", _fake_run)

    resp = client.post(
        "/api/v1/tools/video-sync/compare",
        json={"file_path": sub, "video_path": video},
    )
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["any_output"] is True
    assert data["original"][0]["start"] == 1000
    ff = data["candidates"][0]
    assert ff["engine"] == "ffsubsync"
    assert ff["status"] == "ok"
    assert ff["cues"][0]["start"] == 1500
