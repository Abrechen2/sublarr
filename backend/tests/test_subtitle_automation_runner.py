"""Drain-worker tests for SubtitleAutomationRunner (Phase 3b).

The runner:
  1. calls `claim_next()` on the queue repo,
  2. invokes the extraction helper (_extract_embedded_sub) for the claim,
  3. calls `mark_done` on success or `mark_failed` with an exponential
     backoff `next_retry_at` on failure.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)
from services.subtitle_automation_runner import (
    SubtitleAutomationRunner,
    compute_backoff,
)


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


@pytest.fixture
def runner(app_ctx):
    return SubtitleAutomationRunner()


@pytest.fixture
def automation_on():
    """Enable the master toggle for drain tests. Patched at the module
    level so `runner.drain()` sees it without touching config storage."""
    with patch(
        "services.subtitle_automation_runner._automation_enabled",
        return_value=True,
    ):
        yield


class TestExponentialBackoff:
    """compute_backoff maps attempt_count → next_retry_at delay."""

    def test_first_retry_five_minutes(self):
        assert compute_backoff(attempt=1) == timedelta(minutes=5)

    def test_second_retry_fifteen_minutes(self):
        assert compute_backoff(attempt=2) == timedelta(minutes=15)

    def test_third_retry_one_hour(self):
        assert compute_backoff(attempt=3) == timedelta(hours=1)

    def test_fourth_retry_six_hours(self):
        assert compute_backoff(attempt=4) == timedelta(hours=6)

    def test_fifth_retry_twenty_four_hours(self):
        assert compute_backoff(attempt=5) == timedelta(hours=24)

    def test_later_retries_capped_at_twenty_four_hours(self):
        assert compute_backoff(attempt=10) == timedelta(hours=24)
        assert compute_backoff(attempt=99) == timedelta(hours=24)


class TestProcessOne:
    def test_returns_false_when_queue_empty(self, runner):
        assert runner.process_one() is False

    def test_success_marks_done(self, repo, runner):
        repo.enqueue(wanted_item_id=1, file_path="/m/a.mkv", target_language="ger")
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            return_value={"status": "ok", "output_path": "/m/a.ger.srt"},
        ):
            processed = runner.process_one()
        assert processed is True
        e = repo.get_by_wanted_item(1)
        assert e["state"] == "done"
        assert e["attempt_count"] == 0  # never incremented on success
        assert e["last_finished_at"] is not None

    def test_failure_marks_failed_with_backoff(self, repo, runner):
        repo.enqueue(wanted_item_id=2, file_path="/m/b.mkv", target_language="ger")
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            side_effect=LookupError("No suitable subtitle stream"),
        ):
            processed = runner.process_one()
        assert processed is True
        e = repo.get_by_wanted_item(2)
        assert e["state"] == "failed"
        assert e["attempt_count"] == 1
        assert e["next_retry_at"] is not None
        assert "No suitable subtitle stream" in e["last_error"]

    def test_missing_file_does_not_retry_infinitely(self, repo, runner):
        """A FileNotFoundError means the media file is gone — no retry."""
        repo.enqueue(wanted_item_id=3, file_path="/m/gone.mkv", target_language="ger")
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            side_effect=FileNotFoundError("Media file not found"),
        ):
            runner.process_one()
        e = repo.get_by_wanted_item(3)
        assert e["state"] == "failed"
        # next_retry_at None signals "terminal, don't retry".
        assert e["next_retry_at"] is None


class TestDrain:
    def test_drain_processes_all_pending_items(self, repo, runner, automation_on):
        for i in range(5):
            repo.enqueue(
                wanted_item_id=100 + i,
                file_path=f"/m/{i}.mkv",
                target_language="ger",
            )
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            return_value={"status": "ok", "output_path": "/m/x.ger.srt"},
        ):
            processed = runner.drain(max_items=10)
        assert processed == 5
        counts = repo.get_counts()
        assert counts["done"] == 5
        assert counts["pending"] == 0

    def test_drain_respects_max_items_limit(self, repo, runner, automation_on):
        """Scheduler tick should not hog the worker forever."""
        for i in range(20):
            repo.enqueue(
                wanted_item_id=200 + i,
                file_path=f"/m/{i}.mkv",
                target_language="ger",
            )
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            return_value={"status": "ok", "output_path": "/m/x.ger.srt"},
        ):
            processed = runner.drain(max_items=3)
        assert processed == 3
        counts = repo.get_counts()
        assert counts["done"] == 3
        assert counts["pending"] == 17

    def test_drain_stops_on_empty_queue(self, repo, runner, automation_on):
        repo.enqueue(wanted_item_id=300, file_path="/m/a.mkv", target_language="ger")
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            return_value={"status": "ok", "output_path": "/m/x.ger.srt"},
        ):
            # max_items=100 but only 1 item present — must return 1, not loop.
            processed = runner.drain(max_items=100)
        assert processed == 1

    def test_drain_continues_past_single_failure(self, repo, runner, automation_on):
        """One item failing shouldn't abort the whole drain."""
        repo.enqueue(wanted_item_id=400, file_path="/m/a.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=401, file_path="/m/b.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=402, file_path="/m/c.mkv", target_language="ger")

        call_count = {"n": 0}

        def flaky(item_id, file_path, auto_translate=False):
            call_count["n"] += 1
            if item_id == 401:
                raise RuntimeError("ffprobe failed")
            return {"status": "ok", "output_path": f"/m/{item_id}.ger.srt"}

        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            side_effect=flaky,
        ):
            processed = runner.drain(max_items=10)
        assert processed == 3
        # 400 and 402 done, 401 failed.
        assert repo.get_by_wanted_item(400)["state"] == "done"
        assert repo.get_by_wanted_item(401)["state"] == "failed"
        assert repo.get_by_wanted_item(402)["state"] == "done"


class TestMasterToggleGate:
    def test_runner_noop_when_master_toggle_off(self, repo, runner):
        """If subtitle_automation_enabled is False, drain should do nothing
        even with pending rows — user hasn't opted in."""
        repo.enqueue(wanted_item_id=500, file_path="/m/a.mkv", target_language="ger")
        with (
            patch("services.subtitle_automation_runner._extract_embedded_sub") as extract_mock,
            patch(
                "services.subtitle_automation_runner._automation_enabled",
                return_value=False,
            ),
        ):
            processed = runner.drain(max_items=10)
        assert processed == 0
        extract_mock.assert_not_called()
        assert repo.get_by_wanted_item(500)["state"] == "pending"
