"""The Socket.IO handshake follows the same gate as the HTTP API (#79 follow-up).

/socket.io/ is exempt from the HTTP gate, and the connect handler only
checked anything when an API key was set: before the first setup, or with UI
auth on but no API key, anyone could connect and stream the logs.
"""

from __future__ import annotations

import pytest
from flask import Flask

import ui_auth


class _Settings:
    def __init__(self, api_key=""):
        self.api_key = api_key


@pytest.fixture
def gate(monkeypatch):
    import config

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    monkeypatch.setattr(ui_auth, "has_valid_session", lambda: False)

    def run(*, remote="8.8.8.8", configured=False, enabled=False, api_key="", provided=""):
        monkeypatch.setattr(config, "get_settings", lambda: _Settings(api_key))
        monkeypatch.setattr(ui_auth, "is_ui_auth_configured", lambda: configured)
        monkeypatch.setattr(ui_auth, "is_ui_auth_enabled", lambda: enabled)
        with app.test_request_context("/socket.io/", environ_base={"REMOTE_ADDR": remote}):
            return ui_auth.socket_connect_allowed(provided)

    return run


def test_public_client_is_refused_before_setup(gate):
    assert gate() is False


def test_lan_client_connects_before_setup(gate):
    assert gate(remote="192.168.1.10") is True


def test_ui_auth_on_without_api_key_needs_a_session(gate):
    assert gate(remote="192.168.1.10", configured=True, enabled=True) is False


def test_auth_deliberately_disabled_stays_open(gate):
    assert gate(configured=True, enabled=False) is True


def test_api_key_still_decides_when_set(gate):
    assert gate(api_key="k", provided="k") is True
    assert gate(remote="192.168.1.10", configured=True, api_key="k", provided="x") is False
