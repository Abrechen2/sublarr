"""HTTP tests for job cancel/clear — DELETE /jobs/<id> and POST /jobs/clear-queued."""

# ---------------------------------------------------------------------------
# DELETE /api/v1/jobs/<job_id> — cancel queued / delete finished
# ---------------------------------------------------------------------------


def test_delete_queued_job_cancels_it(app_ctx, temp_db):
    """DELETE on a queued job soft-cancels it (row stays, status=cancelled)."""
    from db.jobs import create_job, get_job

    job = create_job("/media/queued.mkv")

    with app_ctx.test_client() as client:
        resp = client.delete(f"/api/v1/jobs/{job['id']}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "cancelled"
    assert data["job_id"] == job["id"]

    stored = get_job(job["id"])
    assert stored["status"] == "cancelled"
    assert stored["completed_at"] is not None


def test_delete_running_job_returns_409(app_ctx, temp_db):
    """DELETE on a running job is rejected with 409 and leaves it running."""
    from db.jobs import create_job, get_job, update_job

    job = create_job("/media/running.mkv")
    update_job(job["id"], "running")

    with app_ctx.test_client() as client:
        resp = client.delete(f"/api/v1/jobs/{job['id']}")

    assert resp.status_code == 409
    assert "running" in resp.get_json()["error"].lower()
    assert get_job(job["id"])["status"] == "running"


def test_delete_failed_job_removes_row(app_ctx, temp_db):
    """DELETE on a failed job hard-deletes the row."""
    from db.jobs import create_job, get_job, update_job

    job = create_job("/media/failed.mkv")
    update_job(job["id"], "failed", error="boom")

    with app_ctx.test_client() as client:
        resp = client.delete(f"/api/v1/jobs/{job['id']}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "deleted"
    assert get_job(job["id"]) is None


def test_delete_completed_job_removes_row(app_ctx, temp_db):
    """DELETE on a completed job hard-deletes the row."""
    from db.jobs import create_job, get_job, update_job

    job = create_job("/media/done.mkv")
    update_job(job["id"], "completed", result={})

    with app_ctx.test_client() as client:
        resp = client.delete(f"/api/v1/jobs/{job['id']}")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "deleted"
    assert get_job(job["id"]) is None


def test_delete_unknown_job_returns_404(app_ctx, temp_db):
    with app_ctx.test_client() as client:
        resp = client.delete("/api/v1/jobs/nonexist")

    assert resp.status_code == 404
    assert "not found" in resp.get_json()["error"].lower()


def test_delete_queued_job_race_to_running_returns_409(app_ctx, temp_db):
    """A job that turns running between read and conditional UPDATE gets 409."""
    from unittest.mock import patch

    from db.jobs import create_job, get_job, update_job

    job = create_job("/media/race.mkv")

    real_cancel_job = __import__("db.jobs", fromlist=["cancel_job"]).cancel_job

    def losing_cancel(job_id):
        # Simulate the worker grabbing the job first: the conditional UPDATE
        # then matches zero rows because the status is no longer "queued".
        update_job(job_id, "running")
        return real_cancel_job(job_id)

    with (
        patch("db.jobs.cancel_job", side_effect=losing_cancel),
        app_ctx.test_client() as client,
    ):
        resp = client.delete(f"/api/v1/jobs/{job['id']}")

    assert resp.status_code == 409
    assert get_job(job["id"])["status"] == "running"


# ---------------------------------------------------------------------------
# POST /api/v1/jobs/clear-queued — bulk cancel
# ---------------------------------------------------------------------------


def test_clear_queued_cancels_only_queued(app_ctx, temp_db):
    """clear-queued cancels queued jobs and leaves the running one alone."""
    from db.jobs import create_job, get_job, update_job

    q1 = create_job("/media/q1.mkv")
    q2 = create_job("/media/q2.mkv")
    running = create_job("/media/running.mkv")
    update_job(running["id"], "running")

    with app_ctx.test_client() as client:
        resp = client.post("/api/v1/jobs/clear-queued")

    assert resp.status_code == 200
    assert resp.get_json()["cancelled"] == 2
    assert get_job(q1["id"])["status"] == "cancelled"
    assert get_job(q2["id"])["status"] == "cancelled"
    assert get_job(running["id"])["status"] == "running"


def test_clear_queued_idempotent(app_ctx, temp_db):
    """A second clear-queued call finds nothing left and reports 0."""
    from db.jobs import create_job

    create_job("/media/q1.mkv")

    with app_ctx.test_client() as client:
        first = client.post("/api/v1/jobs/clear-queued")
        second = client.post("/api/v1/jobs/clear-queued")

    assert first.status_code == 200
    assert first.get_json()["cancelled"] == 1
    assert second.status_code == 200
    assert second.get_json()["cancelled"] == 0
