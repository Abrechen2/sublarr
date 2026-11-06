"""A UI session must never be a cheaper credential than the API key.

Code check 2026-11-05 (Forgejo #70, #72, #73): with UI auth disabled,
``POST /auth/login {}`` handed any caller a session that opened every API
route and ``/auth/bootstrap``, although an API key was set. Sessions could
also not be ended server-side, and anyone could run the first setup.
"""

import pytest
from flask import Flask, jsonify

import auth
import config
import ui_auth

API_KEY = "k" * 64
LAN = {"REMOTE_ADDR": "192.168.1.10"}
REMOTE = {"REMOTE_ADDR": "8.8.4.4"}


class _Settings:
    api_key = API_KEY
    session_timeout_minutes = 0


@pytest.fixture
def store(monkeypatch):
    entries: dict[str, str] = {}
    monkeypatch.setattr(ui_auth, "_get_config_entry", entries.get)

    def save(key, value):
        entries[key] = value
        ui_auth._invalidate_cache()

    monkeypatch.setattr(ui_auth, "_save_config_entry", save)
    monkeypatch.setattr(config, "get_settings", lambda: _Settings())
    monkeypatch.setattr(auth, "get_settings", lambda: _Settings())
    ui_auth._invalidate_cache()
    ui_auth._setup_token = None
    yield entries
    ui_auth._invalidate_cache()


@pytest.fixture
def app(store):
    from auth import init_auth
    from routes.auth_ui import auth_ui_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    init_auth(app)
    app.register_blueprint(auth_ui_bp)

    @app.get("/api/v1/config")
    def protected():
        return jsonify({})

    return app


def _disabled(store):
    store["ui_password_hash"] = "disabled"
    store["ui_auth_enabled"] = "false"


def _enabled(store, password="correct-horse"):
    store["ui_password_hash"] = ui_auth.hash_password(password)
    store["ui_auth_enabled"] = "true"


# -- #70: the free session -------------------------------------------------


def test_free_session_from_outside_the_lan_is_refused(app, store):
    _disabled(store)
    with app.test_client() as c:
        assert c.post("/api/v1/auth/login", json={}, environ_base=REMOTE).status_code == 403
        assert c.get("/api/v1/config", environ_base=REMOTE).status_code == 401
        assert c.get("/api/v1/auth/bootstrap", environ_base=REMOTE).status_code == 403


def test_free_session_through_a_reverse_proxy_is_refused(app, store):
    _disabled(store)
    proxied = {"X-Forwarded-For": "8.8.4.4"}
    with app.test_client() as c:
        r = c.post("/api/v1/auth/login", json={}, headers=proxied, environ_base=LAN)
        assert r.status_code == 403
        assert c.get("/api/v1/config", headers=proxied, environ_base=LAN).status_code == 401


def test_free_session_before_setup_is_refused(app, store):
    with app.test_client() as c:
        assert c.post("/api/v1/auth/login", json={}, environ_base=LAN).status_code == 409
        assert c.get("/api/v1/config", environ_base=LAN).status_code == 401


def test_free_session_works_in_the_lan_when_auth_is_disabled(app, store):
    _disabled(store)
    with app.test_client() as c:
        assert c.post("/api/v1/auth/login", json={}, environ_base=LAN).status_code == 200
        assert c.get("/api/v1/config", environ_base=LAN).status_code == 200
        assert c.get("/api/v1/auth/bootstrap", environ_base=LAN).get_json()["api_key"] == API_KEY


def test_free_session_does_not_travel_out_of_the_lan(app, store):
    _disabled(store)
    with app.test_client() as c:
        c.post("/api/v1/auth/login", json={}, environ_base=LAN)
        assert c.get("/api/v1/config", environ_base=REMOTE).status_code == 401


def test_free_session_ends_when_auth_is_enabled(app, store):
    _disabled(store)
    with app.test_client() as c:
        c.post("/api/v1/auth/login", json={}, environ_base=LAN)
        r = c.post("/api/v1/auth/toggle", json={"enabled": True}, environ_base=LAN)
        assert r.status_code == 200
        assert c.get("/api/v1/config", environ_base=LAN).status_code == 401


def test_a_forged_session_without_generation_is_refused(app, store):
    _enabled(store)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["ui_authenticated"] = True
        assert c.get("/api/v1/config", environ_base=REMOTE).status_code == 401


# -- #73: ending sessions --------------------------------------------------


def _login(c, password="correct-horse"):
    r = c.post("/api/v1/auth/login", json={"password": password}, environ_base=REMOTE)
    assert r.status_code == 200


def test_password_session_opens_the_api(app, store):
    _enabled(store)
    with app.test_client() as c:
        _login(c)
        assert c.get("/api/v1/config", environ_base=REMOTE).status_code == 200


def test_a_copied_cookie_dies_with_logout(app, store):
    _enabled(store)
    with app.test_client() as c:
        _login(c)
        with c.session_transaction() as s:
            stolen = dict(s)
        c.post("/api/v1/auth/logout", environ_base=REMOTE)
    with app.test_client() as thief:
        with thief.session_transaction() as s:
            s.update(stolen)
        assert thief.get("/api/v1/config", environ_base=REMOTE).status_code == 401


def test_password_change_ends_other_sessions(app, store):
    _enabled(store)
    # Plain clients: two nested ``with`` clients unwind each other's contexts.
    other, c = app.test_client(), app.test_client()
    _login(other)
    _login(c)
    r = c.post(
        "/api/v1/auth/change-password",
        json={"current_password": "correct-horse", "new_password": "battery-staple"},
        environ_base=REMOTE,
    )
    assert r.status_code == 200
    assert other.get("/api/v1/config", environ_base=REMOTE).status_code == 401
    assert c.get("/api/v1/config", environ_base=REMOTE).status_code == 200


def test_revocations_expire_and_stay_bounded(store, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ui_auth.time, "time", lambda: now[0])
    for i in range(ui_auth._MAX_REVOKED_SESSIONS + 50):
        ui_auth._revoke(f"sid-{i}", ttl_seconds=60)
    assert len(ui_auth._revoked_sessions()) == ui_auth._MAX_REVOKED_SESSIONS
    now[0] += 61
    ui_auth._revoke("late", ttl_seconds=60)
    assert set(ui_auth._revoked_sessions()) == {"late"}


# -- #72: first setup ------------------------------------------------------


def test_setup_from_outside_the_lan_needs_the_token(app, store):
    with app.test_client() as c:
        r = c.post("/api/v1/auth/setup", json={"action": "disable"}, environ_base=REMOTE)
        assert r.status_code == 403
        assert r.get_json()["setup_token_required"] is True
        assert "ui_auth_enabled" not in store
        r = c.post(
            "/api/v1/auth/setup",
            json={"action": "disable", "setup_token": ui_auth.setup_token()},
            environ_base=REMOTE,
        )
        assert r.status_code == 200


def test_setup_with_a_wrong_token_is_refused(app, store):
    ui_auth.setup_token()
    with app.test_client() as c:
        r = c.post(
            "/api/v1/auth/setup",
            json={"action": "disable", "setup_token": "nope"},
            environ_base=REMOTE,
        )
        assert r.status_code == 403


def test_setup_from_the_lan_needs_no_token(app, store):
    with app.test_client() as c:
        r = c.post(
            "/api/v1/auth/setup",
            json={"action": "set_password", "password": "correct-horse"},
            environ_base=LAN,
        )
        assert r.status_code == 200
        assert c.get("/api/v1/config", environ_base=LAN).status_code == 200


def test_the_api_key_alone_cannot_claim_the_setup(app, store):
    """Sonarr and friends may hold the API key; it must not set the password."""
    with app.test_client() as c:
        r = c.post(
            "/api/v1/auth/setup",
            json={"action": "disable"},
            headers={"X-Api-Key": API_KEY},
            environ_base=REMOTE,
        )
        assert r.status_code == 403
        assert "ui_auth_enabled" not in store


# -- the API key cannot switch sign-in off --------------------------------


def test_the_api_key_alone_cannot_turn_sign_in_off(app, store):
    _enabled(store)
    with app.test_client() as c:
        r = c.post(
            "/api/v1/auth/toggle",
            json={"enabled": False},
            headers={"X-Api-Key": API_KEY},
            environ_base=LAN,
        )
        assert r.status_code == 403
        assert r.get_json()["password_required"] is True
        assert store["ui_auth_enabled"] == "true"


def test_the_api_key_with_the_password_can_switch_sign_in(app, store):
    _enabled(store)
    with app.test_client() as c:
        r = c.post(
            "/api/v1/auth/toggle",
            json={"enabled": False, "password": "correct-horse"},
            headers={"X-Api-Key": API_KEY},
            environ_base=LAN,
        )
        assert r.status_code == 200
        assert store["ui_auth_enabled"] == "false"


# -- locality --------------------------------------------------------------


@pytest.mark.parametrize(
    ("addr", "headers", "local"),
    [
        ("127.0.0.1", {}, True),
        ("::1", {}, True),
        ("10.0.0.4", {}, True),
        ("172.19.0.1", {}, True),
        ("::ffff:192.168.178.20", {}, True),
        ("100.101.102.103", {}, True),  # Tailscale / CGNAT range
        ("fd00::1", {}, True),
        ("8.8.4.4", {}, False),
        ("2a00:1450::1", {}, False),
        ("", {}, False),
        ("192.168.1.2", {"Forwarded": "for=8.8.4.4"}, False),
        ("192.168.1.2", {"X-Real-IP": "8.8.4.4"}, False),
    ],
)
def test_request_is_local_network(addr, headers, local):
    app = Flask(__name__)
    with app.test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": addr}):
        assert ui_auth.request_is_local_network() is local
