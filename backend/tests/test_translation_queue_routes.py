"""API tests for /api/v1/translation/queue."""

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("SUBLARR_API_KEY", "")
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "disabled")
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def reset_queue():
    from translation.queue_state import reset_for_tests

    reset_for_tests()


def test_empty_queue(client, reset_queue):
    resp = client.get("/api/v1/translation/queue")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"active": [], "recent": []}


def test_active_job_visible(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=428,
    )
    get_queue_state().update_progress("j1", done=142)

    resp = client.get("/api/v1/translation/queue")
    data = resp.get_json()
    assert len(data["active"]) == 1
    job = data["active"][0]
    assert job["job_id"] == "j1"
    assert job["progress"]["done"] == 142
    assert job["progress"]["total"] == 428


def test_cancel_job(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=10,
    )
    resp = client.post("/api/v1/translation/queue/j1/cancel")
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "cancelling"
    assert get_queue_state().is_cancelled("j1")


def test_cancel_unknown_404(client, reset_queue):
    resp = client.post("/api/v1/translation/queue/nope/cancel")
    assert resp.status_code == 404


def test_cancel_already_cancelled_409(client, reset_queue):
    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=10,
    )
    client.post("/api/v1/translation/queue/j1/cancel")
    resp = client.post("/api/v1/translation/queue/j1/cancel")
    assert resp.status_code == 409


def test_audit_log_written(client, reset_queue, caplog):
    import logging

    from translation.queue_state import get_queue_state

    get_queue_state().register_job(
        job_id="j1",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="claude",
        total_lines=10,
    )
    with caplog.at_level(logging.INFO, logger="routes.translation.queue"):
        client.post("/api/v1/translation/queue/j1/cancel")
    assert any("translation_admin_action" in r.message for r in caplog.records)
