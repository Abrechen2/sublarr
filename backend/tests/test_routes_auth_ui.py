"""Tests for /api/v1/auth/* endpoints."""

import pytest

import ui_auth


@pytest.fixture
def app(monkeypatch):
    from flask import Flask

    from routes.auth_ui import auth_ui_bp

    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: None)
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: None)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    app.register_blueprint(auth_ui_bp)
    return app


def test_status_unconfigured(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: False)
    with app.test_client() as client:
        r = client.get("/api/v1/auth/status")
        assert r.status_code == 200
        data = r.get_json()
        assert data["configured"] is False
        assert data["enabled"] is False
        assert data["authenticated"] is False


def test_setup_set_password(app, monkeypatch):
    saved = {}
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: saved.update({k: v}))
    with app.test_client() as client:
        r = client.post(
            "/api/v1/auth/setup", json={"action": "set_password", "password": "hunter2-correct"}
        )
        assert r.status_code == 200
        assert "ui_password_hash" in saved
        assert saved["ui_auth_enabled"] == "true"


def test_setup_disable(app, monkeypatch):
    saved = {}
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: saved.update({k: v}))
    with app.test_client() as client:
        r = client.post("/api/v1/auth/setup", json={"action": "disable"})
        assert r.status_code == 200
        assert saved.get("ui_auth_enabled") == "false"


def test_setup_rejected_when_already_configured(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    with app.test_client() as client:
        r = client.post("/api/v1/auth/setup", json={"action": "disable"})
        assert r.status_code == 409


def test_setup_rejects_short_password(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    with app.test_client() as client:
        r = client.post("/api/v1/auth/setup", json={"action": "set_password", "password": "ab"})
        assert r.status_code == 400


def test_login_correct_password(app, monkeypatch):
    pw_hash = ui_auth.hash_password("correct")
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: True)
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: pw_hash if k == "ui_password_hash" else "true"
    )
    with app.test_client() as client:
        r = client.post("/api/v1/auth/login", json={"password": "correct"})
        assert r.status_code == 200


def test_login_wrong_password(app, monkeypatch):
    pw_hash = ui_auth.hash_password("correct")
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: True)
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: pw_hash if k == "ui_password_hash" else "true"
    )
    with app.test_client() as client:
        r = client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert r.status_code == 401


def test_login_when_auth_disabled_succeeds(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: False)
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    with app.test_client() as client:
        r = client.post("/api/v1/auth/login", json={"password": ""})
        assert r.status_code == 200


def test_logout_clears_session(app, monkeypatch):
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 200
        with client.session_transaction() as sess:
            assert not sess.get("ui_authenticated")


def test_change_password_correct(app, monkeypatch):
    pw_hash = ui_auth.hash_password("old")
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: pw_hash if k == "ui_password_hash" else "true"
    )
    saved = {}
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: saved.update({k: v}))
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        r = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "old", "new_password": "newpass1-secure"},
        )
        assert r.status_code == 200
        assert "ui_password_hash" in saved


def test_change_password_wrong_current(app, monkeypatch):
    pw_hash = ui_auth.hash_password("old")
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: pw_hash if k == "ui_password_hash" else "true"
    )
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        r = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "wrong", "new_password": "newpass1"},
        )
        assert r.status_code == 401


def test_toggle_disable_requires_session(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: None)
    monkeypatch.setattr(ui_auth, "_has_valid_api_key", lambda: False)
    with app.test_client() as client:
        r = client.post("/api/v1/auth/toggle", json={"enabled": False})
        assert r.status_code == 401


def test_toggle_disable_with_session(app, monkeypatch):
    saved = {}
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: saved.update({k: v}))
    monkeypatch.setattr(ui_auth, "_has_valid_api_key", lambda: False)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        r = client.post("/api/v1/auth/toggle", json={"enabled": False})
        assert r.status_code == 200
        assert saved.get("ui_auth_enabled") == "false"
