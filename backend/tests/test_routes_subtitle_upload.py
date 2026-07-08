"""HTTP tests for routes/subtitles/upload.py — manual subtitle upload endpoints.

Covers the two POST endpoints wired in Task 3 of the manual-upload plan:
  POST /api/v1/library/episodes/<ep_id>/subtitles/upload
  POST /api/v1/library/movies/<movie_id>/subtitles/upload

These are the first live callers of services.subtitle_upload.prepare_upload —
Task 1/2 unit tests exercised prepare_upload/save_manual_subtitle directly but
had no Flask/DB context, so they could not verify the subtitle_downloads
history row. These integration tests run with the real app/client fixture
(temp_db) and can, and do, query that row.
"""

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.subtitle_upload import MAX_UPLOAD_BYTES

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"


def _make_sub(directory: str, name: str, content: str = "1\n00:00:01,000 --> 00:00:02,000\nHi\n"):
    path = os.path.join(directory, name)
    Path(path).write_text(content, encoding="utf-8")
    return path


def _upload(client, url, filename, content, **form):
    data = {"file": (io.BytesIO(content), filename), **form}
    return client.post(url, data=data, content_type="multipart/form-data")


def _mock_episode_sonarr(monkeypatch, video_path):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = video_path
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    monkeypatch.setattr("config.map_path", lambda p: p)
    return mock_sonarr


# ---------------------------------------------------------------------------
# POST /api/v1/library/episodes/<ep_id>/subtitles/upload
# ---------------------------------------------------------------------------


def test_upload_episode_subtitle_success_records_manual_source(client, temp_dir, monkeypatch):
    from db.models.providers import SubtitleDownload

    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _mock_episode_sonarr(monkeypatch, video)

    resp = _upload(
        client, "/api/v1/library/episodes/1/subtitles/upload", "sub.srt", _SRT, language="de"
    )
    data = resp.get_json()
    assert resp.status_code == 201
    assert data["saved_path"].endswith(".de.srt")
    assert os.path.exists(data["saved_path"])
    assert open(data["saved_path"], "rb").read() == _SRT

    with client.application.app_context():
        # file_path is the VIDEO path, matching every other source -- see
        # test_subtitle_download_file_path_convention.py.
        row = SubtitleDownload.query.filter_by(file_path=video).one()
        assert row.source == "manual"
        assert row.language == "de"
        assert row.format == "srt"


def test_upload_episode_subtitle_unsupported_extension_415(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _mock_episode_sonarr(monkeypatch, video)

    resp = _upload(
        client, "/api/v1/library/episodes/1/subtitles/upload", "sub.txt", b"hello", language="de"
    )
    assert resp.status_code == 415
    # Nothing should have been written next to the video.
    assert not os.path.exists(os.path.join(temp_dir, "episode.de.txt"))


def test_upload_episode_subtitle_conflict_without_overwrite_409(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    existing = _make_sub(temp_dir, "episode.de.srt")
    _mock_episode_sonarr(monkeypatch, video)

    resp = _upload(
        client, "/api/v1/library/episodes/1/subtitles/upload", "sub.srt", _SRT, language="de"
    )
    assert resp.status_code == 409
    # The pre-existing sidecar must be untouched.
    assert open(existing, encoding="utf-8").read() == "1\n00:00:01,000 --> 00:00:02,000\nHi\n"


def test_upload_episode_subtitle_conflict_with_overwrite_replaces(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _make_sub(temp_dir, "episode.de.srt")
    _mock_episode_sonarr(monkeypatch, video)

    resp = _upload(
        client,
        "/api/v1/library/episodes/1/subtitles/upload",
        "sub.srt",
        _SRT,
        language="de",
        overwrite="true",
    )
    data = resp.get_json()
    assert resp.status_code == 201
    assert open(data["saved_path"], "rb").read() == _SRT


def test_upload_episode_subtitle_content_length_guard_413(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _mock_episode_sonarr(monkeypatch, video)

    oversized = MAX_UPLOAD_BYTES + 2 * 1024 * 1024  # comfortably over _MAX_REQUEST_BYTES
    resp = client.post(
        "/api/v1/library/episodes/1/subtitles/upload",
        data={"file": (io.BytesIO(b"tiny"), "sub.srt"), "language": "de"},
        content_type="multipart/form-data",
        environ_overrides={"CONTENT_LENGTH": str(oversized)},
    )
    assert resp.status_code == 413
    # The guard must fire before the body is ever parsed/written to disk.
    assert not os.path.exists(os.path.join(temp_dir, "episode.de.srt"))


def test_upload_episode_subtitle_missing_language_400(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _mock_episode_sonarr(monkeypatch, video)

    resp = _upload(client, "/api/v1/library/episodes/1/subtitles/upload", "sub.srt", _SRT)
    assert resp.status_code == 400


def test_upload_episode_subtitle_no_file_400(client, temp_dir, monkeypatch):
    video = os.path.join(temp_dir, "episode.mkv")
    Path(video).touch()
    _mock_episode_sonarr(monkeypatch, video)

    resp = client.post(
        "/api/v1/library/episodes/1/subtitles/upload",
        data={"language": "de"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_upload_episode_subtitle_standalone_unknown_episode_404(client, monkeypatch):
    # No Sonarr → the resolver falls through to the standalone wanted_items
    # lookup. An unknown ep_id resolves to nothing → 404 (not the old 503).
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    resp = _upload(
        client, "/api/v1/library/episodes/1/subtitles/upload", "sub.srt", _SRT, language="de"
    )
    assert resp.status_code == 404


def test_upload_episode_subtitle_no_video_file_404(client, monkeypatch):
    mock_sonarr = MagicMock()
    mock_sonarr.get_episode_file_path.return_value = None
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: mock_sonarr)
    resp = _upload(
        client, "/api/v1/library/episodes/99/subtitles/upload", "sub.srt", _SRT, language="de"
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/library/movies/<movie_id>/subtitles/upload
# ---------------------------------------------------------------------------


def test_upload_movie_subtitle_success_records_manual_source(client, temp_dir):
    from db.models.providers import SubtitleDownload
    from db.standalone import upsert_standalone_movie

    video = os.path.join(temp_dir, "Movie (2020).mkv")
    Path(video).touch()

    with client.application.app_context():
        movie_id = upsert_standalone_movie("Movie", str(video), year=2020)

    resp = _upload(
        client,
        f"/api/v1/library/movies/{movie_id}/subtitles/upload",
        "sub.srt",
        _SRT,
        language="en",
    )
    data = resp.get_json()
    assert resp.status_code == 201
    assert os.path.exists(data["saved_path"])

    with client.application.app_context():
        row = SubtitleDownload.query.filter_by(file_path=video).one()
        assert row.source == "manual"
        assert row.language == "en"


def test_upload_movie_subtitle_not_found_404(client):
    with patch("db.standalone.get_standalone_movies", return_value=None):
        resp = _upload(
            client,
            "/api/v1/library/movies/9999/subtitles/upload",
            "sub.srt",
            _SRT,
            language="en",
        )
    assert resp.status_code == 404


def test_upload_movie_subtitle_no_video_file_404(client):
    with patch(
        "db.standalone.get_standalone_movies",
        return_value={"id": 1, "file_path": "/nonexistent/movie.mkv"},
    ):
        resp = _upload(
            client, "/api/v1/library/movies/1/subtitles/upload", "sub.srt", _SRT, language="en"
        )
    assert resp.status_code == 404
