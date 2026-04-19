"""Route tests for /api/v1/scheduler/*."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    # Disable API-key auth so the test_client can hit /api/v1/scheduler/* directly.
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app
    scheduler = app.extensions.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(timeout_s=2)


@pytest.fixture
def client(app):
    return app.test_client()


def _ensure_bootstrap(app):
    """Ensure scheduler is bootstrapped (tests may run before startup wiring)."""
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)


def test_jobs_list_returns_registered_jobs(app, client):
    _ensure_bootstrap(app)
    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "jobs" in data
    ids = [j["id"] for j in data["jobs"]]
    assert "scheduler_history_cleanup" in ids


def test_jobs_list_503_when_scheduler_disabled(app, client):
    with app.app_context():
        app.extensions["scheduler"] = None
    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 503
    assert resp.get_json()["error_type"] == "SchedulerDownError"


def test_single_job_detail(app, client):
    _ensure_bootstrap(app)
    resp = client.get("/api/v1/scheduler/jobs/scheduler_history_cleanup")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == "scheduler_history_cleanup"
    assert "trigger" in data
    assert "paused" in data
    assert "trigger_is_default" in data


def test_single_job_404(app, client):
    _ensure_bootstrap(app)
    resp = client.get("/api/v1/scheduler/jobs/nope")
    assert resp.status_code == 404


def test_runs_list_paginates(app, client):
    _ensure_bootstrap(app)
    s = app.extensions["scheduler"]
    import time

    for _ in range(3):
        s.run_now("scheduler_history_cleanup")
        time.sleep(1)
    resp = client.get("/api/v1/scheduler/jobs/scheduler_history_cleanup/runs?limit=2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["limit"] == 2
    assert len(data["runs"]) <= 2
    assert "total" in data


def test_runs_status_filter(app, client):
    _ensure_bootstrap(app)
    resp = client.get("/api/v1/scheduler/jobs/scheduler_history_cleanup/runs?status=ok")
    assert resp.status_code == 200
    data = resp.get_json()
    for r in data["runs"]:
        assert r["status"] == "ok"


def test_stats_7d_present_on_list(app, client):
    _ensure_bootstrap(app)
    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    for j in resp.get_json()["jobs"]:
        assert "stats_7d" in j
        assert set(j["stats_7d"].keys()) >= {"ok", "error", "timeout", "missed"}
