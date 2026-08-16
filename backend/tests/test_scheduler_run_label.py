"""Scheduled runs identify themselves in the log.

Every record logged outside a Flask request renders `[-]` for its
request-id slot. Sweep work, webhook work and queue-drain work all log
from background threads through the same module names, so a line like
`wanted_search.post_processor: Auto-sync: starting ffsubsync` cannot be
attributed to a run.

That cost a diagnosis on 2026-08-15: a `wanted_search` tick was recorded
`timeout_abandoned`, and the work still running afterwards was
indistinguishable from concurrent Sonarr-webhook work. The label rides on
the cancellation event, which the scheduler already propagates correctly
into nested pools — so it reaches exactly the threads that belong to the
run, and nothing else.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from services.scheduler import cancellation


class TestRunLabel:
    def test_none_outside_a_run(self):
        assert cancellation.current_run_label() is None

    def test_names_the_job_inside_a_run(self):
        event = cancellation.begin_run("wanted_search")
        try:
            with cancellation.bound(event):
                label = cancellation.current_run_label()
            assert label is not None
            assert label.startswith("wanted_search:")
        finally:
            cancellation.end_run("wanted_search", event)

    def test_two_runs_of_one_job_are_distinguishable(self):
        """Consecutive runs must not share an id, or the log cannot separate
        an abandoned run from the run that replaced it."""
        first = cancellation.begin_run("wanted_search")
        first_label = None
        with cancellation.bound(first):
            first_label = cancellation.current_run_label()
        second = cancellation.begin_run("wanted_search")
        try:
            with cancellation.bound(second):
                assert cancellation.current_run_label() != first_label
        finally:
            cancellation.end_run("wanted_search", second)
            cancellation.end_run("wanted_search", first)

    def test_reaches_a_nested_pool_worker(self):
        """The trap this whole mechanism exists for.

        `ThreadPoolExecutor.submit` does not carry context into the worker.
        A job that owns a nested pool must re-bind inside it — and when it
        does, the label has to follow the event.
        """
        event = cancellation.begin_run("wanted_search")
        seen = []

        def work():
            with cancellation.bound(event):
                seen.append(cancellation.current_run_label())

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(work).result(timeout=10)
            assert seen and seen[0].startswith("wanted_search:")
        finally:
            cancellation.end_run("wanted_search", event)

    def test_unbound_worker_sees_nothing(self):
        """A thread that never bound the event is not part of the run —
        webhook work running concurrently must stay unlabelled."""
        event = cancellation.begin_run("wanted_search")
        seen = []
        try:
            with cancellation.bound(event), ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(lambda: seen.append(cancellation.current_run_label())).result(
                    timeout=10
                )
            assert seen == [None]
        finally:
            cancellation.end_run("wanted_search", event)

    def test_label_gone_after_end_run(self):
        event = cancellation.begin_run("wanted_search")
        cancellation.end_run("wanted_search", event)
        with cancellation.bound(event):
            assert cancellation.current_run_label() is None


class TestLogRecordCarriesLabel:
    def test_record_outside_a_run_keeps_the_placeholder(self):
        from app_logging import NO_REQUEST_ID, _current_request_id

        assert _current_request_id() == NO_REQUEST_ID

    def test_record_inside_a_run_carries_the_label(self):
        from app_logging import _current_request_id

        event = cancellation.begin_run("subtitle_automation")
        try:
            with cancellation.bound(event):
                assert _current_request_id().startswith("subtitle_automation:")
        finally:
            cancellation.end_run("subtitle_automation", event)

    def test_formatting_a_record_inside_a_run_does_not_raise(self):
        """`%(request_id)s` is in LOG_FORMAT — a lookup that raises here
        drops the record and sends the traceback to stderr."""
        from app_logging import LOG_FORMAT, RequestIdFilter

        event = cancellation.begin_run("wanted_search")
        try:
            with cancellation.bound(event):
                record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
                RequestIdFilter().filter(record)
                rendered = logging.Formatter(LOG_FORMAT).format(record)
            assert "wanted_search:" in rendered
        finally:
            cancellation.end_run("wanted_search", event)

    def test_thread_without_binding_is_unlabelled(self):
        from app_logging import NO_REQUEST_ID, _current_request_id

        event = cancellation.begin_run("wanted_search")
        seen = []
        try:
            with cancellation.bound(event):
                t = threading.Thread(target=lambda: seen.append(_current_request_id()))
                t.start()
                t.join(timeout=10)
            assert seen == [NO_REQUEST_ID]
        finally:
            cancellation.end_run("wanted_search", event)
