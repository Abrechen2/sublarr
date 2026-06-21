from unittest.mock import MagicMock, patch

from services.subtitle_health import sweep


def test_sweep_reports_only_by_default(app_ctx):
    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = "/m/e11.mkv"
    with (
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
        patch("services.subtitle_health.sweep.scan_episode") as scan,
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=False),
        patch("services.subtitle_health.sweep.apply_fix") as fx,
    ):
        sweep.subtitle_health_sweep_tick()
    assert scan.called
    assert not fx.called  # report-only when auto-fix disabled


def test_sweep_autofix_only_safe_actions(app_ctx):
    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = "/m/e11.mkv"
    from services.subtitle_health.models import (
        Issue,
        IssueType,
        ScanResult,
        Severity,
        TargetKind,
    )

    res = ScanResult(
        episode_id=11,
        video_path="/m/e11.mkv",
        issues=[
            Issue(
                type=IssueType.ASS_ESCAPE_LEAK,
                severity=Severity.CONFIRMED,
                episode_id=11,
                target_kind=TargetKind.SIDECAR,
                target_path="/m/e11.de.srt",
                stream_index=None,
                lang="de",
                count=1,
                snippets=[],
                raw_hash="h",
                fixable=True,
                suggested_fix="repair_escapes",
            ),
        ],
    )
    with (
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
        patch("services.subtitle_health.sweep.scan_episode", return_value=res),
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=True),
        patch("services.subtitle_health.sweep._is_stable", return_value=True),
        patch(
            "services.subtitle_health.sweep.store.get_findings_for_episode",
            return_value=[
                {
                    "id": 1,
                    "issue_type": "ass_escape_leak",
                    "target_kind": "sidecar",
                    "suggested_fix": "repair_escapes",
                    "target_path": "/m/e11.de.srt",
                }
            ],
        ),
        patch("services.subtitle_health.sweep.apply_fix") as fx,
    ):
        sweep.subtitle_health_sweep_tick()
    actions = {
        (
            c.kwargs.get("action")
            if c.kwargs.get("action")
            else (c.args[1] if len(c.args) > 1 else None)
        )
        for c in fx.call_args_list
    }
    assert actions <= {"repair_escapes", "reencode"}
