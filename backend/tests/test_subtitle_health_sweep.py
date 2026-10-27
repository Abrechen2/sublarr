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
    client.list_series.return_value = [{"id": 1}]
    client.list_episodes.return_value = [{"id": 11}, {"id": 12}, {"id": 13}]
    client.get_episode_file_path.side_effect = lambda ep_id: f"/m/e{ep_id}.mkv"

    scanned: list[int] = []
    event = threading.Event()

    def fake_scan(*, episode_id, video_path, **_):
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
    client.list_series.return_value = [{"id": 1}]
    client.list_episodes.return_value = [{"id": 11}]
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
    client.list_series.return_value = [{"id": 1}]
    client.list_episodes.return_value = [{"id": 11}]
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


def test_sweep_applies_path_mapping_to_sonarr_paths(app_ctx):
    """Sonarr reports /tv/...; with /tv -> /media the sweep must open /media/..."""
    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.list_series.return_value = [{"id": 1}]
    client.list_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = "/tv/Show/e11.mkv"
    with (
        patch("config.get_settings", return_value=MagicMock(path_mapping="/tv=/media")),
        patch("services.subtitle_health.sweep._sweep_enabled", return_value=True),
        patch("services.subtitle_health.sweep._standalone_episodes", return_value=iter(())),
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch(
            "services.subtitle_health.sweep.os.path.exists",
            side_effect=lambda p: p.startswith("/media/"),
        ),
        patch("services.subtitle_health.sweep.scan_episode") as scan,
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=False),
    ):
        sweep.subtitle_health_sweep_tick()
    assert scan.called, "the mapped path exists, so the episode must be scanned"
    assert scan.call_args.kwargs["video_path"] == "/media/Show/e11.mkv"


def test_sweep_passes_sidecars_like_the_episode_route(app_ctx):
    """The sweep's findings must match the single-episode scan's, sidecars included."""
    client = MagicMock()
    client.get_series.return_value = [{"id": 1}]
    client.get_episodes.return_value = [{"id": 11}]
    client.list_series.return_value = [{"id": 1}]
    client.list_episodes.return_value = [{"id": 11}]
    client.get_episode_file_path.return_value = "/m/e11.mkv"
    sidecar = {"path": "/m/e11.de.ass", "language": "de", "format": "ass"}
    with (
        patch("services.subtitle_health.sweep._sweep_enabled", return_value=True),
        patch("services.subtitle_health.sweep._standalone_episodes", return_value=iter(())),
        patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
        patch("services.sidecar_scan.scan_subtitle_sidecars", return_value=[sidecar]),
        patch("services.subtitle_health.sweep.scan_episode") as scan,
        patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=False),
    ):
        sweep.subtitle_health_sweep_tick()
    assert scan.call_args.kwargs["sidecars"] == [{"path": "/m/e11.de.ass", "lang": "de"}]


# --- resume cursor + time budget ---------------------------------------------


class _Library:
    """A fake Sonarr library plus a fake clock that every scan advances."""

    def __init__(self, series: dict[int, list[int]], scan_seconds: float = 0.0):
        self.series = series
        self.scan_seconds = scan_seconds
        self.now = 0.0
        self.scanned: list[int] = []
        self.episode_calls: list[int] = []
        self.client = MagicMock()
        # Deliberately unordered: the sweep must sort, or a resume point means nothing.
        self.client.get_series.side_effect = lambda: [
            {"id": sid} for sid in reversed(list(self.series))
        ]
        self.client.get_episodes.side_effect = self._episodes
        self.client.list_series.side_effect = self.client.get_series.side_effect
        self.client.list_episodes.side_effect = self._episodes
        self.client.get_episode_file_path.side_effect = lambda ep_id: f"/m/e{ep_id}.mkv"

    def _episodes(self, sid):
        self.episode_calls.append(sid)
        return [{"id": e} for e in reversed(self.series.get(sid, []))]

    def scan(self, *, episode_id, video_path, **_):
        self.scanned.append(episode_id)
        self.now += self.scan_seconds

    def run(self, budget_s: float = 10_000, standalone=None):
        standalone = standalone or (lambda after: iter(()))
        with (
            patch("services.subtitle_health.sweep._sweep_enabled", return_value=True),
            patch("services.subtitle_health.sweep._standalone_episodes", side_effect=standalone),
            patch("services.subtitle_health.sweep.get_sonarr_client", return_value=self.client),
            patch("services.subtitle_health.sweep.os.path.exists", return_value=True),
            patch("services.subtitle_health.sweep.episode_sidecars", return_value=[]),
            patch(
                "services.subtitle_health.sweep.scan_episode",
                side_effect=lambda **kw: self.scan(**kw),
            ),
            patch("services.subtitle_health.sweep._auto_fix_enabled", return_value=False),
            patch("services.subtitle_health.sweep._clock", side_effect=lambda: self.now),
            patch("services.subtitle_health.sweep.SWEEP_BUDGET_S", budget_s),
        ):
            sweep.subtitle_health_sweep_tick()


def test_sweep_budget_leaves_room_before_the_job_timeout():
    assert sweep.SWEEP_BUDGET_S > 0
    # One slow episode (several 300 s extractions) must still fit.
    assert sweep.SWEEP_TIMEOUT_S - sweep.SWEEP_BUDGET_S >= 900


def test_sweep_job_uses_the_shared_timeout():
    import inspect

    import services.scheduler as sched

    src = inspect.getsource(sched)
    block = src[src.index('id="subtitle_health_sweep"') :]
    block = block[: block.index("JobSpec(")]
    assert "timeout_s=SWEEP_TIMEOUT_S" in block, (
        "the sweep's budget is derived from SWEEP_TIMEOUT_S; the JobSpec must use it too"
    )


def test_sweep_resumes_where_the_budget_stopped_it(app_ctx, caplog):
    import logging

    lib = _Library({1: [11, 12], 2: [21, 22], 3: [31]}, scan_seconds=100)
    with caplog.at_level(logging.INFO):
        lib.run(budget_s=350)  # clock 0 -> 100 -> 200 -> 300 -> 400: four episodes start
    assert lib.scanned == [11, 12, 21, 22]
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], (
        "a budget stop is a normal night and must not log a warning or error"
    )
    paused = [r.getMessage() for r in caplog.records if "paused" in r.getMessage()]
    assert paused and "4 episode" in paused[0]
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 2, 22)

    lib.scanned.clear()
    lib.episode_calls.clear()
    lib.now = 0
    lib.run(budget_s=50)
    assert lib.scanned == [31]
    # Series 1 lies before the resume point: it is only fetched once the sweep wraps.
    assert lib.episode_calls == [2, 3, 1]


def test_sweep_wraps_around_and_logs_a_full_pass(app_ctx, caplog):
    import logging

    lib = _Library({1: [11, 12], 2: [21, 22]}, scan_seconds=100)
    sweep.save_cursor((sweep.SOURCE_SONARR, 2, 21))
    with caplog.at_level(logging.INFO):
        lib.run(budget_s=250)
    assert lib.scanned == [22, 11, 12]
    assert any("sweep completed a full pass" in r.getMessage() for r in caplog.records)
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 1, 12)


def test_sweep_full_pass_in_one_run_scans_each_episode_once(app_ctx):
    lib = _Library({1: [11, 12], 2: [21]})
    sweep.save_cursor((sweep.SOURCE_SONARR, 1, 11))
    lib.run()
    assert lib.scanned == [12, 21, 11]


def test_sweep_fresh_full_pass_clears_the_cursor(app_ctx):
    lib = _Library({1: [11], 2: [21]})
    lib.run()
    assert lib.scanned == [11, 21]
    assert sweep.load_cursor() is None


def test_sweep_saves_the_cursor_when_aborted(app_ctx):
    import threading

    from services.scheduler import cancellation

    lib = _Library({1: [11, 12, 13]})
    event = threading.Event()
    original = lib.scan

    def scan_then_abort(**kw):
        original(**kw)
        if kw["episode_id"] == 12:
            event.set()

    lib.scan = scan_then_abort
    token = cancellation.activate(event)
    try:
        lib.run()
    finally:
        cancellation.deactivate(token)
    assert lib.scanned == [11, 12]
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 1, 12)


def test_sweep_resume_survives_added_and_removed_items(app_ctx):
    # The cursor's own series and episode are gone; new items appear on both sides.
    sweep.save_cursor((sweep.SOURCE_SONARR, 2, 22))
    lib = _Library({1: [11, 15], 3: [31], 5: [51]})
    lib.run()
    assert lib.scanned == [31, 51, 11, 15]


def test_sweep_resume_inside_a_series_skips_lower_episodes(app_ctx):
    sweep.save_cursor((sweep.SOURCE_SONARR, 2, 22))
    lib = _Library({2: [20, 22, 23, 25]}, scan_seconds=100)
    lib.run(budget_s=150)
    assert lib.scanned == [23, 25]


def test_sweep_ignores_an_unreadable_cursor(app_ctx):
    from db.repositories.config import ConfigRepository

    ConfigRepository().save_config_entry(sweep.CURSOR_KEY, "not json")
    assert sweep.load_cursor() is None
    lib = _Library({1: [11]})
    lib.run()
    assert lib.scanned == [11]


def test_sweep_standalone_items_follow_sonarr_and_resume(app_ctx):
    lib = _Library({1: [11]})
    sweep.save_cursor((sweep.SOURCE_STANDALONE, 7, -5))

    def standalone(after):
        items = [
            ((sweep.SOURCE_STANDALONE, 7, -6), "/s/a.mkv"),
            ((sweep.SOURCE_STANDALONE, 7, -4), "/s/b.mkv"),
        ]
        for key, path in items:
            if after is None or key > after:
                yield key, (lambda p=path: p)

    lib.run(standalone=standalone)
    assert lib.scanned == [-4, 11, -6]


def test_sweep_stopped_before_its_first_episode_keeps_the_resume_point(app_ctx):
    lib = _Library({1: [11, 12], 2: [21]})
    sweep.save_cursor((sweep.SOURCE_SONARR, 1, 12))
    lib.run(budget_s=0)  # the budget is spent before the first episode
    assert lib.scanned == []
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 1, 12)


def test_sweep_keeps_the_resume_point_when_sonarr_lists_nothing(app_ctx):
    # A Sonarr outage is no completed pass.
    lib = _Library({})
    lib.client.list_series.side_effect = lambda: None
    sweep.save_cursor((sweep.SOURCE_SONARR, 5, 51))
    lib.run()
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 5, 51)


def test_sweep_keeps_the_resume_point_when_sonarr_is_down_but_standalone_exists(app_ctx):
    lib = _Library({})
    lib.client.list_series.side_effect = lambda: None
    sweep.save_cursor((sweep.SOURCE_SONARR, 5, 51))

    def standalone(after):
        yield (sweep.SOURCE_STANDALONE, 1, -1), lambda: "/m/s1.mkv"

    lib.run(standalone=standalone)
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 5, 51)


def test_an_empty_sonarr_still_sweeps_standalone(app_ctx):
    lib = _Library({})
    seen = []

    def standalone(after):
        def path():
            seen.append(-1)
            return "/m/s1.mkv"

        yield (sweep.SOURCE_STANDALONE, 1, -1), path

    lib.run(standalone=standalone)
    assert seen == [-1]


def test_an_episode_list_failure_keeps_that_series_for_next_time(app_ctx):
    lib = _Library({1: [11, 12], 2: [21], 3: [31]})
    lib.client.list_episodes.side_effect = lambda sid: None if sid == 2 else lib._episodes(sid)
    lib.run()
    assert lib.scanned == [11, 12]
    assert sweep.load_cursor() == (sweep.SOURCE_SONARR, 1, 12)
