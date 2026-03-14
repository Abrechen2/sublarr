import os
from unittest.mock import MagicMock, patch


def _make_app():
    """Import create_app lazily to avoid import-time side effects."""
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


def _mock_settings(tmp_path, streaming_enabled=True):
    s = MagicMock()
    s.streaming_enabled = streaming_enabled
    s.media_path = str(tmp_path)
    s.api_key = None  # No API key — auth passes through
    return s


import pytest


@pytest.fixture()
def client(tmp_path):
    app = _make_app()
    # Point media_path to a tmp dir so is_safe_path passes
    fake_video = tmp_path / "video.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    with patch("routes.media.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(tmp_path)
        with app.test_client() as c:
            yield c, str(fake_video)


def test_stream_returns_206_with_range(client):
    c, path = client
    resp = c.get(
        f"/api/v1/media/stream?path={path}",
        headers={"Range": "bytes=0-511"},
    )
    assert resp.status_code == 206
    assert resp.headers["Content-Type"].startswith("video/")
    assert resp.headers.get("Accept-Ranges") == "bytes"


def test_stream_returns_200_without_range(client):
    c, path = client
    resp = c.get(f"/api/v1/media/stream?path={path}")
    assert resp.status_code == 200


def test_stream_rejects_invalid_range(client):
    c, path = client
    resp = c.get(
        f"/api/v1/media/stream?path={path}",
        headers={"Range": "bytes=900-100"},
    )
    assert resp.status_code == 416


def test_stream_rejects_path_traversal(client):
    c, _ = client
    resp = c.get("/api/v1/media/stream?path=/etc/passwd")
    assert resp.status_code == 403


def test_stream_returns_404_for_missing_file(client):
    c, path = client
    # Use a path that is inside media_path but doesn't exist
    missing = os.path.join(os.path.dirname(path), "nonexistent_file.mp4")
    resp = c.get(f"/api/v1/media/stream?path={missing}")
    assert resp.status_code == 404


def test_stream_disabled_returns_503(client):
    c, path = client
    with patch("routes.media.get_settings") as mock_disabled:
        mock_disabled.return_value = _mock_settings(
            os.path.dirname(path), streaming_enabled=False
        )
        resp = c.get(f"/api/v1/media/stream?path={path}")
        assert resp.status_code == 503
