"""Comprehensive tests for backend/routes/tracks.py.

Covers list_tracks, extract_track, use_track_as_source,
_build_track_list, _normalise_stream, _cleanup_series_sidecars,
and batch_extract_series_tracks.
"""

import os
import tempfile
import time
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from config import reload_settings
from db import close_db, init_db
from routes.tracks import (
    _build_track_list,
    _cleanup_series_sidecars,
    _find_track,
    _normalise_stream,
)

# ---------------------------------------------------------------------------
# Sample ffprobe stream data
# ---------------------------------------------------------------------------

SAMPLE_STREAMS = [
    {"index": 0, "codec_type": "video", "codec_name": "h264", "tags": {}, "disposition": {}},
    {
        "index": 1,
        "codec_type": "audio",
        "codec_name": "aac",
        "tags": {"language": "jpn"},
        "disposition": {"default": 1, "forced": 0},
    },
    {
        "index": 2,
        "codec_type": "subtitle",
        "codec_name": "ass",
        "tags": {"language": "jpn", "title": "Japanese"},
        "disposition": {"default": 1, "forced": 0},
    },
    {
        "index": 3,
        "codec_type": "subtitle",
        "codec_name": "srt",
        "tags": {"language": "eng"},
        "disposition": {"default": 0, "forced": 0},
    },
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    os.environ["SUBLARR_PLUGINS_DIR"] = tempfile.mkdtemp()
    os.environ["SUBLARR_MEDIA_PATH"] = os.path.realpath(tempfile.gettempdir())
    reload_settings()
    init_db()
    app = create_app(testing=True)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
    close_db()
    try:
        if os.path.exists(db_path):
            os.unlink(db_path)
    except PermissionError:
        pass
    for key in (
        "SUBLARR_DB_PATH",
        "SUBLARR_API_KEY",
        "SUBLARR_LOG_LEVEL",
        "SUBLARR_PLUGINS_DIR",
        "SUBLARR_MEDIA_PATH",
    ):
        os.environ.pop(key, None)
    reload_settings()


# ===================================================================
# Unit tests for helper functions (no Flask client needed)
# ===================================================================


class TestNormaliseStream:
    """Tests for _normalise_stream."""

    def test_basic_subtitle(self):
        stream = {
            "codec_type": "subtitle",
            "codec_name": "ASS",
            "tags": {"language": "jpn", "title": "Japanese"},
            "disposition": {"default": 1, "forced": 0},
        }
        result = _normalise_stream(stream, 2, 0)
        assert result["index"] == 2
        assert result["sub_index"] == 0
        assert result["codec_type"] == "subtitle"
        assert result["codec"] == "ass"
        assert result["language"] == "jpn"
        assert result["title"] == "Japanese"
        assert result["default"] is True
        assert result["forced"] is False

    def test_missing_tags_returns_empty_strings(self):
        stream = {"codec_type": "audio", "codec_name": "aac"}
        result = _normalise_stream(stream, 1, 0)
        assert result["language"] == ""
        assert result["title"] == ""
        assert result["forced"] is False
        assert result["default"] is False

    def test_tags_none_returns_empty_strings(self):
        stream = {"codec_type": "subtitle", "codec_name": "srt", "tags": None, "disposition": None}
        result = _normalise_stream(stream, 3, 1)
        assert result["language"] == ""
        assert result["title"] == ""
        assert result["forced"] is False
        assert result["default"] is False

    def test_fallback_lang_key(self):
        """Falls back to 'lang' key when 'language' is absent."""
        stream = {"codec_type": "subtitle", "codec_name": "srt", "tags": {"lang": "ger"}}
        result = _normalise_stream(stream, 4, 2)
        assert result["language"] == "ger"

    def test_fallback_handler_name(self):
        """Falls back to 'handler_name' when 'title' is absent."""
        stream = {
            "codec_type": "audio",
            "codec_name": "aac",
            "tags": {"handler_name": "Audio Handler"},
        }
        result = _normalise_stream(stream, 1, 0)
        assert result["title"] == "Audio Handler"

    def test_codec_name_none(self):
        stream = {"codec_type": "subtitle", "codec_name": None}
        result = _normalise_stream(stream, 5, 0)
        assert result["codec"] == ""

    def test_missing_codec_type(self):
        stream = {"codec_name": "srt"}
        result = _normalise_stream(stream, 0, 0)
        assert result["codec_type"] == ""


class TestBuildTrackList:
    """Tests for _build_track_list."""

    def test_filters_video_streams(self):
        tracks = _build_track_list(SAMPLE_STREAMS)
        codec_types = {t["codec_type"] for t in tracks}
        assert "video" not in codec_types

    def test_counts_audio_and_subtitle(self):
        tracks = _build_track_list(SAMPLE_STREAMS)
        assert len(tracks) == 3  # 1 audio + 2 subtitles

    def test_sub_index_increments_independently(self):
        tracks = _build_track_list(SAMPLE_STREAMS)
        subtitles = [t for t in tracks if t["codec_type"] == "subtitle"]
        assert subtitles[0]["sub_index"] == 0
        assert subtitles[1]["sub_index"] == 1
        audios = [t for t in tracks if t["codec_type"] == "audio"]
        assert audios[0]["sub_index"] == 0

    def test_duplicate_index_uses_raw_index(self):
        """When two streams report the same abs index, the second gets raw_index."""
        streams = [
            {
                "index": 5,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "jpn"},
                "disposition": {},
            },
            {
                "index": 5,
                "codec_type": "subtitle",
                "codec_name": "srt",
                "tags": {"language": "eng"},
                "disposition": {},
            },
        ]
        tracks = _build_track_list(streams)
        indices = [t["index"] for t in tracks]
        assert len(set(indices)) == 2  # both have unique indices
        assert 5 in indices
        assert 1 in indices  # raw_index=1 for the second stream

    def test_empty_streams(self):
        assert _build_track_list([]) == []

    def test_only_video_streams(self):
        streams = [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "tags": {},
                "disposition": {},
            },
        ]
        assert _build_track_list(streams) == []

    def test_stream_without_codec_type(self):
        """Streams with missing codec_type are skipped."""
        streams = [{"index": 0, "codec_name": "srt"}]
        assert _build_track_list(streams) == []


class TestFindTrack:
    """Tests for _find_track."""

    def test_finds_existing_track(self):
        tracks = [{"index": 2, "codec": "ass"}, {"index": 3, "codec": "srt"}]
        result = _find_track(tracks, 2)
        assert result is not None
        assert result["codec"] == "ass"

    def test_returns_none_for_missing(self):
        tracks = [{"index": 2, "codec": "ass"}]
        assert _find_track(tracks, 99) is None

    def test_empty_list(self):
        assert _find_track([], 0) is None


# ===================================================================
# Route tests: list_tracks
# ===================================================================


class TestListTracks:
    """Tests for GET /library/episodes/<id>/tracks."""

    def test_returns_tracks_successfully(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
        ):
            resp = client.get("/api/v1/library/episodes/1/tracks")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["tracks"]) == 3
        assert data["video_path"] == "/media/ep.mkv"

    def test_404_no_video_path(self, client):
        with patch("routes.tracks._get_video_path", return_value=None):
            resp = client.get("/api/v1/library/episodes/99/tracks")
        assert resp.status_code == 404

    def test_404_file_missing_on_disk(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/missing.mkv"),
            patch("os.path.exists", return_value=False),
        ):
            resp = client.get("/api/v1/library/episodes/1/tracks")
        assert resp.status_code == 404
        assert "not found on disk" in resp.get_json()["error"]

    def test_500_runtime_error_from_probe(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=RuntimeError("ffprobe not found"),
            ),
        ):
            resp = client.get("/api/v1/library/episodes/1/tracks")
        assert resp.status_code == 500
        assert "ffprobe not found" in resp.get_json()["error"]

    def test_500_unexpected_exception_from_probe(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=ValueError("unexpected"),
            ),
        ):
            resp = client.get("/api/v1/library/episodes/1/tracks")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Internal server error"

    def test_empty_streams_returns_empty_list(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": []}),
        ):
            resp = client.get("/api/v1/library/episodes/1/tracks")
        assert resp.status_code == 200
        assert resp.get_json()["tracks"] == []


# ===================================================================
# Route tests: extract_track
# ===================================================================


class TestExtractTrack:
    """Tests for POST /library/episodes/<id>/tracks/<idx>/extract."""

    def test_successful_extraction(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch("routes.tracks.extract_subtitle_stream") as mock_ext,
        ):
            resp = client.post(
                "/api/v1/library/episodes/1/tracks/2/extract", json={"language": "jpn"}
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["output_path"].endswith(".jpn.ass")
        assert data["format"] == "ass"
        assert mock_ext.called

    def test_srt_codec_extraction(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/3/extract")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["format"] == "srt"
        assert data["language"] == "eng"

    def test_language_override_from_body(self, client):
        """Body language overrides the track language."""
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post(
                "/api/v1/library/episodes/1/tracks/2/extract", json={"language": "de"}
            )
        data = resp.get_json()
        assert data["language"] == "de"
        assert data["output_path"].endswith(".de.ass")

    def test_fallback_language_und(self, client):
        """When no language in body or track, defaults to 'und'."""
        no_lang_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {},
                "disposition": {},
            },
        ]
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": no_lang_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract", json={})
        data = resp.get_json()
        assert data["language"] == "und"

    def test_404_no_video_path(self, client):
        with patch("routes.tracks._get_video_path", return_value=None):
            resp = client.post("/api/v1/library/episodes/99/tracks/0/extract")
        assert resp.status_code == 404

    def test_404_file_missing_on_disk(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/missing.mkv"),
            patch("os.path.exists", return_value=False),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 404

    def test_404_track_not_found(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/99/extract")
        assert resp.status_code == 404

    def test_400_audio_track(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/1/extract")
        assert resp.status_code == 400
        assert "subtitle" in resp.get_json()["error"].lower()

    def test_500_runtime_error_from_probe(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=RuntimeError("probe failed"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 500
        assert "probe failed" in resp.get_json()["error"]

    def test_500_unexpected_probe_exception(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=TypeError("oops"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Internal server error"

    def test_500_extraction_runtime_error(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=RuntimeError("mkvextract failed"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/extract")
        assert resp.status_code == 500
        assert "mkvextract failed" in resp.get_json()["error"]

    def test_500_extraction_unexpected_error(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=MemoryError("out of memory"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/extract")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Internal server error"

    def test_no_body_defaults(self, client):
        """Request with no JSON body still works."""
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post(
                "/api/v1/library/episodes/1/tracks/2/extract",
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        # Falls back to track language "jpn"
        assert data["language"] == "jpn"


# ===================================================================
# Route tests: use_track_as_source
# ===================================================================


class TestUseTrackAsSource:
    """Tests for POST /library/episodes/<id>/tracks/<idx>/use-as-source."""

    def _fake_extract(self, content="[Script Info]\nTitle: Test\n"):
        def _extract(video_path, stream_info, output_path):
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)

        return _extract

    def test_successful_extraction(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=self._fake_extract(),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["content"] == "[Script Info]\nTitle: Test\n"
        assert data["format"] == "ass"
        assert data["language"] == "jpn"
        assert data["title"] == "Japanese"

    def test_und_language_fallback(self, client):
        """Track with no language tag defaults to 'und'."""
        no_lang = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {},
                "disposition": {},
            },
        ]
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": no_lang}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=self._fake_extract(),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/use-as-source")
        assert resp.status_code == 200
        assert resp.get_json()["language"] == "und"

    def test_404_no_video_path(self, client):
        with patch("routes.tracks._get_video_path", return_value=None):
            resp = client.post("/api/v1/library/episodes/99/tracks/0/use-as-source")
        assert resp.status_code == 404

    def test_404_file_missing_on_disk(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/missing.mkv"),
            patch("os.path.exists", return_value=False),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/use-as-source")
        assert resp.status_code == 404

    def test_404_track_not_found(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/99/use-as-source")
        assert resp.status_code == 404

    def test_400_audio_track(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/1/use-as-source")
        assert resp.status_code == 400
        assert "subtitle" in resp.get_json()["error"].lower()

    def test_500_runtime_error_from_probe(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=RuntimeError("probe error"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/use-as-source")
        assert resp.status_code == 500
        assert "probe error" in resp.get_json()["error"]

    def test_500_unexpected_probe_exception(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=KeyError("bad"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/use-as-source")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Internal server error"

    def test_500_extraction_runtime_error(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=RuntimeError("extract boom"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
        assert resp.status_code == 500
        assert "extract boom" in resp.get_json()["error"]

    def test_500_os_error(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=OSError("disk full"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
        assert resp.status_code == 500
        assert "disk full" in resp.get_json()["error"]

    def test_500_unexpected_extraction_error(self, client):
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=MemoryError("oom"),
            ),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "Internal server error"

    def test_tempfile_cleaned_up_on_success(self, client):
        """Verify the temp file is deleted after reading."""
        created_paths = []

        def _extract_and_record(video_path, stream_info, output_path):
            created_paths.append(output_path)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("content")

        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": SAMPLE_STREAMS}),
            patch("routes.tracks.extract_subtitle_stream", side_effect=_extract_and_record),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/2/use-as-source")
        assert resp.status_code == 200
        # Temp file should have been cleaned up
        for p in created_paths:
            assert not os.path.exists(p)


# ===================================================================
# Tests for _cleanup_series_sidecars
# ===================================================================


class TestCleanupSeriesSidecars:
    """Tests for _cleanup_series_sidecars."""

    def test_deletes_unwanted_languages(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_text("fake video")
        srt_de = tmp_path / "ep.de.srt"
        srt_de.write_text("srt content")
        srt_fr = tmp_path / "ep.fr.srt"
        srt_fr.write_text("srt content")

        sidecars = [
            {"language": "de", "format": "srt", "path": str(srt_de)},
            {"language": "fr", "format": "srt", "path": str(srt_fr)},
        ]

        episode_files = {1: {"path": str(video)}}

        with (
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.subtitles.scan_subtitle_sidecars", return_value=sidecars),
        ):
            deleted = _cleanup_series_sidecars(episode_files, {"de"}, "any")

        assert deleted == 1  # only "fr" deleted
        assert srt_de.exists()
        assert not srt_fr.exists()

    def test_prefer_ass_deletes_srt_when_ass_exists(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_text("fake video")
        ass_de = tmp_path / "ep.de.ass"
        ass_de.write_text("ass content")
        srt_de = tmp_path / "ep.de.srt"
        srt_de.write_text("srt content")

        sidecars = [
            {"language": "de", "format": "ass", "path": str(ass_de)},
            {"language": "de", "format": "srt", "path": str(srt_de)},
        ]
        episode_files = {1: {"path": str(video)}}

        with (
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.subtitles.scan_subtitle_sidecars", return_value=sidecars),
        ):
            deleted = _cleanup_series_sidecars(episode_files, {"de"}, "ass")

        assert deleted == 1
        assert ass_de.exists()
        assert not srt_de.exists()

    def test_no_deletion_when_all_in_keep(self, tmp_path):
        video = tmp_path / "ep.mkv"
        video.write_text("fake video")

        sidecars = [
            {"language": "de", "format": "ass", "path": str(tmp_path / "ep.de.ass")},
        ]
        (tmp_path / "ep.de.ass").write_text("content")
        episode_files = {1: {"path": str(video)}}

        with (
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.subtitles.scan_subtitle_sidecars", return_value=sidecars),
        ):
            deleted = _cleanup_series_sidecars(episode_files, {"de"}, "any")

        assert deleted == 0

    def test_skips_missing_video(self, tmp_path):
        episode_files = {1: {"path": str(tmp_path / "nonexistent.mkv")}}
        deleted = _cleanup_series_sidecars(episode_files, {"de"}, "any")
        assert deleted == 0

    def test_skips_empty_path(self):
        episode_files = {1: {"path": ""}, 2: {}}
        deleted = _cleanup_series_sidecars(episode_files, {"de"}, "any")
        assert deleted == 0

    def test_handles_os_error_on_unlink(self, tmp_path):
        """OSError during unlink is caught and does not crash."""
        video = tmp_path / "ep.mkv"
        video.write_text("fake video")

        sidecars = [
            {"language": "fr", "format": "srt", "path": str(tmp_path / "ep.fr.srt")},
        ]
        (tmp_path / "ep.fr.srt").write_text("content")
        episode_files = {1: {"path": str(video)}}

        with (
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.subtitles.scan_subtitle_sidecars", return_value=sidecars),
            patch("os.unlink", side_effect=OSError("permission denied")),
        ):
            deleted = _cleanup_series_sidecars(episode_files, {"de"}, "any")

        assert deleted == 0  # unlink failed, so count stays 0


# ===================================================================
# Route tests: batch_extract_series_tracks
# ===================================================================


class TestBatchExtractSeriesTracks:
    """Tests for POST /library/series/<id>/batch-extract-tracks."""

    def test_returns_202_immediately(self, client):
        """Endpoint returns 202 and spawns background thread."""
        with patch("routes.tracks.threading.Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/v1/library/series/1/batch-extract-tracks")
        assert resp.status_code == 202
        data = resp.get_json()
        assert data["status"] == "started"
        assert data["series_id"] == 1
        mock_thread.return_value.start.assert_called_once()

    def test_background_extracts_subtitles(self, client):
        """Full integration of background thread logic with Sonarr client."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/ep01.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test Anime"}

        sub_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "jpn"},
                "disposition": {},
            },
        ]

        _extract_calls = {"sidecar": 0}

        def _exists_for_extract(path):
            # Return True for the video path, False for sidecar pre-check,
            # True for sidecar post-check
            if path == "/media/ep01.mkv":
                return True
            _extract_calls["sidecar"] += 1
            return _extract_calls["sidecar"] > 1

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.get_media_streams", return_value={"streams": sub_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
            patch("routes.tracks.remove_subtitle_streams", return_value="/media/ep01.mkv.bak"),
            patch("routes.tracks.emit_event"),
            patch("routes.tracks.os.path.exists", side_effect=_exists_for_extract),
            patch("routes.tracks.os.path.getsize", return_value=500),
            patch("db.jobs.create_job", return_value={"id": "abc123"}),
            patch("db.jobs.update_job"),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            resp = client.post("/api/v1/library/series/1/batch-extract-tracks")

            assert resp.status_code == 202

            # Extract the _run function and call it
            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

    def test_background_sonarr_error_emits_event(self, client):
        """When Sonarr raises an exception, emit completed event with zero counts."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.side_effect = Exception("Sonarr down")

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        # Check that batch_extract_completed was emitted with zeros
        completed_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_completed"
        ]
        assert len(completed_calls) == 1
        event_data = completed_calls[0][0][1]
        assert event_data["total"] == 0
        assert event_data["succeeded"] == 0

    def test_background_no_files_emits_completed(self, client):
        """When Sonarr returns empty file list, emit completed with zeros."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {}

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        completed_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_completed"
        ]
        assert len(completed_calls) == 1
        assert completed_calls[0][0][1]["total"] == 0

    def test_background_skips_missing_file(self, client):
        """Files not on disk are skipped."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/missing.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("routes.tracks.os.path.exists", return_value=False),
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job"),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        progress_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_progress"
        ]
        assert len(progress_calls) == 1
        assert progress_calls[0][0][1]["status"] == "skipped"

    def test_background_probe_failure(self, client):
        """Probe failure for a file counts as failed."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/bad.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch(
                "routes.tracks.get_media_streams",
                side_effect=RuntimeError("corrupt file"),
            ),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("routes.tracks.os.path.exists", return_value=True),
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job"),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        progress_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_progress"
        ]
        assert len(progress_calls) == 1
        assert progress_calls[0][0][1]["status"] == "failed"

    def test_background_empty_sidecar_counted_as_failed(self, client):
        """When extracted sidecar is <10 bytes, it is removed and counted as failed."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/ep.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        sub_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "jpn"},
                "disposition": {},
            },
        ]

        # exists must return True for the video, False for the sidecar pre-check,
        # then True for the sidecar post-extraction check
        call_count = {"n": 0}

        def _exists_side(path):
            if path == "/media/ep.mkv":
                return True
            # First call for sidecar = pre-extract check (should not exist yet)
            # Second call for sidecar = post-extract check (should exist)
            call_count["n"] += 1
            return call_count["n"] > 1

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.get_media_streams", return_value={"streams": sub_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
            patch("routes.tracks.os.path.exists", side_effect=_exists_side),
            patch("routes.tracks.os.path.getsize", return_value=5),  # <10 bytes
            patch("routes.tracks.os.unlink"),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job") as mock_update_job,
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        completed_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_completed"
        ]
        assert completed_calls[0][0][1]["failed"] == 1
        assert completed_calls[0][0][1]["succeeded"] == 0

        # Job should be finalized as "failed" (0 succeeded, >0 failed)
        update_calls = mock_update_job.call_args_list
        final_call = update_calls[-1]
        assert final_call[0][1] == "failed"

    def test_background_extract_exception_counted_as_failed(self, client):
        """When extract_subtitle_stream raises, the track is counted as failed."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/ep.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        sub_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "jpn"},
                "disposition": {},
            },
        ]

        def _exists_extract_fail(path):
            return path == "/media/ep.mkv"

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.get_media_streams", return_value={"streams": sub_streams}),
            patch(
                "routes.tracks.extract_subtitle_stream",
                side_effect=RuntimeError("extract fail"),
            ),
            patch("routes.tracks.os.path.exists", side_effect=_exists_extract_fail),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job"),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        completed_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_completed"
        ]
        assert completed_calls[0][0][1]["failed"] == 1

    def test_background_remux_error_does_not_crash(self, client):
        """RemuxError during stream removal is logged but does not abort."""
        from remux import RemuxError

        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/ep.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        sub_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "ass",
                "tags": {"language": "jpn"},
                "disposition": {},
            },
        ]

        # exists: True for video, False for pre-extract sidecar check (line 397),
        # True for post-extract sidecar check (line 405)
        _remux_calls = {"sidecar": 0}

        def _exists_remux(path):
            if path == "/media/ep.mkv":
                return True
            # sidecar path: first call = pre-extract (False), second = post-extract (True)
            _remux_calls["sidecar"] += 1
            return _remux_calls["sidecar"] > 1

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.get_media_streams", return_value={"streams": sub_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
            patch("routes.tracks.os.path.exists", side_effect=_exists_remux),
            patch("routes.tracks.os.path.getsize", return_value=500),
            patch(
                "routes.tracks.remove_subtitle_streams",
                side_effect=RemuxError("mkvmerge error"),
            ),
            patch("routes.tracks.emit_event") as mock_emit,
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job"),
            patch("routes.tracks.threading.Thread") as mock_thread,
        ):
            mock_thread.return_value.start = MagicMock()
            client.post("/api/v1/library/series/1/batch-extract-tracks")

            call_args = mock_thread.call_args
            target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
            app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
            target_fn(app_arg)

        # Should still complete successfully despite RemuxError
        completed_calls = [
            c for c in mock_emit.call_args_list if c[0][0] == "batch_extract_completed"
        ]
        assert len(completed_calls) == 1
        assert completed_calls[0][0][1]["succeeded"] == 1

    def test_background_auto_cleanup(self, client):
        """When auto_cleanup_after_extract is enabled, sidecars are cleaned."""
        mock_client = MagicMock()
        mock_client.get_episode_files_by_series.return_value = {
            1: {"path": "/media/ep.mkv"},
        }
        mock_client.get_series_by_id.return_value = {"title": "Test"}

        # No subtitle tracks — just testing the cleanup path runs
        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", side_effect=lambda p: p),
            patch("routes.tracks.get_media_streams", return_value={"streams": []}),
            patch("routes.tracks.os.path.exists", return_value=True),
            patch("routes.tracks.emit_event"),
            patch("db.jobs.create_job", return_value={"id": "j1"}),
            patch("db.jobs.update_job"),
            patch("config.get_settings") as mock_settings,
            patch("routes.tracks._cleanup_series_sidecars", return_value=3) as mock_cleanup,
        ):
            settings_obj = MagicMock()
            settings_obj.auto_cleanup_after_extract = True
            settings_obj.auto_cleanup_keep_languages = "de,en"
            settings_obj.auto_cleanup_keep_formats = "ass"
            mock_settings.return_value = settings_obj

            with patch("routes.tracks.threading.Thread") as mock_thread:
                mock_thread.return_value.start = MagicMock()
                client.post("/api/v1/library/series/1/batch-extract-tracks")

                call_args = mock_thread.call_args
                target_fn = call_args[1]["target"] if "target" in call_args[1] else call_args[0][0]
                app_arg = call_args[1]["args"][0] if "args" in call_args[1] else call_args[0][1][0]
                target_fn(app_arg)

            mock_cleanup.assert_called_once()
            cleanup_args = mock_cleanup.call_args[0]
            assert cleanup_args[1] == {"de", "en"}
            assert cleanup_args[2] == "ass"


# ===================================================================
# Tests for _get_video_path
# ===================================================================


class TestGetVideoPath:
    """Tests for _get_video_path helper."""

    def test_returns_mapped_path(self, client):
        from routes.tracks import _get_video_path

        mock_client = MagicMock()
        mock_client.get_episode_file_path.return_value = "/sonarr/media/ep.mkv"

        with (
            patch("sonarr_client.get_sonarr_client", return_value=mock_client),
            patch("routes.tracks.map_path", return_value="/local/media/ep.mkv"),
        ):
            result = _get_video_path(42)

        assert result == "/local/media/ep.mkv"
        mock_client.get_episode_file_path.assert_called_once_with(42)

    def test_returns_none_when_client_is_none(self, client):
        from routes.tracks import _get_video_path

        with patch("sonarr_client.get_sonarr_client", return_value=None):
            result = _get_video_path(42)

        assert result is None

    def test_returns_none_when_no_path(self, client):
        from routes.tracks import _get_video_path

        mock_client = MagicMock()
        mock_client.get_episode_file_path.return_value = None

        with patch("sonarr_client.get_sonarr_client", return_value=mock_client):
            result = _get_video_path(42)

        assert result is None


# ===================================================================
# Codec extension mapping
# ===================================================================


class TestCodecExtMapping:
    """Verify _CODEC_EXT mapping is used correctly."""

    def test_webvtt_codec(self, client):
        webvtt_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "webvtt",
                "tags": {"language": "eng"},
                "disposition": {},
            },
        ]
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": webvtt_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 200
        assert resp.get_json()["format"] == "vtt"

    def test_mov_text_codec(self, client):
        mov_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "mov_text",
                "tags": {"language": "eng"},
                "disposition": {},
            },
        ]
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mp4"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": mov_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 200
        assert resp.get_json()["format"] == "srt"

    def test_unknown_codec_defaults_to_ass(self, client):
        unknown_streams = [
            {
                "index": 0,
                "codec_type": "subtitle",
                "codec_name": "dvd_subtitle",
                "tags": {"language": "eng"},
                "disposition": {},
            },
        ]
        with (
            patch("routes.tracks._get_video_path", return_value="/media/ep.mkv"),
            patch("os.path.exists", return_value=True),
            patch("routes.tracks.get_media_streams", return_value={"streams": unknown_streams}),
            patch("routes.tracks.extract_subtitle_stream"),
        ):
            resp = client.post("/api/v1/library/episodes/1/tracks/0/extract")
        assert resp.status_code == 200
        assert resp.get_json()["format"] == "ass"
