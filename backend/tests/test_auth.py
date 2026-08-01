"""Tests for auth.py — API key authentication."""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from auth import init_auth, require_api_key
from config import reload_settings


def test_no_auth_when_key_empty():
    """Test that auth is disabled when API key is empty."""
    if "SUBLARR_API_KEY" in os.environ:
        del os.environ["SUBLARR_API_KEY"]

    settings = reload_settings()
    assert settings.api_key == ""

    app = Flask(__name__)
    init_auth(app)
    # Should not raise any errors


def test_auth_required_when_key_set():
    """Test that auth is enabled when API key is set."""
    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    settings = reload_settings()
    assert settings.api_key == "test-key-123"

    app = Flask(__name__)
    init_auth(app)

    # Cleanup
    del os.environ["SUBLARR_API_KEY"]
    reload_settings()


def test_require_api_key_decorator():
    """When API key is set, require it on protected endpoints."""
    app = Flask(__name__)

    @app.route("/test")
    @require_api_key
    def test_route():
        return {"status": "ok"}

    # Case 1: no API key configured — request should succeed
    os.environ.pop("SUBLARR_API_KEY", None)
    reload_settings()
    with app.test_client() as client:
        response = client.get("/test")
        assert response.status_code == 200

    # Case 2: API key configured — request without key should fail
    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    reload_settings()
    try:
        with app.test_client() as client:
            response = client.get("/test")
            assert response.status_code == 401

            response_with_key = client.get("/test", headers={"X-Api-Key": "test-key-123"})
            assert response_with_key.status_code == 200
    finally:
        os.environ.pop("SUBLARR_API_KEY", None)
        reload_settings()


def test_ip_allowlist_blocks_unlisted_ip():
    """Requests from IPs outside allowed_ip_ranges must receive 403."""
    app = Flask(__name__)

    @app.route("/api/v1/health")
    def health():
        return {"status": "ok"}

    init_auth(app)

    settings_mock = MagicMock()
    settings_mock.allowed_ip_ranges = "10.0.0.0/8"
    settings_mock.api_key = ""

    with patch("auth.get_settings", return_value=settings_mock), app.test_client() as client:
        # Flask test client sends from 127.0.0.1 by default
        resp = client.get("/api/v1/health")
        assert resp.status_code == 403


def test_ip_allowlist_allows_listed_ip():
    """Requests from IPs inside allowed_ip_ranges must pass through."""
    app = Flask(__name__)

    @app.route("/api/v1/health")
    def health():
        return {"status": "ok"}

    init_auth(app)

    settings_mock = MagicMock()
    settings_mock.allowed_ip_ranges = "127.0.0.1/32"
    settings_mock.api_key = ""

    with patch("auth.get_settings", return_value=settings_mock), app.test_client() as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code != 403


def test_ip_allowlist_empty_allows_all():
    """Empty allowed_ip_ranges allows all IPs."""
    app = Flask(__name__)

    @app.route("/api/v1/health")
    def health():
        return {"status": "ok"}

    init_auth(app)

    settings_mock = MagicMock()
    settings_mock.allowed_ip_ranges = ""
    settings_mock.api_key = ""

    with patch("auth.get_settings", return_value=settings_mock), app.test_client() as client:
        resp = client.get("/api/v1/health")
        assert resp.status_code != 403


def _protected_app():
    """Flask app with init_auth and a protected /api/v1 route + session support."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/api/v1/protected")
    def protected():
        return {"status": "ok"}

    init_auth(app)
    return app


def _settings(api_key="server-key", allowed_ip_ranges=""):
    settings_mock = MagicMock()
    settings_mock.api_key = api_key
    settings_mock.allowed_ip_ranges = allowed_ip_ranges
    settings_mock.max_login_attempts = 20
    return settings_mock


def test_ui_session_satisfies_api_key_gate():
    """A logged-in UI session must pass the API gate without an X-Api-Key.

    Regression test for the 1.6.0 login loop: the SPA logs in (session cookie
    set) but has no key in localStorage yet; every API call got 401 and the
    frontend's 401 interceptor bounced back to /login forever.
    """
    app = _protected_app()
    with patch("auth.get_settings", return_value=_settings()), app.test_client() as client:
        with client.session_transaction() as sess:
            sess["ui_authenticated"] = True
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 200


def test_no_session_no_key_still_401():
    """Without a session and without a key the gate must still reject."""
    app = _protected_app()
    with patch("auth.get_settings", return_value=_settings()), app.test_client() as client:
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 401


def test_unauthenticated_session_cookie_does_not_bypass():
    """A session cookie without the ui_authenticated flag must not pass."""
    app = _protected_app()
    with patch("auth.get_settings", return_value=_settings()), app.test_client() as client:
        with client.session_transaction() as sess:
            sess["some_other_flag"] = True
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 401


def test_valid_proxy_auth_satisfies_api_key_gate():
    """A trusted-proxy-authenticated request must pass without an X-Api-Key."""
    app = _protected_app()
    with (
        patch("auth.get_settings", return_value=_settings()),
        patch("proxy_auth.request_has_valid_proxy_auth", return_value=True),
        app.test_client() as client,
    ):
        resp = client.get("/api/v1/protected")
        assert resp.status_code == 200


def test_require_api_key_decorator_accepts_ui_session():
    """The decorator must honour the same session-OR-key contract as the hook."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/decorated")
    @require_api_key
    def decorated_route():
        return {"status": "ok"}

    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    reload_settings()
    try:
        with app.test_client() as client:
            resp = client.get("/decorated")
            assert resp.status_code == 401

            with client.session_transaction() as sess:
                sess["ui_authenticated"] = True
            resp = client.get("/decorated")
            assert resp.status_code == 200
    finally:
        os.environ.pop("SUBLARR_API_KEY", None)
        reload_settings()


def test_require_api_key_decorator_accepts_proxy_auth():
    """Trusted-proxy SSO requests must pass decorated routes without a key."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"

    @app.route("/decorated")
    @require_api_key
    def decorated_route():
        return {"status": "ok"}

    os.environ["SUBLARR_API_KEY"] = "test-key-123"
    reload_settings()
    try:
        with (
            patch("proxy_auth.request_has_valid_proxy_auth", return_value=True),
            app.test_client() as client,
        ):
            resp = client.get("/decorated")
            assert resp.status_code == 200
    finally:
        os.environ.pop("SUBLARR_API_KEY", None)
        reload_settings()
