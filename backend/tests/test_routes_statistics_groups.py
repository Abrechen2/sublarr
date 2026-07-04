"""HTTP tests for the grouped /api/v1/statistics/<group> endpoints (V1.6 #9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _seed_download(client):
    from db.models.providers import SubtitleDownload
    from extensions import db

    with client.application.app_context():
        db.session.add(
            SubtitleDownload(
                provider_name="opensubtitles",
                subtitle_id="stat1",
                language="de",
                format="srt",
                file_path="/m/x.de.srt",
                score=80,
                source="provider",
                downloaded_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        db.session.commit()


def test_subtitles_endpoint(client):
    _seed_download(client)
    resp = client.get("/api/v1/statistics/subtitles?range=7d")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["total"] >= 1
    assert data["by_source"].get("provider", 0) >= 1
    assert data["range"] == "7d"


def test_translation_endpoint(client):
    resp = client.get("/api/v1/statistics/translation")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "by_backend" in data and "mt_awaiting_original" in data


def test_providers_endpoint(client):
    resp = client.get("/api/v1/statistics/providers")
    assert resp.status_code == 200
    assert "providers" in resp.get_json()


def test_system_endpoint(client):
    resp = client.get("/api/v1/statistics/system")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "cpu_percent" in data and "db_size_bytes" in data


def test_library_endpoint(client):
    _seed_download(client)
    resp = client.get("/api/v1/statistics/library")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["subtitle_files"] >= 1


def test_trends_endpoint(client):
    resp = client.get("/api/v1/statistics/trends?range=30d")
    data = resp.get_json()
    assert resp.status_code == 200
    assert "dates" in data and "downloads" in data


def test_invalid_range_falls_back(client):
    resp = client.get("/api/v1/statistics/subtitles?range=bogus")
    assert resp.status_code == 200
    assert resp.get_json()["range"] == "30d"
