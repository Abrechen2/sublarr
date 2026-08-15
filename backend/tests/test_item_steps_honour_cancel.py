"""One item is five sequential provider sweeps, and nothing checked between them.

`_run_search_steps` tries Step 1 → 2 → 3 → 4 → 5 in order, each a full search
across every enabled provider with its own retries. Until now the only stop
check in the whole per-item path was the auto-sync guard, so once an item had
started it ran its remaining steps to the end no matter what the scheduler had
asked for.

That is what filled the wind-down of a cancelled tick on prod 2026-08-15: after
the item loop stopped at 71s, the log showed eight further
`search_coordinator.retry` lines, plus downloads and a remux, for nearly four
more minutes — items working through the steps they had left.

Stopping between steps is safe precisely because a step is self-contained: it
searches, and on success downloads and saves. Nothing is half-written at the
boundary.

The item must NOT be charged for the stop. `record_search_outcome` sets
`failure_kind` and `retry_after`, so treating a cancelled item as a failed
search would push it into a backoff it never earned — the same mistake the
automation queue made by stranding claimed rows.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.scheduler import cancellation


@pytest.fixture
def _ctx():
    """Minimal ctx for the orchestrator — every step is patched out anyway."""
    settings = MagicMock()
    settings.wanted_skip_srt_on_no_ass = False
    return {
        "item": {"id": 42, "sonarr_series_id": None},
        "item_id": 42,
        "settings": settings,
        "auto_translate": True,
        "ass_had_results": True,
        "decision_log": MagicMock(),
        "dry_run": False,
        "allow_translate_fallback": True,
    }


@pytest.fixture
def _stopped():
    """A stop request bound to this thread for the duration of the test."""
    import threading

    event = threading.Event()
    event.set()
    token = cancellation.activate(event)
    yield
    cancellation.deactivate(token)


class TestStepsStopWhenAsked:
    def test_no_provider_step_runs_after_a_stop_request(self, _ctx, _stopped):
        from wanted_search import process as proc

        with (
            patch.object(proc, "_try_target_ass_direct") as s1,
            patch.object(proc, "_try_source_ass_translation") as s2,
            patch.object(proc, "_try_target_srt_direct") as s3,
            patch.object(proc, "_try_source_srt_translation") as s4,
            patch.object(proc, "_fallback_translate_file") as s5,
        ):
            result = proc._run_search_steps(_ctx)

        for name, step in (("1", s1), ("2", s2), ("3", s3), ("4", s4), ("5", s5)):
            step.assert_not_called(), f"Step {name} ran after a stop request"
        assert result["status"] == "stopped"

    def test_stops_between_steps_when_the_request_arrives_mid_item(self, _ctx):
        """The realistic case: the item is already running when cancel lands."""
        import threading

        from wanted_search import process as proc

        event = threading.Event()
        token = cancellation.activate(event)
        try:
            # Step 1 finds nothing and the stop arrives while it runs.
            def _step1_then_cancel(ctx):
                event.set()
                return None

            with (
                patch.object(proc, "_try_target_ass_direct", side_effect=_step1_then_cancel),
                patch.object(proc, "_try_source_ass_translation") as s2,
                patch.object(proc, "_try_target_srt_direct") as s3,
                patch.object(proc, "_fallback_translate_file") as s5,
            ):
                result = proc._run_search_steps(_ctx)
        finally:
            cancellation.deactivate(token)

        s2.assert_not_called()
        s3.assert_not_called()
        s5.assert_not_called()
        assert result["status"] == "stopped"

    def test_a_stopped_item_is_not_charged_a_failed_search(self, _ctx, _stopped):
        """No backoff for work that was never allowed to finish."""
        from wanted_search import process as proc

        with (
            patch.object(proc, "_try_target_ass_direct", return_value=None),
            patch("services.wanted_search_runner.record_search_outcome") as rec,
        ):
            proc._run_search_steps(_ctx)

        rec.assert_not_called()

    def test_stopped_is_neither_found_nor_failed(self, _ctx, _stopped):
        """The runner counts `found`/`failed` specially; a stop is neither."""
        from wanted_search import process as proc

        with patch.object(proc, "_try_target_ass_direct", return_value=None):
            result = proc._run_search_steps(_ctx)

        assert result["status"] not in ("found", "failed")
        assert result["wanted_id"] == 42


class TestNormalPathUnaffected:
    def test_all_steps_still_run_when_nobody_asked_to_stop(self, _ctx):
        from wanted_search import process as proc

        with (
            patch.object(proc, "_try_target_ass_direct", return_value=None) as s1,
            patch.object(proc, "_try_source_ass_translation", return_value=None) as s2,
            patch.object(proc, "_try_target_srt_direct", return_value=None) as s3,
            patch.object(proc, "_try_source_srt_translation", return_value=None) as s4,
            patch.object(proc, "_fallback_translate_file", return_value={"status": "not_found"}),
        ):
            proc._run_search_steps(_ctx)

        s1.assert_called_once()
        s2.assert_called_once()
        s3.assert_called_once()
        s4.assert_called_once()

    def test_a_hit_in_step_1_still_returns_it(self, _ctx):
        from wanted_search import process as proc

        hit = {"wanted_id": 42, "status": "found"}
        with (
            patch.object(proc, "_try_target_ass_direct", return_value=hit),
            patch.object(proc, "_try_source_ass_translation") as s2,
        ):
            result = proc._run_search_steps(_ctx)

        assert result is hit
        s2.assert_not_called()
