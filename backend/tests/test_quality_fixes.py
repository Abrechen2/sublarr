"""Tests for quality fix endpoints: /tools/overlap-fix, /tools/timing-normalize, /tools/merge-lines, /tools/split-lines."""

import pysubs2
import pytest


def _make_srt(tmp_path, content: str) -> str:
    p = tmp_path / "test.srt"
    p.write_text(content, encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def set_media_path(tmp_path, monkeypatch):
    """Set SUBLARR_MEDIA_PATH so _validate_file_path accepts tmp_path files."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))


def test_overlap_fix(client, tmp_path):
    srt_content = (
        "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
        "2\n00:00:02,000 --> 00:00:04,000\nWorld\n\n"
    )
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/overlap-fix", json={"file_path": path})
    assert r.status_code == 200
    body = r.get_json()
    assert body["fixed"] == 1
    subs = pysubs2.load(path)
    assert subs[0].end <= subs[1].start


def test_overlap_fix_no_overlaps(client, tmp_path):
    srt_content = (
        "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\nWorld\n\n"
    )
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/overlap-fix", json={"file_path": path})
    assert r.status_code == 200
    assert r.get_json()["fixed"] == 0


def test_timing_normalize_extends_short_cue(client, tmp_path):
    srt_content = "1\n00:00:01,000 --> 00:00:01,100\nHi\n\n"
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/timing-normalize",
                    json={"file_path": path, "min_ms": 500})
    assert r.status_code == 200
    assert r.get_json()["extended"] == 1
    subs = pysubs2.load(path)
    assert subs[0].end - subs[0].start >= 500


def test_timing_normalize_reports_too_long(client, tmp_path):
    srt_content = "1\n00:00:01,000 --> 00:00:12,000\nLong\n\n"
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/timing-normalize",
                    json={"file_path": path, "min_ms": 500, "max_ms": 5000})
    assert r.status_code == 200
    assert r.get_json()["too_long"] == 1


def test_merge_lines(client, tmp_path):
    srt_content = (
        "1\n00:00:01,000 --> 00:00:01,500\nA\n\n"
        "2\n00:00:01,600 --> 00:00:02,000\nB\n\n"
    )
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/merge-lines", json={"file_path": path, "gap_ms": 200})
    assert r.status_code == 200
    assert r.get_json()["merged"] == 1
    subs = pysubs2.load(path)
    assert len(subs) == 1


def test_merge_lines_no_merge_large_gap(client, tmp_path):
    srt_content = (
        "1\n00:00:01,000 --> 00:00:01,500\nA\n\n"
        "2\n00:00:05,000 --> 00:00:06,000\nB\n\n"
    )
    path = _make_srt(tmp_path, srt_content)
    r = client.post("/api/v1/tools/merge-lines", json={"file_path": path, "gap_ms": 200})
    assert r.status_code == 200
    assert r.get_json()["merged"] == 0


def test_quality_fix_missing_file(client, tmp_path):
    r = client.post("/api/v1/tools/overlap-fix",
                    json={"file_path": str(tmp_path / "missing.srt")})
    assert r.status_code == 404
