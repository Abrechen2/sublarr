# backend/tests/test_subtitle_processor_routes.py
"""Tests for /api/v1/tools/process* and /api/v1/library/*/process routes."""

import json
import os
import time

import pytest


def test_process_dry_run_returns_changes(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nDownloaded from opensubtitles.org\n\n",
        encoding="utf-8",
    )
    resp = client.post(
        "/api/v1/tools/process",
        json={
            "path": str(sub),
            "mods": [{"mod": "common_fixes", "options": {"watermark_removal": True}}],
            "dry_run": True,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dry_run"] is True
    assert isinstance(data["changes"], list)
    assert len(data["changes"]) >= 1
    assert data["changes"][0]["original_text"]
    # File must not have been modified (dry_run=True)
    mtime_before = os.path.getmtime(str(sub))
    # Re-request with same dry_run — mtime must remain unchanged
    time.sleep(0.01)
    client.post(
        "/api/v1/tools/process",
        json={
            "path": str(sub),
            "mods": [{"mod": "common_fixes", "options": {"watermark_removal": True}}],
            "dry_run": True,
        },
    )
    assert os.path.getmtime(str(sub)) == mtime_before


def test_process_applies_changes(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nDownloaded from opensubtitles.org\n\n",
        encoding="utf-8",
    )
    resp = client.post(
        "/api/v1/tools/process",
        json={
            "path": str(sub),
            "mods": [{"mod": "common_fixes", "options": {"watermark_removal": True}}],
            "dry_run": False,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["backed_up"] is True


def test_process_undo_restores_bak(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    original_content = "1\n00:00:01,000 --> 00:00:02,000\nDownloaded from opensubtitles.org\n\n"
    sub.write_text(original_content, encoding="utf-8")

    # First apply to create backup
    client.post(
        "/api/v1/tools/process",
        json={
            "path": str(sub),
            "mods": [{"mod": "common_fixes", "options": {"watermark_removal": True}}],
        },
    )

    # Then undo
    resp = client.post("/api/v1/tools/process/undo", json={"path": str(sub)})
    assert resp.status_code == 200
    assert sub.read_text(encoding="utf-8") == original_content


def test_process_undo_404_when_no_bak(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")

    resp = client.post("/api/v1/tools/process/undo", json={"path": str(sub)})
    assert resp.status_code == 404


def test_process_undo_409_on_os_error(client, tmp_path, monkeypatch):
    from unittest.mock import patch

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    # Create a fake .bak file
    bak = tmp_path / "ep.en.bak.srt"
    bak.write_text("original", encoding="utf-8")

    with patch("shutil.move", side_effect=OSError("locked")):
        resp = client.post("/api/v1/tools/process/undo", json={"path": str(sub)})
    assert resp.status_code == 409


def test_bak_exists_returns_true_when_bak_present(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()

    sub = tmp_path / "ep.en.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n\n", encoding="utf-8")
    bak = tmp_path / "ep.en.bak.srt"
    bak.write_text("backup", encoding="utf-8")

    resp = client.get(f"/api/v1/tools/process/bak-exists?path={sub}")
    assert resp.status_code == 200
    assert resp.get_json()["exists"] is True


def test_get_interjections_returns_list(client):
    resp = client.get("/api/v1/tools/process/interjections")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) > 0
    assert "is_custom" in data


def test_put_interjections_updates_list(client):
    resp = client.put(
        "/api/v1/tools/process/interjections",
        json={"items": ["Blorp", "Zorp"]},
    )
    assert resp.status_code == 200

    resp2 = client.get("/api/v1/tools/process/interjections")
    data = resp2.get_json()
    assert "Blorp" in data["items"]
    assert data["is_custom"] is True


def test_process_series_returns_202(client):
    resp = client.post("/api/v1/library/series/123/process")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "started"
    assert data["series_id"] == 123


def test_process_all_returns_202(client):
    resp = client.post("/api/v1/library/process-all", json={"filter": "all"})
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "started"
    assert data["filter"] == "all"


def test_update_series_processing_config_returns_200(client):
    resp = client.patch(
        "/api/v1/library/series/42/processing-config",
        json={"hi_removal": True, "common_fixes": False},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["series_id"] == 42
    assert data["config"]["hi_removal"] is True
