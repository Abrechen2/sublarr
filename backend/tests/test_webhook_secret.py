"""Webhooks authenticate with their own secret, not the admin API key.

Code check 2026-11-05 (Forgejo #71): Sonarr, Radarr and Jellyfin held the one
API key that also installs plugins, so whoever read their webhook settings
could run code in Sublarr. Webhooks now take ``webhook_secret``, which opens
nothing else; the API key stays accepted on webhooks until the operator turns
``webhook_legacy_auth`` off.
"""

from unittest.mock import MagicMock, patch

import pytest

API_KEY = "admin-api-key"
SECRET = "webhook-only-secret"
TEST_EVENT = {"eventType": "Test"}


def _settings(**overrides):
    values = {
        "api_key": API_KEY,
        "webhook_secret": SECRET,
        "webhook_legacy_auth": True,
        "media_path": "/media",
        "webhook_delay_minutes": 0,
        "webhook_auto_scan": False,
        "webhook_auto_search": False,
        "webhook_auto_translate": False,
    }
    values.update(overrides)
    mock = MagicMock()
    for k, v in values.items():
        setattr(mock, k, v)
    return mock


def _post(client, service, key, **overrides):
    with patch("config.get_settings", return_value=_settings(**overrides)):
        return client.post(
            f"/api/v1/webhook/{service}",
            json=TEST_EVENT,
            headers={"X-Api-Key": key} if key is not None else {},
        )


SERVICES = ["sonarr", "radarr"]


@pytest.mark.parametrize("service", SERVICES)
def test_the_webhook_secret_is_accepted(client, service):
    assert _post(client, service, SECRET).status_code == 200


@pytest.mark.parametrize("service", SERVICES)
def test_the_api_key_still_works_while_legacy_auth_is_on(client, service):
    assert _post(client, service, API_KEY).status_code == 200


@pytest.mark.parametrize("service", SERVICES)
def test_the_api_key_is_refused_once_legacy_auth_is_off(client, service):
    assert _post(client, service, API_KEY, webhook_legacy_auth=False).status_code == 401
    assert _post(client, service, SECRET, webhook_legacy_auth=False).status_code == 200


@pytest.mark.parametrize("service", SERVICES)
@pytest.mark.parametrize("key", [None, "", "wrong"])
def test_anything_else_is_refused(client, service, key):
    assert _post(client, service, key).status_code == 401


@pytest.mark.parametrize("service", SERVICES)
def test_no_credentials_configured_refuses(client, service):
    r = _post(client, service, "", api_key="", webhook_secret="")
    assert r.status_code == 401


def test_jellyfin_takes_the_webhook_secret(client):
    with patch("config.get_settings", return_value=_settings(webhook_legacy_auth=False)):
        refused = client.post("/api/v1/webhook/jellyfin", json={}, headers={"X-Api-Key": API_KEY})
    assert refused.status_code == 401


def test_the_webhook_secret_opens_no_other_route(client):
    import auth

    with patch.object(auth, "get_settings", return_value=_settings()):
        r = client.get("/api/v1/config", headers={"X-Api-Key": SECRET})
    assert r.status_code == 403  # a key that is not the API key


def test_the_secret_can_be_read_and_regenerated(client):
    first = client.get("/api/v1/system/webhook-secret").get_json()
    assert first["legacy_auth"] is True
    new = client.post("/api/v1/system/webhook-secret/regenerate").get_json()["webhook_secret"]
    assert len(new) == 64 and new != first["webhook_secret"]
    assert client.get("/api/v1/system/webhook-secret").get_json()["webhook_secret"] == new


def test_the_api_key_alone_cannot_read_or_replace_the_secret(client):
    """Whoever holds only the API key (an arr) must not manage webhook trust."""
    with patch("ui_auth.request_has_admin_presence", return_value=False):
        assert client.get("/api/v1/system/webhook-secret").status_code == 403
        assert client.post("/api/v1/system/webhook-secret/regenerate").status_code == 403


def test_the_generic_config_writer_refuses_the_webhook_secret():
    from routes.config.keys import is_writable_config_key

    assert not is_writable_config_key("webhook_secret")
