import os
from unittest.mock import MagicMock, patch

import pytest

from app import create_app


def _mock_settings(tmp_path, streaming_enabled=True):
    s = MagicMock()
    s.streaming_enabled = streaming_enabled
    s.media_path = str(tmp_path)
    s.api_key = None  # No API key — auth passes through
    return s


@pytest.fixture()
def media_client(temp_db, tmp_path):
    app = create_app(testing=True)
    app.config["TESTING"] = True
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    with patch("routes.media.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(tmp_path)
        with app.test_client() as c:
            yield c, str(fake_video)


def test_stream_returns_206_with_range(media_client):
    c, path = media_client
    resp = c.get(
        f"/api/v1/media/stream?path={path}",
        headers={"Range": "bytes=0-511"},
    )
    assert resp.status_code == 206
    assert resp.headers["Content-Type"].startswith("video/")
    assert resp.headers.get("Accept-Ranges") == "bytes"


def test_stream_returns_200_without_range(media_client):
    c, path = media_client
    resp = c.get(f"/api/v1/media/stream?path={path}")
    assert resp.status_code == 200


def test_stream_rejects_invalid_range(media_client):
    c, path = media_client
    resp = c.get(
        f"/api/v1/media/stream?path={path}",
        headers={"Range": "bytes=900-100"},
    )
    assert resp.status_code == 416


def test_stream_rejects_path_traversal(media_client):
    c, _ = media_client
    resp = c.get("/api/v1/media/stream?path=/etc/passwd")
    assert resp.status_code == 403


def test_stream_returns_404_for_missing_file(media_client, tmp_path):
    c, path = media_client
    missing = os.path.join(os.path.dirname(path), "nonexistent_file.mp4")
    resp = c.get(f"/api/v1/media/stream?path={missing}")
    assert resp.status_code == 404


def test_stream_disabled_returns_503(media_client):
    c, path = media_client
    with patch("routes.media.get_settings") as mock_disabled:
        mock_disabled.return_value = _mock_settings(os.path.dirname(path), streaming_enabled=False)
        resp = c.get(f"/api/v1/media/stream?path={path}")
        assert resp.status_code == 503
