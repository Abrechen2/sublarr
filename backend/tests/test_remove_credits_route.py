"""Route tests for POST /api/v1/tools/remove-credits."""

import os

import pytest


@pytest.fixture
def client(temp_db, tmp_path, monkeypatch):
    # temp_db comes from backend/tests/conftest.py (shared fixture that initialises SQLite)
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    with app.test_client() as c:
        yield c, tmp_path


def _make_srt(path, content):
    path.write_text(content, encoding="utf-8")
    return str(path)


SRT_WITH_CREDITS = (
    "1\n00:00:01,000 --> 00:00:03,000\nHello, how are you?\n\n"
    "2\n00:00:04,000 --> 00:00:06,000\nCredits: John Smith\n\n"
    "3\n00:00:07,000 --> 00:00:09,000\nI am fine, thanks.\n"
)


def test_dry_run_returns_preview_no_modification(client):
    c, tmp_path = client
    f = _make_srt(tmp_path / "test.srt", SRT_WITH_CREDITS)
    original = (tmp_path / "test.srt").read_text()

    resp = c.post(
        "/api/v1/tools/remove-credits",
        json={"file_path": f, "dry_run": True},
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "dry_run"
    assert data["would_remove"] >= 1
    assert isinstance(data["preview"], list)
    # File must NOT be modified
    assert (tmp_path / "test.srt").read_text() == original


def test_remove_credits_modifies_file_and_creates_backup(client):
    c, tmp_path = client
    f = _make_srt(tmp_path / "sub.srt", SRT_WITH_CREDITS)

    resp = c.post(
        "/api/v1/tools/remove-credits", json={"file_path": f}, content_type="application/json"
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "cleaned"
    assert data["removed"] >= 1
    assert data["original_lines"] > data["cleaned_lines"]
    assert "backed_up" in data
    # Backup file exists
    assert os.path.exists(data["backed_up"])
    # Modified file no longer contains credits line
    assert "Credits: John Smith" not in (tmp_path / "sub.srt").read_text()


def test_path_outside_media_path_returns_403(client):
    c, _ = client
    resp = c.post(
        "/api/v1/tools/remove-credits",
        json={"file_path": "/etc/passwd"},
        content_type="application/json",
    )
    assert resp.status_code == 403


def test_unsupported_format_returns_400(client):
    c, tmp_path = client
    f = tmp_path / "test.vtt"
    f.write_text("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nHello\n")
    resp = c.post(
        "/api/v1/tools/remove-credits", json={"file_path": str(f)}, content_type="application/json"
    )
    assert resp.status_code == 400
