"""Tests for `list_audio_tracks` service + GET /api/v1/audio/tracks route.

Plan B8 Task 1 — exposes the audio-track picker that the WaveformEditor
uses to switch between language tracks (Center for Dialog vs.
international audio).
"""

from __future__ import annotations

import os
from unittest.mock import patch

# ─── Service: list_audio_tracks ────────────────────────────────────────────

SAMPLE_PROBE = {
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "tags": {},
            "disposition": {},
        },
        {
            "index": 1,
            "codec_type": "audio",
            "codec_name": "aac",
            "channels": 2,
            "tags": {"language": "jpn", "title": "Stereo"},
            "disposition": {"default": 1, "forced": 0},
        },
        {
            "index": 2,
            "codec_type": "audio",
            "codec_name": "ac3",
            "channels": 6,
            "tags": {"language": "eng", "title": "5.1 Surround"},
            "disposition": {"default": 0, "forced": 0},
        },
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "ass",
            "tags": {"language": "jpn"},
            "disposition": {},
        },
    ]
}


class TestListAudioTracks:
    def test_returns_only_audio_streams(self):
        """Video and subtitle streams are filtered out."""
        from services.audio_visualizer import list_audio_tracks

        with patch("services.audio_visualizer.get_media_streams", return_value=SAMPLE_PROBE):
            tracks = list_audio_tracks("/media/ep.mkv")

        assert len(tracks) == 2
        assert all(t["codec_type"] == "audio" for t in tracks)

    def test_normalizes_track_shape(self):
        """Each track exposes index, codec, channels, language, title, default, forced."""
        from services.audio_visualizer import list_audio_tracks

        with patch("services.audio_visualizer.get_media_streams", return_value=SAMPLE_PROBE):
            tracks = list_audio_tracks("/media/ep.mkv")

        first = tracks[0]
        assert first["index"] == 1
        assert first["codec"] == "aac"
        assert first["channels"] == 2
        assert first["language"] == "jpn"
        assert first["title"] == "Stereo"
        assert first["default"] is True
        assert first["forced"] is False

    def test_handles_missing_tags_and_disposition(self):
        """Streams without tags/disposition return empty strings + False flags."""
        from services.audio_visualizer import list_audio_tracks

        sparse = {
            "streams": [
                {"index": 0, "codec_type": "audio", "codec_name": "opus", "channels": 1},
            ]
        }
        with patch("services.audio_visualizer.get_media_streams", return_value=sparse):
            tracks = list_audio_tracks("/media/ep.mkv")

        assert len(tracks) == 1
        track = tracks[0]
        assert track["language"] == ""
        assert track["title"] == ""
        assert track["default"] is False
        assert track["forced"] is False
        assert track["channels"] == 1

    def test_empty_probe_returns_empty_list(self):
        from services.audio_visualizer import list_audio_tracks

        with patch("services.audio_visualizer.get_media_streams", return_value={"streams": []}):
            tracks = list_audio_tracks("/media/ep.mkv")

        assert tracks == []


# ─── Route: GET /api/v1/audio/tracks ───────────────────────────────────────


def _media_root() -> str:
    return os.environ.get("SUBLARR_MEDIA_PATH", os.path.realpath("/tmp"))


class TestAudioTracksRoute:
    def test_requires_file_path_param(self, client):
        resp = client.get("/api/v1/audio/tracks")
        assert resp.status_code == 400
        assert "file_path" in resp.get_json()["error"]

    def test_rejects_path_traversal(self, client):
        resp = client.get("/api/v1/audio/tracks?file_path=/etc/passwd")
        assert resp.status_code == 403

    def test_returns_404_for_missing_file(self, client, tmp_path):
        # Path inside media_root but the file does not exist
        fake = tmp_path / "missing.mkv"
        resp = client.get(f"/api/v1/audio/tracks?file_path={fake}")
        assert resp.status_code == 404

    def test_returns_tracks_for_existing_file(self, client, tmp_path):
        # Create an empty file inside the media root and mock the probe
        video = tmp_path / "ep.mkv"
        video.write_bytes(b"\x00")  # ffprobe will be mocked, content ignored

        with patch("services.audio_visualizer.get_media_streams", return_value=SAMPLE_PROBE):
            resp = client.get(f"/api/v1/audio/tracks?file_path={video}")

        assert resp.status_code == 200
        body = resp.get_json()
        assert "tracks" in body
        assert len(body["tracks"]) == 2
        assert body["video_path"] == str(video)
