"""A stop request has to reach the work, not just the loop that hands it out.

Prod 2026-08-15, the wind-down of a cancelled `wanted_search`:

    15:21:18  timeout reached, stop requested
    15:24:44  Auto-sync: STARTING ffsubsync      <- started AFTER the request
    15:25:41  Auto-sync: STARTING ffsubsync
    15:26:18  scheduler: did NOT stop when asked (300s grace spent)
    15:28:00  Auto-sync: STARTING ffsubsync
    15:28:05  Wanted search cancelled after 140/2100 items
    15:28:32  Auto-sync: STARTING ffsubsync

Two defects, one cause. `abort_requested()` reads a `contextvars` variable
bound by the scheduler to the *tick* thread, and contextvars do not cross into
`ThreadPoolExecutor` workers — `_search_with_ctx` carried the Flask app context
over but not the stop signal. So every check below it silently saw "nobody
asked us to stop", and auto-sync, which never checked at all, kept starting
minute-long ffsubsync runs long after the grace had expired.

That made the wind-down unbounded: it lasts as long as the in-flight items feel
like syncing. No `cancel_grace_s` value can be right against an unbounded tail,
which is why raising the grace to 300s (c5c50013) did not stop the label from
reading `timeout_abandoned`.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from services.scheduler import cancellation


class TestStopSignalCrossesIntoWorkers:
    def test_plain_submit_loses_the_signal(self):
        """The bug, pinned. If this ever fails, the platform changed."""
        event = threading.Event()
        event.set()
        token = cancellation.activate(event)
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                seen = ex.submit(cancellation.abort_requested).result()
        finally:
            cancellation.deactivate(token)

        assert seen is False, (
            "contextvars are expected NOT to propagate into pool workers — "
            "this test documents why the propagation below is needed"
        )

    def test_runner_submit_carries_the_signal(self):
        """The fix: work handed to a worker must see the stop request."""
        from services.wanted_search_runner import _submit_with_context

        event = threading.Event()
        event.set()
        token = cancellation.activate(event)
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                seen = _submit_with_context(ex, cancellation.abort_requested).result()
        finally:
            cancellation.deactivate(token)

        assert seen is True

    def test_no_stop_requested_stays_false_in_the_worker(self):
        """Propagation must not invent a stop that nobody asked for."""
        from services.wanted_search_runner import _submit_with_context

        event = threading.Event()  # deliberately NOT set
        token = cancellation.activate(event)
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                seen = _submit_with_context(ex, cancellation.abort_requested).result()
        finally:
            cancellation.deactivate(token)

        assert seen is False

    def test_arguments_are_passed_through_unchanged(self):
        """The seam that already broke six test doubles once — keep it honest."""
        from services.wanted_search_runner import _submit_with_context

        with ThreadPoolExecutor(max_workers=1) as ex:
            got = _submit_with_context(ex, lambda a, b, c=None: (a, b, c), 1, 2, c=3).result()

        assert got == (1, 2, 3)


class TestAutoSyncNeverRunsOnTheSearchThread:
    """The stop check this class used to pin is gone, and better so.

    Auto-sync once ran ffsubsync inline and asked `abort_requested()` first,
    so that a cancel would not start a fresh ten-minute correction. That check
    only ever bounded the damage: an item that got past it still held the
    sweep for up to 600s, which is what left three prod runs recorded
    `timeout_abandoned` (2026-08-15/16).

    The search now only enqueues, so there is no expensive work left on this
    thread to refuse — and refusing an INSERT would drop the correction rather
    than defer it. What is asserted here is the stronger property: ffsubsync
    is not reachable from the search path at all, cancel or no cancel.
    """

    def _settings(self):
        s = MagicMock()
        s.auto_sync_after_download = True
        s.auto_sync_engine = "ffsubsync"
        return s

    def _enqueue_patch(self):
        return patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue"
        )

    def test_does_not_run_ffsubsync_after_a_stop_request(self, tmp_path):
        """The measured defect: new ffsubsync runs started minutes after cancel."""
        from wanted_search.post_processor import _try_auto_sync

        sub = tmp_path / "e.srt"
        vid = tmp_path / "e.mkv"
        sub.touch()
        vid.touch()

        event = threading.Event()
        event.set()
        token = cancellation.activate(event)
        try:
            with (
                patch("services.video_sync.sync_with_ffsubsync") as mock_sync,
                self._enqueue_patch(),
            ):
                _try_auto_sync(
                    str(sub), str(vid), self._settings(), item_id=1, target_language="de"
                )
        finally:
            cancellation.deactivate(token)

        mock_sync.assert_not_called()

    def test_does_not_run_ffsubsync_when_nobody_asked_to_stop_either(self, tmp_path):
        """No cancel in sight, and still nothing expensive happens here."""
        from wanted_search.post_processor import _try_auto_sync

        sub = tmp_path / "e.srt"
        vid = tmp_path / "e.mkv"
        sub.touch()
        vid.touch()

        with (
            patch("services.video_sync.sync_with_ffsubsync") as mock_sync,
            self._enqueue_patch(),
        ):
            _try_auto_sync(str(sub), str(vid), self._settings(), item_id=2, target_language="de")

        mock_sync.assert_not_called()

    def test_a_stop_request_does_not_drop_the_correction(self, tmp_path):
        """A cancelled sweep must still leave the correction due.

        The old inline version had to skip it outright — the work could not be
        deferred, only abandoned. Queueing it costs one INSERT, so a stop is no
        longer a reason to lose it.
        """
        from wanted_search.post_processor import _try_auto_sync

        sub = tmp_path / "e.srt"
        vid = tmp_path / "e.mkv"
        sub.touch()
        vid.touch()

        event = threading.Event()
        event.set()
        token = cancellation.activate(event)
        try:
            with self._enqueue_patch() as enqueue:
                _try_auto_sync(
                    str(sub), str(vid), self._settings(), item_id=3, target_language="de"
                )
        finally:
            cancellation.deactivate(token)

        assert enqueue.call_count == 1
