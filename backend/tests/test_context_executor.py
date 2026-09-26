"""I7: scheduler run labels must reach the pool workers a run spawns.

The label rides on the cancel-event contextvar, and contextvars do not cross
into ThreadPoolExecutor workers. Only wanted_search_runner copied the context,
so every other pool a scheduled job used logged `[-]` for its own work.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from services.scheduler import cancellation


def _in_run(job_id: str, fn, *, cancelled: bool = False):
    event = cancellation.begin_run(job_id)
    if cancelled:
        event.set()
    token = cancellation.activate(event)
    try:
        return fn(), cancellation.current_run_label()
    finally:
        cancellation.deactivate(token)
        cancellation.end_run(job_id, event)


class TestSubmitWithContext:
    def test_plain_submit_loses_the_label(self):
        """Documents the defect the helper exists for."""

        def work():
            with ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(cancellation.current_run_label).result()

        seen, label = _in_run("wanted_scanner", work)
        assert label is not None
        assert seen is None

    def test_helper_carries_the_label(self):
        from utils.context_executor import submit_with_context

        def work():
            with ThreadPoolExecutor(max_workers=1) as ex:
                return submit_with_context(ex, cancellation.current_run_label).result()

        seen, label = _in_run("wanted_scanner", work)
        assert seen == label

    def test_arguments_pass_through(self):
        from utils.context_executor import submit_with_context

        with ThreadPoolExecutor(max_workers=1) as ex:
            got = submit_with_context(ex, lambda a, b, c=None: (a, b, c), 1, 2, c=3).result()
        assert got == (1, 2, 3)

    def test_runner_alias_is_the_shared_helper(self):
        from services.wanted_search_runner import _submit_with_context
        from utils.context_executor import submit_with_context

        assert _submit_with_context is submit_with_context


def _worker_view():
    """What a pool worker sees: the log id its records carry, and the stop flag."""
    from app_logging import _current_request_id

    return _current_request_id(), cancellation.abort_requested()


class TestSubmitWithRunLabel:
    """Review I-2: copying the WHOLE context also handed workers the run's cancel
    signal (and any other contextvar). The label-only helper carries the log id
    and nothing else."""

    def test_worker_logs_under_the_run_label(self):
        from utils.context_executor import submit_with_run_label

        def work():
            with ThreadPoolExecutor(max_workers=1) as ex:
                return submit_with_run_label(ex, _worker_view).result()

        (log_id, _stop), label = _in_run("wanted_scanner", work)
        assert log_id == label

    def test_worker_does_not_inherit_the_cancel_signal(self):
        from utils.context_executor import submit_with_run_label

        def work():
            with ThreadPoolExecutor(max_workers=1) as ex:
                return submit_with_run_label(ex, _worker_view).result()

        (_log_id, stop), _ = _in_run("wanted_scanner", work, cancelled=True)
        assert stop is False

    def test_label_does_not_stick_to_the_pool_thread(self):
        from utils.context_executor import submit_with_run_label

        with ThreadPoolExecutor(max_workers=1) as ex:
            _in_run("wanted_scanner", lambda: submit_with_run_label(ex, _worker_view).result())
            log_id, _ = ex.submit(_worker_view).result()
        assert log_id == "-"

    def test_outside_a_run_nothing_is_attached(self):
        from utils.context_executor import submit_with_run_label

        with ThreadPoolExecutor(max_workers=1) as ex:
            log_id, stop = submit_with_run_label(ex, _worker_view).result()
        assert (log_id, stop) == ("-", False)

    def test_arguments_pass_through(self):
        from utils.context_executor import submit_with_run_label

        with ThreadPoolExecutor(max_workers=1) as ex:
            got = submit_with_run_label(ex, lambda a, b, c=None: (a, b, c), 1, 2, c=3).result()
        assert got == (1, 2, 3)


class TestCallSitesPropagate:
    """The sites converted in rc.2 log under the run label but must NOT see a
    cancel: a cancelled run's queued probes were refused by the media gate,
    stored as "no streams", and upserted as wrong wanted rows."""

    def test_batch_probe_workers_log_under_the_label_without_the_stop(self, monkeypatch):
        import services.wanted_item_scanner as scanner

        seen: list[tuple] = []
        lock = threading.Lock()

        def _probe(path, _flag):
            with lock:
                seen.append(_worker_view())
            return {}

        monkeypatch.setattr(scanner, "get_media_streams", _probe)
        monkeypatch.setattr(
            scanner,
            "get_settings",
            lambda: type("S", (), {"scan_metadata_max_workers": 2})(),
        )

        _, label = _in_run(
            "wanted_scanner",
            lambda: scanner.batch_probe(["/a.mkv", "/b.mkv"]),
            cancelled=True,
        )

        assert seen == [(label, False), (label, False)], seen

    def test_wanted_batch_workers_log_under_the_run_label(self, monkeypatch):
        from types import SimpleNamespace

        from wanted_search import batch

        seen: list[tuple] = []
        lock = threading.Lock()

        def _process(item_id):
            with lock:
                seen.append(_worker_view())
            return {"status": "found"}

        monkeypatch.setattr(batch, "process_wanted_item", _process)
        monkeypatch.setattr(
            batch, "get_settings", lambda: SimpleNamespace(wanted_max_search_attempts=5)
        )
        monkeypatch.setattr(
            batch, "get_wanted_item", lambda iid: {"id": iid, "search_count": 0, "title": "x"}
        )

        _, label = _in_run(
            "wanted_search", lambda: list(batch.process_wanted_batch(item_ids=[1, 2]))
        )

        assert len(seen) == 2 and all(v == (label, False) for v in seen), seen
