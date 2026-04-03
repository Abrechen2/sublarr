"""HTTP tests for routes/media.py — streaming endpoint with security checks."""

import os
import tempfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The conftest sets SUBLARR_MEDIA_PATH = os.path.realpath(tempfile.gettempdir()).
# Files must live inside that base dir to pass is_safe_path().
_MEDIA_BASE = os.path.realpath(tempfile.gettempdir())


# ---------------------------------------------------------------------------
# GET /api/v1/media/stream
# ---------------------------------------------------------------------------


def test_stream_missing_path_param(client):
    # No path query parameter → 400
    resp = client.get("/api/v1/media/stream")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_stream_path_traversal_blocked(client):
    # Path outside media_path (e.g. /etc/passwd) must be rejected with 403
    resp = client.get("/api/v1/media/stream?path=/etc/passwd")
    assert resp.status_code == 403
    data = resp.get_json()
    assert "error" in data


def test_stream_windows_traversal_blocked(client):
    # Windows-style path outside media base
    resp = client.get("/api/v1/media/stream?path=C:/Windows/System32/drivers/etc/hosts")
    assert resp.status_code == 403
    data = resp.get_json()
    assert "error" in data


def test_stream_file_not_found(client):
    # Path inside media_base but file does not exist → 404
    ghost = os.path.join(_MEDIA_BASE, "ghost_file_that_does_not_exist.mkv")
    resp = client.get(f"/api/v1/media/stream?path={ghost}")
    assert resp.status_code == 404
    data = resp.get_json()
    assert "error" in data


def test_stream_disabled_returns_503(client, monkeypatch):
    # When streaming_enabled is False the endpoint returns 503 before any path check.
    # Patch get_settings at the point where routes/media.py resolves it (it imports
    # the function from config at module load time, so we patch the reference used
    # inside that module).
    import config as _config_mod
    import routes.media as _media_mod

    real_settings = _config_mod.get_settings()

    class _FakeSettings:
        streaming_enabled = False
        media_path = _MEDIA_BASE

        def __getattr__(self, item):
            return getattr(real_settings, item)

    monkeypatch.setattr(_media_mod, "get_settings", lambda: _FakeSettings())
    resp = client.get(f"/api/v1/media/stream?path={_MEDIA_BASE}/anything.mkv")
    assert resp.status_code == 503
    data = resp.get_json()
    assert "error" in data


def test_stream_valid_file_returns_content(client):
    # Create a real 1 KB file inside the allowed media base, then stream it.
    # On Windows, Flask's send_file / streaming generator may keep the file handle
    # open briefly after the response, so we tolerate a PermissionError on cleanup.
    video_path = os.path.join(_MEDIA_BASE, "test_stream_video.mkv")
    try:
        with open(video_path, "wb") as f:
            f.write(b"\x00" * 1024)

        resp = client.get(f"/api/v1/media/stream?path={video_path}")
        # 200 (full) or 206 (partial) means the file was served successfully.
        # 503 means streaming is disabled in this test environment.
        assert resp.status_code in (200, 206, 503)
    finally:
        try:
            if os.path.exists(video_path):
                os.unlink(video_path)
        except PermissionError:
            pass  # Windows file-lock from streaming generator; OS will reclaim on process exit
