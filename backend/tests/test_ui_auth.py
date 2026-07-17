"""Tests for ui_auth.py — UI session authentication."""

from datetime import timedelta

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


@pytest.fixture(autouse=True)
def reset_auth_cache():
    """Reset the auth flag cache before each test to ensure test isolation."""
    ui_auth._auth_enabled_cache = None
    yield
    ui_auth._auth_enabled_cache = None


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
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: "some_hash" if k == "ui_password_hash" else None
    )
    assert is_ui_auth_configured() is True


def test_is_ui_auth_enabled_false_when_disabled(monkeypatch):
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: "false" if k == "ui_auth_enabled" else None
    )
    assert is_ui_auth_enabled() is False


def test_is_ui_auth_enabled_true_when_enabled(monkeypatch):
    monkeypatch.setattr(
        ui_auth, "_get_config_entry", lambda k: "true" if k == "ui_auth_enabled" else "hash"
    )
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


def test_session_lifetime_uses_configured_timeout(monkeypatch):
    """PERMANENT_SESSION_LIFETIME must respect session_timeout_minutes when set.

    ``session_timeout_minutes`` is a UI field since v0.88.0-beta — set via
    DB override (the path the live UI takes), not via env.
    """
    from config import reload_settings

    reload_settings(overrides={"session_timeout_minutes": "60"})

    app = Flask(__name__)
    app.config["TESTING"] = True

    init_ui_auth(app)

    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(minutes=60)

    # Cleanup
    reload_settings()


def test_session_lifetime_defaults_to_8h_when_not_configured(monkeypatch):
    """PERMANENT_SESSION_LIFETIME must default to 8 hours when session_timeout_minutes is 0."""
    # Ensure timeout is 0
    import os

    os.environ.pop("SUBLARR_SESSION_TIMEOUT_MINUTES", None)
    from config import reload_settings

    reload_settings()

    app = Flask(__name__)
    app.config["TESTING"] = True

    init_ui_auth(app)

    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=8)


def test_is_ui_auth_enabled_cached(monkeypatch):
    ui_auth._auth_enabled_cache = None
    calls = []

    def fake_get(key):
        calls.append(key)
        return "true"

    monkeypatch.setattr(ui_auth, "_get_config_entry", fake_get)
    assert ui_auth.is_ui_auth_enabled() is True
    assert ui_auth.is_ui_auth_enabled() is True
    assert calls.count("ui_auth_enabled") == 1, "flag must be cached between requests"


def test_saving_flag_invalidates_cache(monkeypatch):
    import db.config

    monkeypatch.setattr(db.config, "save_config_entry", lambda key, value: None)
    ui_auth._auth_enabled_cache = (float("inf"), True)
    ui_auth._save_config_entry("ui_auth_enabled", "false")
    assert ui_auth._auth_enabled_cache is None, "write must drop the cached flag"


def test_saving_other_key_keeps_cache(monkeypatch):
    import db.config

    monkeypatch.setattr(db.config, "save_config_entry", lambda key, value: None)
    ui_auth._auth_enabled_cache = (float("inf"), True)
    ui_auth._save_config_entry("ui_session_secret", "abc")
    assert ui_auth._auth_enabled_cache is not None


class _RaceTuple(tuple):
    """A cache tuple that simulates another thread invalidating the module
    global (``ui_auth._auth_enabled_cache = None``) the instant its first
    element is read.

    ``is_ui_auth_enabled`` must capture ``_auth_enabled_cache`` into a local
    exactly once before touching it. If it instead re-reads the global for
    the ``[0]``/``[1]`` accesses (the pre-fix bug), the second access below
    hits ``None[1]`` and raises ``TypeError: 'NoneType' object is not
    subscriptable``.
    """

    def __getitem__(self, index):
        if index == 0:
            ui_auth._auth_enabled_cache = None
        return tuple.__getitem__(self, index)


def test_is_ui_auth_enabled_survives_concurrent_cache_invalidation(monkeypatch):
    """Regression test for the race between is_ui_auth_enabled's cache reads
    and _save_config_entry's cache invalidation (HIGH finding, Task 7).

    Installs a _RaceTuple as the cache value so that reading its timestamp
    ([0]) flips the module global to None mid-function, exactly as a
    concurrent _save_config_entry call would. Because is_ui_auth_enabled
    must capture the global into a local once, this must not raise and must
    still return the cached value.
    """
    ui_auth._auth_enabled_cache = _RaceTuple((float("inf"), True))
    assert ui_auth.is_ui_auth_enabled() is True
