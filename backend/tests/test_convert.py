"""Tests for /tools/convert subtitle format conversion endpoint."""

import os

import pytest

from config import reload_settings


@pytest.fixture
def media_srt(tmp_path, monkeypatch):
    """Create a minimal SRT file under a temp media_path."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    srt = tmp_path / "ep.de.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    yield srt
    reload_settings()  # restore clean state


def test_convert_srt_to_ass(client, media_srt):
    r = client.post(
        "/api/v1/tools/convert",
        json={"file_path": str(media_srt), "target_format": "ass"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["format"] == "ass"
    output = media_srt.parent / "ep.de.converted.ass"
    assert output.exists()


def test_convert_srt_to_vtt(client, media_srt):
    r = client.post(
        "/api/v1/tools/convert",
        json={"file_path": str(media_srt), "target_format": "vtt"},
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["format"] == "vtt"


def test_convert_invalid_format(client, media_srt):
    r = client.post(
        "/api/v1/tools/convert",
        json={"file_path": str(media_srt), "target_format": "xyz"},
    )
    assert r.status_code == 400
    assert "target_format" in r.get_json()["error"]


def test_convert_missing_file(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    r = client.post(
        "/api/v1/tools/convert",
        json={"file_path": str(tmp_path / "nonexistent.srt"), "target_format": "ass"},
    )
    assert r.status_code == 404


def test_convert_missing_params(client):
    r = client.post("/api/v1/tools/convert", json={"target_format": "ass"})
    assert r.status_code == 400


def test_convert_missing_target_format(client, media_srt):
    r = client.post(
        "/api/v1/tools/convert",
        json={"file_path": str(media_srt)},
    )
    assert r.status_code == 400


def test_convert_file_path_outside_media_path_403(client, tmp_path, monkeypatch):
    """Regression: /tools/convert was missing the is_safe_path gate. A user
    could read any subtitle-parseable file the container had access to and
    write a converted output back to that path. Now it must 403."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(media_dir))
    reload_settings()
    try:
        outside = tmp_path / "outside.srt"
        outside.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
        r = client.post(
            "/api/v1/tools/convert",
            json={"file_path": str(outside), "target_format": "ass"},
        )
        assert r.status_code == 403
        assert "media_path" in r.get_json()["error"]
    finally:
        reload_settings()


def test_convert_video_path_outside_media_path_403(client, tmp_path, monkeypatch):
    """Same gate must cover the embedded-track branch (video_path)."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(media_dir))
    reload_settings()
    try:
        outside_video = tmp_path / "outside.mkv"
        outside_video.write_bytes(b"fake")
        r = client.post(
            "/api/v1/tools/convert",
            json={
                "video_path": str(outside_video),
                "track_index": 0,
                "target_format": "srt",
            },
        )
        assert r.status_code == 403
        assert "media_path" in r.get_json()["error"]
    finally:
        reload_settings()
