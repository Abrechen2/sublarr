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


class TestAutoSyncHonoursTheStopRequest:
    def _settings(self):
        s = MagicMock()
        s.auto_sync_after_download = True
        s.auto_sync_engine = "ffsubsync"
        return s

    def test_does_not_start_a_new_sync_after_a_stop_request(self, tmp_path):
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
            with patch("services.video_sync.sync_with_ffsubsync") as mock_sync:
                _try_auto_sync(str(sub), str(vid), self._settings())
        finally:
            cancellation.deactivate(token)

        mock_sync.assert_not_called()

    def test_the_skip_is_logged(self, tmp_path, caplog):
        import logging

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
                caplog.at_level(logging.INFO),
                patch("services.video_sync.sync_with_ffsubsync"),
            ):
                _try_auto_sync(str(sub), str(vid), self._settings())
        finally:
            cancellation.deactivate(token)

        text = " ".join(r.getMessage() for r in caplog.records)
        assert "auto-sync" in text.lower() and "stop" in text.lower()

    def test_still_syncs_when_nobody_asked_to_stop(self, tmp_path):
        """Guards the change: the normal path must be untouched."""
        from wanted_search.post_processor import _try_auto_sync

        sub = tmp_path / "e.srt"
        vid = tmp_path / "e.mkv"
        sub.touch()
        vid.touch()

        with patch("services.video_sync.sync_with_ffsubsync") as mock_sync:
            _try_auto_sync(str(sub), str(vid), self._settings())

        mock_sync.assert_called_once_with(str(sub), str(vid))
