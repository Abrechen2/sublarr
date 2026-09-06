"""Wall-clock budget for the subtitle-automation drain.

The drain claims up to `max_items` rows and checks the abort signal between
them, but it had no clock of its own. The JobSpec's `timeout_s` was the only
bound, and a timeout does not cancel — it stops *waiting* and sets the abort
event. So a tick that was doing exactly the work asked of it still got
recorded as `timeout`, and its deliberate wind-down surfaced as an ERROR-level
"translation failed". Prod 2026-09-06: 12 of 70 ticks in 24h, mean 2549s
against a 2400s timeout, i.e. ~150s of legitimate wind-down past the wait.

That is the same complaint the JobSpec comment already records for the old
600s bound. Raising the ceiling again just moves it. The fix is a budget the
drain checks *before claiming* the next row, so the tick ends inside the
timeout and is recorded as `ok`.
"""

from unittest.mock import patch

import pytest

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)
from services.subtitle_automation_runner import SubtitleAutomationRunner


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


@pytest.fixture
def runner(app_ctx):
    return SubtitleAutomationRunner()


@pytest.fixture
def automation_on():
    with patch(
        "services.subtitle_automation_runner._automation_enabled",
        return_value=True,
    ):
        yield


class TestDrainWallClockBudget:
    def test_drain_stops_once_the_budget_is_spent(self, repo, runner, automation_on):
        """Two items fit the budget, the clock then runs out, the rest wait."""
        for i in range(6):
            repo.enqueue(
                wanted_item_id=7100 + i,
                file_path=f"/m/budget{i}.mkv",
                target_language="ger",
            )

        # Each processed item costs 400s of a 900s budget: items 1 and 2 fit
        # (0s, 400s), the check before item 3 sees 800s... still inside, item 3
        # runs, and the check before item 4 sees 1200s and stops. So 3 items.
        clock = {"t": 0.0}

        def fake_monotonic():
            return clock["t"]

        def advance(*_a, **_kw):
            clock["t"] += 400.0
            return {"status": "ok", "output_path": "/m/x.ger.srt"}

        with (
            patch("services.subtitle_automation_runner.time.monotonic", fake_monotonic),
            patch(
                "services.subtitle_automation_runner._extract_embedded_sub",
                side_effect=advance,
            ),
        ):
            processed = runner.drain(max_items=6, budget_s=900)

        assert processed == 3, (
            f"budget of 900s at 400s per item should fit 3 items, got {processed}"
        )
        assert repo.get_counts()["pending"] == 3

    def test_budget_is_checked_before_claiming_not_after(self, repo, runner, automation_on):
        """A row must not be claimed when the budget is already gone.

        Checking after the work would claim a row and then abandon it, which
        is the failure the abort-between-items check already avoids.
        """
        repo.enqueue(wanted_item_id=7200, file_path="/m/a.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=7201, file_path="/m/b.mkv", target_language="ger")

        clock = {"t": 0.0}

        def fake_monotonic():
            return clock["t"]

        def advance(*_a, **_kw):
            clock["t"] += 500.0
            return {"status": "ok", "output_path": "/m/x.ger.srt"}

        with (
            patch("services.subtitle_automation_runner.time.monotonic", fake_monotonic),
            patch(
                "services.subtitle_automation_runner._extract_embedded_sub",
                side_effect=advance,
            ),
        ):
            processed = runner.drain(max_items=2, budget_s=100)

        assert processed == 1, "the first item always runs; the second must not be claimed"
        second = repo.get_by_wanted_item(7201)
        assert second["state"] == "pending", (
            f"row 7201 was claimed despite the spent budget: state={second['state']}"
        )

    def test_a_generous_budget_does_not_cut_a_normal_tick_short(self, repo, runner, automation_on):
        """The budget must not change behaviour for ticks that fit inside it."""
        for i in range(4):
            repo.enqueue(
                wanted_item_id=7300 + i,
                file_path=f"/m/fast{i}.mkv",
                target_language="ger",
            )
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            return_value={"status": "ok", "output_path": "/m/x.ger.srt"},
        ):
            processed = runner.drain(max_items=10, budget_s=1800)
        assert processed == 4
        assert repo.get_counts()["pending"] == 0

    def test_drain_without_an_explicit_budget_uses_the_setting(self, repo, runner, automation_on):
        """The scheduler tick passes no budget — the setting must supply it."""
        repo.enqueue(wanted_item_id=7400, file_path="/m/a.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=7401, file_path="/m/b.mkv", target_language="ger")

        clock = {"t": 0.0}

        def advance(*_a, **_kw):
            clock["t"] += 700.0
            return {"status": "ok", "output_path": "/m/x.ger.srt"}

        class _S:
            subtitle_automation_budget_s = 600

        with (
            patch("services.subtitle_automation_runner.time.monotonic", lambda: clock["t"]),
            patch("services.subtitle_automation_runner.get_settings", return_value=_S()),
            patch(
                "services.subtitle_automation_runner._extract_embedded_sub",
                side_effect=advance,
            ),
        ):
            processed = runner.drain(max_items=2)

        assert processed == 1, "the 600s setting should have stopped the drain after one item"


class TestBudgetSetting:
    def test_default_is_1800_seconds(self):
        from config_settings import Settings

        assert Settings().subtitle_automation_budget_s == 1800

    def test_default_leaves_headroom_under_the_job_timeout(self):
        """The budget only helps if it fires before the JobSpec timeout.

        Prod measured a ~150s wind-down for one in-flight item and up to
        ~870s for a single sidecar translation. The gap must cover the item
        that is already running when the budget is found spent.
        """
        from config_settings import Settings
        from services.scheduler import _build_default_jobs

        spec = next(j for j in _build_default_jobs() if j.id == "subtitle_automation")
        budget = Settings().subtitle_automation_budget_s
        assert budget < spec.timeout_s, (
            f"budget {budget}s must fire before the {spec.timeout_s}s timeout"
        )
        assert spec.timeout_s - budget >= 300, (
            "too little headroom for the in-flight item to finish cleanly: "
            f"{spec.timeout_s - budget}s"
        )
