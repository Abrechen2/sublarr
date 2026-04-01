"""Tests for translation disable: job cancellation."""
import pytest


def test_cancel_queued_jobs_cancels_only_queued(app_ctx, temp_db):
    """cancel_queued_jobs() marks queued jobs as cancelled, leaves running/completed alone."""
    from db.jobs import cancel_queued_jobs, create_job, update_job, get_job

    queued_job = create_job("/media/queued.mkv")
    running_job = create_job("/media/running.mkv")
    update_job(running_job["id"], "running")
    done_job = create_job("/media/done.mkv")
    update_job(done_job["id"], "completed", result={})

    cancelled_count = cancel_queued_jobs()

    assert get_job(queued_job["id"])["status"] == "cancelled"
    assert get_job(running_job["id"])["status"] == "running"
    assert get_job(done_job["id"])["status"] == "completed"
    assert cancelled_count == 1


def test_cancel_queued_jobs_returns_zero_when_none(app_ctx, temp_db):
    """cancel_queued_jobs() returns 0 when no queued jobs exist."""
    from db.jobs import cancel_queued_jobs

    count = cancel_queued_jobs()
    assert count == 0
