"""Tests for proxy_auth.request_has_valid_proxy_auth() and its wiring into the
UI-auth enforcement hook (check_ui_session in backend/ui_auth.py).

Uses the ``app_ctx`` fixture from conftest.py (real Flask app + real temp
SQLite DB via ``create_app(testing=True)``, yielded inside an active
``app.app_context()``).
"""

import pytest

import proxy_auth
import ui_auth
from config_singleton import reload_settings
from db.config import save_config_entry


@pytest.fixture(autouse=True)
def reset_auth_cache(app_ctx):
    """Reset the UI-auth flag cache before and after each test.

    Two independent staleness sources hit this cache in this file:

    1. ``create_app()`` (invoked by the ``app_ctx`` fixture) itself calls
       ``ui_auth.is_ui_auth_enabled()`` during startup (see app.py's
       auth-warning check) against a fresh, empty DB — caching a ``False``
       flag before any test body runs.
    2. ``test_e2e_trusted_proxy_bypasses_ui_auth_gate`` writes
       ``ui_auth_enabled`` directly via ``db.config.save_config_entry``,
       bypassing the cache invalidation in ``ui_auth._save_config_entry``.

    Depending on ``app_ctx`` here (rather than resetting unconditionally)
    ensures pytest instantiates ``app_ctx`` — and therefore runs
    ``create_app()``'s cache-poisoning call — first; this fixture's reset
    then runs immediately before the test body, after that poisoning has
    already happened, so the test always starts from a clean cache
    regardless of run order or the 30s TTL.
    """
    ui_auth._auth_enabled_cache = None
    yield
    ui_auth._auth_enabled_cache = None


def _enable(**over):
    base = {
        "proxy_auth_enabled": "true",
        "proxy_auth_trusted_ips": "10.0.0.0/8",
        "proxy_auth_header": "Remote-User",
    }
    base.update(over)
    reload_settings(base)


def test_trusted_ip_with_header_authenticates(app_ctx):
    _enable()
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"Remote-User": "alice"},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is True
    reload_settings({})


def test_untrusted_ip_is_rejected(app_ctx):
    _enable()
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"Remote-User": "alice"},
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is False
    reload_settings({})


def test_missing_or_empty_header_is_rejected(app_ctx):
    _enable()
    with app_ctx.test_request_context("/api/v1/library", environ_base={"REMOTE_ADDR": "10.1.2.3"}):
        assert proxy_auth.request_has_valid_proxy_auth() is False
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"Remote-User": "   "},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is False
    reload_settings({})


def test_disabled_never_authenticates(app_ctx):
    _enable(proxy_auth_enabled="false")
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"Remote-User": "alice"},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is False
    reload_settings({})


def test_enabled_but_no_allowlist_fails_closed(app_ctx):
    _enable(proxy_auth_trusted_ips="")
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"Remote-User": "alice"},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is False
    reload_settings({})


def test_custom_header_name(app_ctx):
    _enable(proxy_auth_header="X-Forwarded-User")
    with app_ctx.test_request_context(
        "/api/v1/library",
        headers={"X-Forwarded-User": "bob"},
        environ_base={"REMOTE_ADDR": "10.9.9.9"},
    ):
        assert proxy_auth.request_has_valid_proxy_auth() is True
    reload_settings({})


def test_e2e_trusted_proxy_bypasses_ui_auth_gate(app_ctx):
    """Real end-to-end gate test: drives an actual ``app.test_client()``
    request through the real ``check_ui_session`` hook (registered by
    ``init_ui_auth`` inside ``create_app``) with real UI auth enabled via
    the DB config_entries table.

    A trusted-proxy request carrying the identity header must pass even
    though there is no UI session and no API key configured, while the
    identical request from an untrusted peer IP must still be rejected
    with 401 — proving the bypass is IP-gated, not header-gated alone.
    """
    save_config_entry("ui_password_hash", ui_auth.hash_password("testpass123"))
    save_config_entry("ui_auth_enabled", "true")
    _enable()

    with app_ctx.test_client() as client:
        trusted = client.get(
            "/api/v1/stats",
            headers={"Remote-User": "alice"},
            environ_base={"REMOTE_ADDR": "10.1.2.3"},
        )
        assert trusted.status_code != 401

        untrusted = client.get(
            "/api/v1/stats",
            headers={"Remote-User": "alice"},
            environ_base={"REMOTE_ADDR": "203.0.113.9"},
        )
        assert untrusted.status_code == 401

    reload_settings({})
