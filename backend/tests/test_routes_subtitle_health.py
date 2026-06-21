from unittest.mock import patch

from services.subtitle_health.models import (
    Issue,
    IssueType,
    ScanResult,
    Severity,
    TargetKind,
)


def test_health_scan_returns_issues(client):
    fake = ScanResult(
        episode_id=54680,
        video_path="/m/x.mkv",
        issues=[
            Issue(
                type=IssueType.ASS_ESCAPE_LEAK,
                severity=Severity.CONFIRMED,
                episode_id=54680,
                target_kind=TargetKind.EMBEDDED,
                target_path="/m/x.mkv",
                stream_index=0,
                lang="ger",
                count=177,
                snippets=["erkannt\\Nwie gut"],
                raw_hash="h",
                fixable=True,
                suggested_fix="extract_clean_sidecar",
            )
        ],
    )
    with (
        patch("routes.tracks._get_video_path", return_value="/m/x.mkv"),
        patch("os.path.exists", return_value=True),
        patch("routes.subtitles.scan_subtitle_sidecars", return_value=[]),
        patch("services.subtitle_health.scan_episode", return_value=fake),
    ):
        resp = client.post("/api/v1/library/episodes/54680/health/scan")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["healthy"] is False
    assert body["issues"][0]["type"] == "ass_escape_leak"


def test_health_scan_404_when_no_video(client):
    with patch("routes.tracks._get_video_path", return_value=None):
        resp = client.post("/api/v1/library/episodes/1/health/scan")
    assert resp.status_code == 404


def test_series_health_scan_starts_background(client):
    from unittest.mock import patch

    with patch("routes.tracks.submit_background") as bg:
        resp = client.post("/api/v1/library/series/99/health/scan")
    assert resp.status_code == 202
    assert resp.get_json()["series_id"] == 99
    assert bg.called


def test_fix_endpoint_requires_fields(client):
    resp = client.post("/api/v1/library/episodes/5/health/fix", json={})
    assert resp.status_code == 400


def test_report_endpoint_ok(client):
    resp = client.get("/api/v1/subtitle-health/report")
    assert resp.status_code == 200
    assert "total_findings" in resp.get_json()
