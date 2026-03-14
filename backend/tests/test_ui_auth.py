"""Tests for ui_auth.py — UI session authentication."""

import pytest
from flask import Flask, session

import ui_auth
from ui_auth import (
    hash_password,
    init_ui_auth,
    is_ui_auth_configured,
    is_ui_auth_enabled,
    verify_password,
)


def test_hash_password_returns_string():
    h = hash_password("secret123")
    assert isinstance(h, str)
    assert h.startswith("$2b$")


def test_verify_password_correct():
    h = hash_password("correct")
    assert verify_password("correct", h) is True


def test_verify_password_wrong():
    h = hash_password("correct")
    assert verify_password("wrong", h) is False


def test_verify_password_empty():
    h = hash_password("correct")
    assert verify_password("", h) is False


def test_is_ui_auth_configured_false_when_no_entry(monkeypatch):
    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: None)
    assert is_ui_auth_configured() is False


def test_is_ui_auth_configured_true_when_entry_exists(monkeypatch):
    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: "some_hash" if k == "ui_password_hash" else None)
    assert is_ui_auth_configured() is True


def test_is_ui_auth_enabled_false_when_disabled(monkeypatch):
    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: "false" if k == "ui_auth_enabled" else None)
    assert is_ui_auth_enabled() is False


def test_is_ui_auth_enabled_true_when_enabled(monkeypatch):
    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: "true" if k == "ui_auth_enabled" else "hash")
    assert is_ui_auth_enabled() is True


def _make_app_with_auth(monkeypatch, *, configured: bool, enabled: bool):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: configured)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: enabled)

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/api/v1/health")
    def health():
        return {"status": "ok"}

    @app.route("/api/v1/auth/status")
    def auth_status():
        return {"ok": True}

    @app.route("/api/v1/protected")
    def protected():
        return {"data": "secret"}

    init_ui_auth(app)
    return app


def test_hook_allows_health_when_auth_enabled(monkeypatch):
    app = _make_app_with_auth(monkeypatch, configured=True, enabled=True)
    with app.test_client() as client:
        r = client.get("/api/v1/health")
        assert r.status_code == 200


def test_hook_allows_auth_endpoints_unauthenticated(monkeypatch):
    app = _make_app_with_auth(monkeypatch, configured=True, enabled=True)
    with app.test_client() as client:
        r = client.get("/api/v1/auth/status")
        assert r.status_code == 200


def test_hook_blocks_protected_when_no_session(monkeypatch):
    app = _make_app_with_auth(monkeypatch, configured=True, enabled=True)
    with app.test_client() as client:
        r = client.get("/api/v1/protected")
        assert r.status_code == 401


def test_hook_allows_protected_with_valid_session(monkeypatch):
    app = _make_app_with_auth(monkeypatch, configured=True, enabled=True)
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        r = client.get("/api/v1/protected")
        assert r.status_code == 200


def test_hook_allows_all_when_auth_disabled(monkeypatch):
    app = _make_app_with_auth(monkeypatch, configured=True, enabled=False)
    with app.test_client() as client:
        r = client.get("/api/v1/protected")
        assert r.status_code == 200


def test_hook_allows_api_key_without_session(monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: True)

    import os
    os.environ["SUBLARR_API_KEY"] = "test-key"
    from config import reload_settings
    reload_settings()

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/api/v1/protected")
    def protected():
        return {"data": "secret"}

    init_ui_auth(app)
    with app.test_client() as client:
        r = client.get("/api/v1/protected", headers={"X-Api-Key": "test-key"})
        assert r.status_code == 200

    os.environ.pop("SUBLARR_API_KEY", None)
    reload_settings()
