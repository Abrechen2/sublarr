from unittest.mock import MagicMock, patch

from services.subtitle_health import series_scan
from services.subtitle_health.models import (
    Issue,
    IssueType,
    ScanResult,
    Severity,
    TargetKind,
)


def _result(ep_id, n):
    issues = [
        Issue(
            type=IssueType.ASS_ESCAPE_LEAK,
            severity=Severity.CONFIRMED,
            episode_id=ep_id,
            target_kind=TargetKind.EMBEDDED,
            target_path="/m/x.mkv",
            stream_index=0,
            lang="ger",
            count=1,
            snippets=["x"],
            raw_hash="h",
            fixable=True,
            suggested_fix="repair_escapes",
        )
        for _ in range(n)
    ]
    return ScanResult(episode_id=ep_id, video_path="/m/x.mkv", issues=issues)


def test_run_series_scan_aggregates():
    client = MagicMock()
    client.get_episodes.return_value = [{"id": 1}, {"id": 2}, {"id": 3}]
    client.get_episode_file_path.side_effect = lambda e: f"/m/e{e}.mkv"

    with (
        patch("services.subtitle_health.series_scan.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.series_scan.os.path.exists", return_value=True),
        patch(
            "services.subtitle_health.series_scan.scan_episode",
            side_effect=lambda episode_id, video_path, **k: _result(episode_id, episode_id),
        ),
        patch("services.subtitle_health.series_scan.emit_event"),
    ):
        summary = series_scan.run_series_scan(series_id=99)

    assert summary["series_id"] == 99
    assert summary["episodes_scanned"] == 3
    assert summary["total_issues"] == 1 + 2 + 3
    assert summary["by_type"]["ass_escape_leak"] == 6
    assert summary["affected_episodes"] == 3


def test_run_series_scan_applies_path_mapping():
    """Sonarr reports /tv/...; with /tv -> /media the scan must open /media/..."""
    client = MagicMock()
    client.get_episodes.return_value = [{"id": 1}]
    client.get_episode_file_path.return_value = "/tv/Show/e1.mkv"

    with (
        patch("config.get_settings", return_value=MagicMock(path_mapping="/tv=/media")),
        patch("services.subtitle_health.series_scan.get_sonarr_client", return_value=client),
        patch(
            "services.subtitle_health.series_scan.os.path.exists",
            side_effect=lambda p: p.startswith("/media/"),
        ),
        patch(
            "services.subtitle_health.series_scan.scan_episode",
            side_effect=lambda episode_id, video_path, **k: _result(episode_id, 0),
        ) as scan,
        patch("services.subtitle_health.series_scan.emit_event"),
    ):
        summary = series_scan.run_series_scan(series_id=7)

    assert summary["episodes_scanned"] == 1
    assert scan.call_args.kwargs["video_path"] == "/media/Show/e1.mkv"


def test_run_series_scan_warns_when_no_file_exists(caplog):
    """A scan that finds no file on disk must not look like a clean success."""
    client = MagicMock()
    client.get_episodes.return_value = [{"id": 1}, {"id": 2}]
    client.get_episode_file_path.side_effect = lambda e: f"/tv/Show/e{e}.mkv"

    with (
        patch("services.subtitle_health.series_scan.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.series_scan.os.path.exists", return_value=False),
        patch("services.subtitle_health.series_scan.scan_episode") as scan,
        patch("services.subtitle_health.series_scan.emit_event"),
        caplog.at_level("WARNING", logger="services.subtitle_health.series_scan"),
    ):
        summary = series_scan.run_series_scan(series_id=7)

    assert not scan.called
    assert summary["episodes_scanned"] == 0
    assert summary["episodes_skipped"] == 2
    assert any("skipped" in r.getMessage() and "2" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]
