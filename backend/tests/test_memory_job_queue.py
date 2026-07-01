"""Tests for the in-process MemoryJobQueue, focused on Flask app-context.

Regression coverage for the silent translation breakage: jobs run in a
ThreadPoolExecutor thread that has NO Flask app context by default, so any
DB-touching job (translation `_run_job`) raised "Working outside of
application context". The queue must push `app.app_context()` when given an
app — mirroring the RQ `worker.py` `_AppContextWorker`.
"""

import time

from flask import Flask, has_app_context

from job_queue.memory_queue import MemoryJobQueue


def _wait(q, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = q.get_job(job_id)
        if info and info.status.value in ("completed", "failed"):
            return info
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_job_runs_inside_app_context_when_app_provided():
    app = Flask(__name__)
    seen = {}

    def job():
        seen["in_ctx"] = has_app_context()
        return "ok"

    q = MemoryJobQueue(max_workers=1, app=app)
    job_id = q.enqueue(job)
    info = _wait(q, job_id)

    assert info.status.value == "completed"
    assert seen["in_ctx"] is True


def test_job_runs_without_context_when_no_app():
    seen = {}

    def job():
        seen["in_ctx"] = has_app_context()
        return "ok"

    q = MemoryJobQueue(max_workers=1)  # no app -> backward compatible
    job_id = q.enqueue(job)
    info = _wait(q, job_id)

    assert info.status.value == "completed"
    assert seen["in_ctx"] is False


def test_create_job_queue_forwards_app_to_memory_backend():
    from job_queue import create_job_queue

    app = Flask(__name__)
    q = create_job_queue("", app=app)  # empty redis_url -> memory backend

    assert isinstance(q, MemoryJobQueue)
    assert q._app is app
