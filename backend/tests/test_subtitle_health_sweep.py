from unittest.mock import MagicMock, patch

from services.subtitle_health import sweep


def test_sweep_stops_at_the_next_episode_when_asked(app_ctx):
    """This is the job that ran sixteen hours past its ceiling (#183, bug 3).

    The sweep walks every episode of every series and ffprobes each one, so a
    stop can only take effect between episodes — that is the unit, and the test
    pins exactly that: the episode being scanned when the request arrives is
    allowed to finish, the next one is never started.

    The tick is driven for real here. A test that looped over its own list and
    checked the flag itself would pass whether or not `subtitle_health_sweep_tick`
    ever asks.
    """
    import threading

    from services.scheduler import cancellation

    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}, {"id": 12}, {"id": 13}]
    client.get_episode_file_path.side_effect = lambda ep_id: f"/m/e{ep_id}.mkv"

    scanned: list[int] = []
    event = threading.Event()

    def fake_scan(*, episode_id, video_path):
        scanned.append(episode_id)
        event.set()  # the stop arrives while the first episode is in flight

    token = cancellation.activate(event)
    try:
        with (
            patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
            patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
            patch("services.subtitle_health.sweep.scan_episode", side_effect=fake_scan),
            patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=False),
        ):
            sweep.subtitle_health_sweep_tick()
    finally:
        cancellation.deactivate(token)

    assert scanned == [11], (
        f"the sweep kept going after being asked to stop: scanned {scanned}. "
        "Without a check point the run is recorded as abandoned and the library "
        "reads continue until the container restarts."
    )


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
