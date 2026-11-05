"""A running flag claimed for a background worker is released when the worker
never starts.

Each of these cleared its flag only inside the worker, so a failed start
(no thread available, pool shut down) left it set and every later request
answered "already running" until a restart — the shape of #248's held lock.
"""

import threading
from unittest.mock import patch

import pytest


def _boom(*a, **k):
    raise RuntimeError("can't start new thread")


def test_mt_pending_batch_claim(app_ctx):
    from services import mt_pending_approval as m

    with patch.object(m, "submit_background", _boom), pytest.raises(RuntimeError):
        m.start_batch(app_ctx, [1])

    assert m.batch_state()["running"] is False


def test_repair_job_running_flag(app_ctx):
    from services.repair import job

    with patch.object(threading.Thread, "start", _boom), pytest.raises(RuntimeError):
        job.start(app_ctx, dry_run=True)

    assert job._state.running is False


def test_wrong_episode_requeue_lock(client):
    from routes import repair

    with patch.object(threading.Thread, "start", _boom):
        client.post("/api/v1/repair/wrong-episodes/requeue", json={})

    assert not repair._requeue_lock.locked()


def test_dedup_scan_flag(client):
    from routes.cleanup import _scan_state, dedup

    with patch.object(dedup, "submit_background", _boom):
        client.post("/api/v1/cleanup/scan", json={})

    assert _scan_state["running"] is False
