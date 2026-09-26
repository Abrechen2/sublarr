"""I7: scheduler run labels must reach the pool workers a run spawns.

The label rides on the cancel-event contextvar, and contextvars do not cross
into ThreadPoolExecutor workers. Only wanted_search_runner copied the context,
so every other pool a scheduled job used logged `[-]` for its own work.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from services.scheduler import cancellation


def _in_run(job_id: str, fn):
    event = cancellation.begin_run(job_id)
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


class TestCallSitesPropagate:
    def test_batch_probe_workers_log_under_the_run_label(self, monkeypatch):
        import services.wanted_item_scanner as scanner

        seen: list[str | None] = []
        lock = threading.Lock()

        def _probe(path, _flag):
            with lock:
                seen.append(cancellation.current_run_label())
            return {}

        monkeypatch.setattr(scanner, "get_media_streams", _probe)
        monkeypatch.setattr(
            scanner,
            "get_settings",
            lambda: type("S", (), {"scan_metadata_max_workers": 2})(),
        )

        _, label = _in_run("wanted_scanner", lambda: scanner.batch_probe(["/a.mkv", "/b.mkv"]))

        assert seen and all(s == label for s in seen), seen

    def test_wanted_batch_workers_log_under_the_run_label(self, monkeypatch):
        from types import SimpleNamespace

        from wanted_search import batch

        seen: list[str | None] = []
        lock = threading.Lock()

        def _process(item_id):
            with lock:
                seen.append(cancellation.current_run_label())
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

        assert len(seen) == 2 and all(s == label for s in seen), seen
