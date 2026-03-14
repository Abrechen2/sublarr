"""Tests for NFO export API endpoints (/api/v1/subtitles/export-nfo and
/api/v1/series/<id>/subtitles/export-nfo).
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

import routes.nfo as nfo_module
from routes.nfo import bp as nfo_bp


# ---------------------------------------------------------------------------
# App fixture — isolated Flask app with just the nfo blueprint
# ---------------------------------------------------------------------------


@pytest.fixture
def app(tmp_path):
    """Minimal Flask app with nfo blueprint and temp media_path."""
    _app = Flask(__name__)
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"

    # Point SUBLARR_MEDIA_PATH at tmp_path so security checks use a real dir
    os.environ["SUBLARR_MEDIA_PATH"] = str(tmp_path)

    _app.register_blueprint(nfo_bp)
    yield _app
    os.environ.pop("SUBLARR_MEDIA_PATH", None)


# ---------------------------------------------------------------------------
# Single-subtitle endpoint
# ---------------------------------------------------------------------------


def test_export_single_missing_path(app):
    """POST without ?path query param → 400."""
    with app.test_client() as client:
        r = client.post("/api/v1/subtitles/export-nfo")
    assert r.status_code == 400
    data = r.get_json()
    assert "error" in data


def test_export_single_unsafe_path(app, monkeypatch, tmp_path):
    """Path outside media_path → 403."""
    monkeypatch.setattr(nfo_module, "is_safe_path", lambda path, root: False)
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")

    with app.test_client() as client:
        r = client.post(f"/api/v1/subtitles/export-nfo?path={sub}")
    assert r.status_code == 403


def test_export_single_file_not_found(app, monkeypatch, tmp_path):
    """Path passes security check but file does not exist on disk → 404."""
    monkeypatch.setattr(nfo_module, "is_safe_path", lambda path, root: True)
    nonexistent = str(tmp_path / "ghost.de.ass")

    with app.test_client() as client:
        r = client.post(f"/api/v1/subtitles/export-nfo?path={nonexistent}")
    assert r.status_code == 404


def test_export_single_success(app, monkeypatch, tmp_path):
    """File exists, write_nfo called, returns {status: ok, nfo_path: ...}."""
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")

    called_with = []

    def _fake_write_nfo(path, meta):
        called_with.append(path)
        # Simulate successful write by creating the .nfo file
        open(path + ".nfo", "w").close()

    monkeypatch.setattr(nfo_module, "is_safe_path", lambda path, root: True)
    monkeypatch.setattr(nfo_module, "write_nfo", _fake_write_nfo)

    with app.test_client() as client:
        r = client.post(f"/api/v1/subtitles/export-nfo?path={sub}")

    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["nfo_path"] == str(sub) + ".nfo"
    assert called_with == [str(sub)]


# ---------------------------------------------------------------------------
# Series endpoint
# ---------------------------------------------------------------------------


def test_export_series_not_found(app, monkeypatch):
    """Series not resolvable via sonarr_client → 404."""

    def _fake_get_series_path(series_id):
        return None

    monkeypatch.setattr(nfo_module, "_get_series_path_for_nfo", _fake_get_series_path)

    with app.test_client() as client:
        r = client.post("/api/v1/series/99/subtitles/export-nfo")

    assert r.status_code == 404
    data = r.get_json()
    assert "error" in data


def test_export_series_success(app, monkeypatch, tmp_path):
    """Series found, 2 files in subtitle_downloads (1 exists on disk) → exported=1, skipped=1."""
    # Create one real subtitle file
    existing_sub = tmp_path / "ep01.de.ass"
    existing_sub.write_text("dummy")
    missing_sub = str(tmp_path / "ep02.de.ass")  # does not exist on disk

    series_path = str(tmp_path)

    monkeypatch.setattr(nfo_module, "_get_series_path_for_nfo", lambda sid: series_path)
    monkeypatch.setattr(nfo_module, "is_safe_path", lambda path, root: True)

    # Fake DB query returns two file_path rows
    fake_rows = [(str(existing_sub),), (missing_sub,)]

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class _FakeConn:
        def execute(self, stmt, params=None):
            return _FakeResult(fake_rows)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    class _FakeDb:
        engine = _FakeEngine()

    monkeypatch.setattr(nfo_module, "_get_db_engine", lambda: _FakeDb())

    written = []

    def _fake_write_nfo(path, meta):
        written.append(path)

    monkeypatch.setattr(nfo_module, "write_nfo", _fake_write_nfo)

    with app.test_client() as client:
        r = client.post("/api/v1/series/1/subtitles/export-nfo")

    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["exported"] == 1
    assert data["skipped"] == 1
    assert written == [str(existing_sub)]


def test_export_single_write_failure(app, monkeypatch, tmp_path):
    """write_nfo does not create the .nfo file → 500."""
    sub = tmp_path / "ep01.de.ass"
    sub.write_text("dummy")

    def _fake_write_nfo_no_op(path, meta):
        pass  # deliberately does NOT create the .nfo file

    monkeypatch.setattr(nfo_module, "is_safe_path", lambda path, root: True)
    monkeypatch.setattr(nfo_module, "write_nfo", _fake_write_nfo_no_op)

    with app.test_client() as client:
        r = client.post(f"/api/v1/subtitles/export-nfo?path={sub}")

    assert r.status_code == 500
    data = r.get_json()
    assert "error" in data


def test_export_series_unsafe_db_path(app, monkeypatch, tmp_path):
    """DB row path passes the LIKE prefix but is_safe_path rejects it → counted as skipped."""
    series_path = str(tmp_path)

    monkeypatch.setattr(nfo_module, "_get_series_path_for_nfo", lambda sid: series_path)

    # Series-level check passes, per-file check rejects
    call_count = [0]

    def _is_safe_path(path, root):
        call_count[0] += 1
        # First call: series_path validation (should pass), subsequent: per-file (fail)
        return call_count[0] == 1

    monkeypatch.setattr(nfo_module, "is_safe_path", _is_safe_path)

    # DB returns a path that passes the LIKE prefix but is outside media_path
    unsafe_path = str(tmp_path / "../../etc/passwd.de.ass")
    fake_rows = [(unsafe_path,)]

    class _FakeResult:
        def fetchall(self):
            return fake_rows

    class _FakeConn:
        def execute(self, stmt, params=None):
            return _FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    class _FakeEngine:
        def connect(self):
            return _FakeConn()

    class _FakeDb:
        engine = _FakeEngine()

    monkeypatch.setattr(nfo_module, "_get_db_engine", lambda: _FakeDb())

    written = []
    monkeypatch.setattr(nfo_module, "write_nfo", lambda path, meta: written.append(path))

    with app.test_client() as client:
        r = client.post("/api/v1/series/1/subtitles/export-nfo")

    assert r.status_code == 200
    data = r.get_json()
    assert data["exported"] == 0
    assert data["skipped"] == 1
    assert written == []  # write_nfo must NOT have been called
