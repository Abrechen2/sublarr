"""Tests for the Socket.IO connect handler's authentication.

The connect gate must honour the same contract as the HTTP API gate:
a valid API key OR an authenticated UI session. The handshake is an
ordinary HTTP request carrying the Flask session cookie, so a browser
that logged in via /auth/login but holds no key in localStorage must
still get its WebSocket connection (log streaming, live updates).

Uses ``create_app(testing=True)`` against the temp DB from conftest.
conftest's temp_db fixture disables API-key auth via ``SUBLARR_API_KEY=""``,
so this file's fixture sets an explicit key to activate the gate.
"""

import os

import pytest

from app import create_app
from config import get_settings, reload_settings
from extensions import socketio


@pytest.fixture
def ws_app(temp_db):
    os.environ["SUBLARR_API_KEY"] = "ws-test-key"
    reload_settings()
    app = create_app(testing=True)
    app.config["TESTING"] = True
    try:
        yield app
    finally:
        os.environ["SUBLARR_API_KEY"] = ""
        reload_settings()


def test_ws_rejected_without_key_or_session(ws_app):
    client = socketio.test_client(ws_app, auth={})
    assert not client.is_connected()


def test_ws_accepts_valid_api_key(ws_app):
    api_key = get_settings().api_key
    assert api_key, "testing app should have an auto-generated api_key"
    client = socketio.test_client(ws_app, auth={"apikey": api_key})
    assert client.is_connected()
    client.disconnect()


def test_ws_accepts_ui_session_without_key(ws_app):
    flask_client = ws_app.test_client()
    with flask_client.session_transaction() as sess:
        sess["ui_authenticated"] = True
    client = socketio.test_client(ws_app, auth={}, flask_test_client=flask_client)
    assert client.is_connected()
    client.disconnect()


def test_ws_unauthenticated_session_cookie_does_not_bypass(ws_app):
    flask_client = ws_app.test_client()
    with flask_client.session_transaction() as sess:
        sess["some_other_flag"] = True
    client = socketio.test_client(ws_app, auth={}, flask_test_client=flask_client)
    assert not client.is_connected()
