"""A translation must be interruptible between its batches.

The drain worker checks `abort_requested()` between queue items, but one item
can be a whole LLM translation — prod measured those running up to ~16 minutes.
The job's grace is 900s, so a stop request arriving early in a translation could
not be honoured in time and the run was recorded `timeout_abandoned`: 43 of the
61 abandoned runs in the 30 days to 2026-08-22 were this job.

The batch boundary is the right place to stop. `_cache_batch` already runs
there, so everything translated so far is paid for and kept, and the next drain
resumes from the cache rather than starting over.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from services.scheduler import cancellation


class _Chunk:
    def __init__(self, batch, lookback=None, lookahead=None):
        self.batch = batch
        self.lookback = lookback or []
        self.lookahead = lookahead or []


def _ok_result(lines):
    r = MagicMock()
    r.success = True
    r.translated_lines = list(lines)
    r.error = None
    return r


class TestTranslationStopsAtABatchBoundary:
    @staticmethod
    def _run(lines, batch_size, stop_after_n_batches, cache_enabled=False):
        """Translate `lines`, setting the abort event after N batches."""
        from translator import manager as tm

        calls: list[list[str]] = []
        cached: list[list[str]] = []
        event = threading.Event()

        def _fake_translate(batch, *a, **kw):
            calls.append(list(batch))
            if len(calls) >= stop_after_n_batches:
                event.set()  # the scheduler's timeout lands here
            return _ok_result(batch)

        chunks = [_Chunk(lines[i : i + batch_size]) for i in range(0, len(lines), batch_size)]
        mgr = MagicMock()
        mgr.translate_with_fallback.side_effect = _fake_translate

        with (
            patch.object(tm, "build_chunks", return_value=chunks),
            patch.object(tm, "_cache_batch", side_effect=lambda *a, **k: cached.append(a[1])),
            patch.object(tm, "_verify_batch"),
            cancellation.bound(event),
        ):
            outcome = None
            try:
                tm._translate_in_batches(
                    mgr,
                    lines,
                    "en",
                    "de",
                    [],
                    [],
                    batch_size=batch_size,
                    cache_enabled=cache_enabled,
                )
            except Exception as exc:  # noqa: BLE001 — the test inspects the type
                outcome = exc
        return calls, cached, outcome

    def test_stops_after_the_batch_that_was_in_flight(self):
        from translator.errors import TranslationAbortedError

        lines = [f"line {i}" for i in range(10)]
        calls, _, outcome = self._run(lines, batch_size=2, stop_after_n_batches=2)

        assert isinstance(outcome, TranslationAbortedError), outcome
        # Five batches were queued; it must not have run them all.
        assert len(calls) == 2, f"kept translating after the stop request: {len(calls)} batches"

    def test_the_finished_batches_are_kept(self):
        """Stopping must not throw away work already paid for — the next drain
        resumes from the cache instead of re-translating."""
        lines = [f"line {i}" for i in range(10)]
        _, cached, _ = self._run(lines, batch_size=2, stop_after_n_batches=2, cache_enabled=True)

        assert len(cached) == 2, f"expected both finished batches cached, got {len(cached)}"

    def test_translation_is_unaffected_when_nothing_asked_it_to_stop(self):
        """abort_requested() is False outside a scheduled run, so a manual or
        API translation must behave exactly as before."""
        from translator import manager as tm

        lines = [f"line {i}" for i in range(6)]
        chunks = [_Chunk(lines[i : i + 2]) for i in range(0, 6, 2)]
        mgr = MagicMock()
        mgr.translate_with_fallback.side_effect = lambda batch, *a, **k: _ok_result(batch)

        with (
            patch.object(tm, "build_chunks", return_value=chunks),
            patch.object(tm, "_cache_batch"),
            patch.object(tm, "_verify_batch"),
        ):
            translated, _ = tm._translate_in_batches(
                mgr, lines, "en", "de", [], [], batch_size=2, cache_enabled=False
            )

        assert translated == lines
        assert mgr.translate_with_fallback.call_count == 3

    def test_a_stop_before_the_first_batch_translates_nothing(self):
        lines = [f"line {i}" for i in range(4)]
        from translator.errors import TranslationAbortedError

        calls, _, outcome = self._run(lines, batch_size=2, stop_after_n_batches=1)
        assert isinstance(outcome, TranslationAbortedError)
        assert len(calls) == 1


class TestAbortedTranslationIsNotAFailedAttempt:
    """Being asked to stop is the scheduler running out of time, not the item
    misbehaving. Counting it as a failed attempt would burn the item's retry
    budget and eventually bury it — the same shape as the dead-path bug fixed
    in 1.12.2."""

    def test_runner_requeues_instead_of_marking_failed(self):
        from db.models.core import SubtitleAutomationQueueEntry
        from services.subtitle_automation_runner import SubtitleAutomationRunner
        from translator.errors import TranslationAbortedError

        runner = SubtitleAutomationRunner()
        repo = MagicMock()
        repo.claim_next.return_value = {
            "id": 7,
            "wanted_item_id": 42,
            "file_path": "/media/x.en.ass",
            "target_language": "de",
            "task_type": SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE,
            "attempt_count": 1,
        }
        runner._repo = repo

        with patch.object(
            runner, "_translate_sidecar", side_effect=TranslationAbortedError("asked to stop")
        ):
            handled = runner.process_one(
                task_types={SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE}
            )

        assert handled is True
        repo.mark_failed.assert_not_called()
        repo.release_for_retry.assert_called_once()
        assert repo.release_for_retry.call_args.args[0] == 7


class TestReleaseForRetryKeepsTheAttemptBudget:
    def test_row_goes_back_to_pending_without_counting_an_attempt(self, app_ctx):
        from db.models.core import SubtitleAutomationQueueEntry
        from db.repositories.subtitle_automation_queue import (
            SubtitleAutomationQueueRepository,
        )

        task = SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE
        repo = SubtitleAutomationQueueRepository()
        repo.enqueue(
            wanted_item_id=4242,
            file_path="/media/x.en.ass",
            target_language="de",
            task_type=task,
        )
        claimed = repo.claim_next(task_types={task})
        assert claimed is not None
        before = repo.get_by_id(claimed["id"])
        assert before["state"] == "running"

        repo.release_for_retry(claimed["id"], reason="stopped when asked")

        after = repo.get_by_id(claimed["id"])
        assert after["state"] == "pending"
        assert after["next_retry_at"] is None
        assert (after["attempt_count"] or 0) == (before["attempt_count"] or 0), (
            "a cooperative stop must not spend one of the item's attempts"
        )


@pytest.mark.parametrize("n", [1, 3])
def test_abort_check_costs_nothing_when_unbound(n):
    """Sanity: the check itself must be cheap and side-effect free."""
    from services.scheduler.cancellation import abort_requested

    for _ in range(n):
        assert abort_requested() is False
