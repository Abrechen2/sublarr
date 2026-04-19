"""QueueState in-memory tracker tests."""

import pytest


def test_register_job_tracks_it():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    snap = q.active_snapshot()
    assert len(snap) == 1
    assert snap[0]["job_id"] == "abc"
    assert snap[0]["progress"]["total"] == 100
    assert snap[0]["progress"]["done"] == 0


def test_progress_updates():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    q.update_progress("abc", done=42, cost_micro_usd_delta=500)
    snap = q.active_snapshot()[0]
    assert snap["progress"]["done"] == 42
    assert snap["cost_so_far_micro_usd"] == 500


def test_finish_moves_to_recent():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    q.finish_job("abc", status="ok")

    assert q.active_snapshot() == []
    recent = q.recent_snapshot()
    assert len(recent) == 1
    assert recent[0]["job_id"] == "abc"
    assert recent[0]["status"] == "ok"


def test_cancel_sets_flag():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    assert q.is_cancelled("abc") is False
    q.cancel("abc")
    assert q.is_cancelled("abc") is True


def test_cancel_unknown_raises_keyerror():
    from translation.queue_state import QueueState

    q = QueueState()
    with pytest.raises(KeyError):
        q.cancel("nope")


def test_double_cancel_is_idempotent():
    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    q.cancel("abc")
    q.cancel("abc")
    assert q.is_cancelled("abc") is True


def test_recent_trims_to_20():
    from translation.queue_state import QueueState

    q = QueueState()
    for i in range(25):
        q.register_job(
            job_id=f"j{i}",
            file_path=f"/x/{i}.mkv",
            source_lang="en",
            target_lang="de",
            backend="ollama",
            total_lines=1,
        )
        q.finish_job(f"j{i}", status="ok")

    assert len(q.recent_snapshot()) == 20


def test_eta_seconds_computed():
    import time

    from translation.queue_state import QueueState

    q = QueueState()
    q.register_job(
        job_id="abc",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=100,
    )
    time.sleep(0.1)
    q.update_progress("abc", done=10)
    snap = q.active_snapshot()[0]
    assert snap["eta_seconds"] is not None
    assert 0 <= snap["eta_seconds"] <= 5


def test_thread_safety_stress():
    import threading

    from translation.queue_state import QueueState

    q = QueueState()

    def worker(i):
        q.register_job(
            job_id=f"j{i}",
            file_path=f"/x/{i}.mkv",
            source_lang="en",
            target_lang="de",
            backend="claude",
            total_lines=100,
        )
        for done in range(0, 100, 10):
            q.update_progress(f"j{i}", done=done)
        q.finish_job(f"j{i}", status="ok")

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    assert q.active_snapshot() == []
    assert len(q.recent_snapshot()) == 20
