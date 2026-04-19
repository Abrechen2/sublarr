"""Write-endpoint tests for /api/v1/scheduler/*."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
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
    from services.scheduler import bootstrap_scheduler

    with app.app_context():
        if app.extensions.get("scheduler") is None:
            bootstrap_scheduler(app)
    return app.test_client()


def test_run_now_queues_oneshot(client):
    resp = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/run-now")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "queued"
    assert data["oneshot_id"].startswith("scheduler_history_cleanup_oneshot_")


def test_run_now_404_unknown(client):
    resp = client.post("/api/v1/scheduler/jobs/nope/run-now")
    assert resp.status_code == 404


def test_pause_and_resume(client):
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/pause")
    assert r.status_code == 200
    assert r.get_json()["status"] == "paused"

    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/resume")
    assert r.status_code == 200
    assert r.get_json()["status"] == "running"


def test_pause_404_unknown(client):
    r = client.post("/api/v1/scheduler/jobs/nope/pause")
    assert r.status_code == 404


def test_patch_trigger_interval(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval", "minutes": 30}},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger"]["type"] == "interval"
    assert data["trigger"]["seconds"] == 1800
    assert data["trigger_is_default"] is False


def test_patch_trigger_cron(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "cron", "hour": 4, "minute": 30}},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger"]["type"] == "cron"
    assert data["trigger"]["hour"] == "4"


def test_patch_invalid_payload(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval"}},  # missing unit
    )
    assert r.status_code == 400


def test_patch_unreachable_cron(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "cron", "day_of_week": "xyz"}},
    )
    assert r.status_code == 400


def test_patch_404_unknown(client):
    r = client.patch(
        "/api/v1/scheduler/jobs/nope",
        json={"trigger": {"type": "interval", "minutes": 1}},
    )
    assert r.status_code == 404


def test_reset_default(client):
    client.patch(
        "/api/v1/scheduler/jobs/scheduler_history_cleanup",
        json={"trigger": {"type": "interval", "minutes": 30}},
    )
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/reset-default")
    assert r.status_code == 200
    data = r.get_json()
    assert data["trigger_is_default"] is True


def test_reset_default_404(client):
    r = client.post("/api/v1/scheduler/jobs/nope/reset-default")
    assert r.status_code == 404


def test_admin_action_audit_logged(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="routes.system.scheduler"):
        client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/pause")
    assert any("scheduler_admin_action" in r.message for r in caplog.records)


def test_503_when_scheduler_down(app, client):
    with app.app_context():
        app.extensions["scheduler"] = None
    r = client.post("/api/v1/scheduler/jobs/scheduler_history_cleanup/run-now")
    assert r.status_code == 503
