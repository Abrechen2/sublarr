"""Tests for /tools/convert subtitle format conversion endpoint."""

import os
import pytest


@pytest.fixture
def media_srt(tmp_path, monkeypatch):
    """Create a minimal SRT file under a temp media_path."""
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    srt = tmp_path / "ep.de.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    return srt


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
