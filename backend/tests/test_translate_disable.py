"""Tests for translation disable: job cancellation and /translate/disable endpoint."""
import pytest


def test_disable_endpoint_sets_flag_and_cancels_jobs(app_ctx, temp_db):
    """POST /translate/disable sets translation_enabled=false and cancels queued jobs."""
    from db.jobs import create_job, get_job

    job = create_job("/media/test.mkv")

    with app_ctx.test_client() as client:
        resp = client.post("/api/v1/translate/disable")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "disabled"
    assert data["cancelled_jobs"] >= 1
    assert get_job(job["id"])["status"] == "cancelled"


def test_disable_endpoint_returns_200_when_no_jobs(app_ctx, temp_db):
    """POST /translate/disable returns 200 even when no queued jobs exist."""
    with app_ctx.test_client() as client:
        resp = client.post("/api/v1/translate/disable")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["cancelled_jobs"] == 0


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
