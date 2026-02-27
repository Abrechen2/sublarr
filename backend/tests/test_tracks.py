"""Tests for backend/routes/tracks.py."""

import os
import tempfile
from unittest.mock import patch

import pytest

from app import create_app
from config import reload_settings
from db import close_db

SAMPLE_STREAMS = [
    {"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {}, "disposition": {}},
    {"index": 1, "codec_type": "audio", "codec_name": "aac", "tags": {"language": "jpn"}, "disposition": {"default": 1, "forced": 0}},
    {"index": 2, "codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "jpn", "title": "Japanese"}, "disposition": {"default": 1, "forced": 0}},
    {"index": 3, "codec_type": "subtitle", "codec_name": "srt", "tags": {"language": "eng"}, "disposition": {"default": 0, "forced": 0}},
]


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    reload_settings()
    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    close_db()
    try:
        if os.path.exists(db_path):
            os.unlink(db_path)
    except PermissionError:
        pass  # Windows: SQLite WAL may hold a brief lock; file cleaned by OS
    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)


def test_list_tracks_returns_all_tracks(client):
    """GET /tracks returns audio and subtitle tracks with correct structure."""
    fake_path = "/media/ep.mkv"
    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}):
        resp = client.get("/api/v1/library/episodes/1/tracks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tracks" in data
    assert "video_path" in data
    tracks = data["tracks"]
    assert len(tracks) == 3
    codecs = {t["codec"] for t in tracks}
    assert "ass" in codecs
    assert "aac" in codecs
    for t in tracks:
        for field in ("index", "codec_type", "language", "forced", "default"):
            assert field in t


def test_list_tracks_404_when_no_file(client):
    """GET /tracks returns 404 if episode has no video file."""
    with patch("routes.tracks._get_video_path", return_value=None):
        resp = client.get("/api/v1/library/episodes/99/tracks")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_list_tracks_404_file_missing_on_disk(client):
    """GET /tracks returns 404 if the video file does not exist on disk."""
    with patch("routes.tracks._get_video_path", return_value="/missing.mkv"), \
         patch("os.path.exists", return_value=False):
        resp = client.get("/api/v1/library/episodes/1/tracks")
    assert resp.status_code == 404


def test_extract_subtitle_track_returns_output_path(client):
    """POST /extract returns 200 with correct output_path for subtitle track."""
    fake_path = "/media/ep.mkv"
    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}), \
         patch("routes.tracks.extract_subtitle_stream") as mock_ext:
        resp = client.post("/api/v1/library/episodes/1/tracks/2/extract",
                           json={"language": "jpn"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "output_path" in data
    assert data["language"] == "jpn"
    assert data["format"] == "ass"
    assert data["output_path"].endswith(".jpn.ass")
    assert mock_ext.called


def test_extract_audio_track_returns_400(client):
    """POST /extract returns 400 when the track is an audio stream."""
    fake_path = "/media/ep.mkv"
    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}):
        resp = client.post("/api/v1/library/episodes/1/tracks/1/extract")
    assert resp.status_code == 400
    assert "subtitle" in resp.get_json()["error"].lower()


def test_extract_unknown_index_returns_404(client):
    """POST /extract returns 404 when track index is not present."""
    fake_path = "/media/ep.mkv"
    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}):
        resp = client.post("/api/v1/library/episodes/1/tracks/99/extract")
    assert resp.status_code == 404


def test_use_as_source_returns_content(client):
    """POST /use-as-source returns subtitle content inline."""
    fake_path = "/media/ep.mkv"
    fake_content = "[Script Info]\nTitle: Test\n"
    def fake_extract(video_path, stream_info, output_path):
        with open(output_path, "w") as f:
            f.write(fake_content)

    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}), \
         patch("routes.tracks.extract_subtitle_stream", side_effect=fake_extract):
        resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "content" in data
    assert data["content"] == fake_content
    assert data["format"] == "ass"
    assert data["language"] == "jpn"


def test_use_as_source_audio_returns_400(client):
    """POST /use-as-source returns 400 for an audio track."""
    fake_path = "/media/ep.mkv"
    with patch("routes.tracks._get_video_path", return_value=fake_path), \
         patch("os.path.exists", return_value=True), \
         patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}):
        resp = client.post("/api/v1/library/episodes/1/tracks/1/use-as-source")
    assert resp.status_code == 400
