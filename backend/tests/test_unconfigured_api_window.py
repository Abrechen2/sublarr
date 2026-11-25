"""Before the first setup, the API answers only the local network (#79).

While UI auth was unconfigured and no API key set, check_ui_session let every
/api request through: logs, config and library were readable by anyone who
reached the port before the owner finished the setup. Now a request from
outside the local network gets 403 until the setup is done, except for
/api/v1/auth/* (the setup itself, with the console token) and /health.
"""

from __future__ import annotations

import pytest
from flask import Flask, jsonify

import ui_auth


class _Settings:
    api_key = ""


@pytest.fixture
def app(monkeypatch):
    import config

    monkeypatch.setattr(ui_auth, "_get_config_entry", lambda k: None)
    monkeypatch.setattr(ui_auth, "_save_config_entry", lambda k, v: None)
    monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: False)
    monkeypatch.setattr(config, "get_settings", lambda: _Settings())
    app = Flask(__name__)
    app.config["TESTING"] = True
    ui_auth.init_ui_auth(app)

    @app.get("/api/v1/logs")
    def logs():
        return jsonify(["secret log line"])

    @app.get("/api/v1/auth/status")
    def status():
        return jsonify({"configured": False})

    @app.get("/api/v1/health")
    def health():
        return jsonify({"status": "healthy"})

    return app


PUBLIC = {"REMOTE_ADDR": "8.8.8.8"}  # TEST-NET ranges count as private in ipaddress
LAN = {"REMOTE_ADDR": "192.168.1.10"}


def test_public_client_cannot_read_the_api_before_setup(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    rv = app.test_client().get("/api/v1/logs", environ_base=PUBLIC)
    assert rv.status_code == 403
    assert rv.get_json()["setup_required"] is True


def test_reverse_proxied_request_counts_as_remote(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    rv = app.test_client().get(
        "/api/v1/logs", environ_base=LAN, headers={"X-Forwarded-For": "203.0.113.7"}
    )
    assert rv.status_code == 403


def test_lan_client_can_still_use_the_api_before_setup(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    assert app.test_client().get("/api/v1/logs", environ_base=LAN).status_code == 200


@pytest.mark.parametrize("path", ["/api/v1/auth/status", "/api/v1/health"])
def test_setup_and_health_stay_reachable(app, monkeypatch, path):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: False)
    assert app.test_client().get(path, environ_base=PUBLIC).status_code == 200


def test_auth_deliberately_disabled_after_setup_stays_open(app, monkeypatch):
    monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: True)
    assert app.test_client().get("/api/v1/logs", environ_base=PUBLIC).status_code == 200
