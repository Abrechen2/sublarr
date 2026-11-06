"""Plugin install takes only indexed plugins and a signed-in person.

Code check 2026-11-05 (Forgejo #71, #77 N-3): the API key — which Sonarr,
Radarr and Jellyfin hold for their webhooks — could install a plugin from any
HTTPS URL with a hash the caller chose, which is code execution. Install now
takes the URL and hash from the plugin index, refuses the API key alone, and
plugin names are checked before they reach the file system.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from extensions import db as sa_db
from tests.ui_session_helpers import grant_ui_session

API_KEY = "m" * 64
INDEXED = {
    "name": "good-plugin",
    "display_name": "Good",
    "version": "1.2.0",
    "zip_url": "https://github.com/someone/good-plugin/releases/download/v1.2.0/good.zip",
    "sha256": "a" * 64,
}


@pytest.fixture()
def app(tmp_path):
    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["SUBLARR_API_KEY"] = API_KEY
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    from config import reload_settings

    reload_settings()
    application = create_app(testing=True)
    application.config["TESTING"] = True
    with application.app_context():
        sa_db.create_all()
        _index(INDEXED)
        yield application
    for k in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
        os.environ.pop(k, None)
    reload_settings()


def _index(entry):
    from datetime import UTC, datetime

    from db.models.plugins import MarketplaceCache

    sa_db.session.add(
        MarketplaceCache(
            name=entry["name"],
            display_name=entry["display_name"],
            author="someone",
            version=entry["version"],
            description="",
            github_url="",
            zip_url=entry["zip_url"],
            sha256=entry["sha256"],
            capabilities="[]",
            min_sublarr_version="",
            is_official=0,
            last_fetched=datetime.now(UTC),
        )
    )
    sa_db.session.commit()


@pytest.fixture()
def signed_in(app):
    client = app.test_client()
    with client.session_transaction() as sess:
        grant_ui_session(sess)
    return client


def _install(client, body, **kw):
    fake = MagicMock(return_value={"path": "/config/plugins/good-plugin"})
    with (
        patch("services.marketplace.PluginMarketplace.install_plugin_from_zip", fake),
        patch("providers.plugins.get_plugin_manager", return_value=None),
    ):
        r = client.post("/api/v1/marketplace/install", json=body, **kw)
    return r, fake


def test_the_api_key_alone_cannot_install(app):
    r, fake = _install(app.test_client(), {"name": "good-plugin"}, headers={"X-Api-Key": API_KEY})
    assert r.status_code == 403
    assert r.get_json()["session_required"] is True
    fake.assert_not_called()


def test_install_uses_the_index_url_and_hash(signed_in):
    r, fake = _install(
        signed_in,
        {"name": "good-plugin", "zip_url": "https://evil.example/x.zip"},
    )
    assert r.status_code == 409
    fake.assert_not_called()

    r, fake = _install(signed_in, {"name": "good-plugin"})
    assert r.status_code == 200, r.get_json()
    kwargs = fake.call_args.kwargs
    assert kwargs["zip_url"] == INDEXED["zip_url"]
    assert kwargs["expected_sha256"] == INDEXED["sha256"]


def test_a_hash_that_differs_from_the_index_is_refused(signed_in):
    r, fake = _install(signed_in, {"name": "good-plugin", "sha256": "b" * 64})
    assert r.status_code == 409
    fake.assert_not_called()


def test_a_plugin_outside_the_index_is_refused(signed_in):
    with patch("routes.marketplace.install._registry_entry", return_value=None):
        r, fake = _install(
            signed_in,
            {"name": "other", "zip_url": "https://evil.example/x.zip", "sha256": "c" * 64},
        )
    assert r.status_code == 404
    fake.assert_not_called()


@pytest.mark.parametrize("name", [".", "..", "../x", "a/b", "Bad Name", ""])
def test_unsafe_names_are_refused(signed_in, name):
    r, fake = _install(signed_in, {"name": name})
    assert r.status_code == 400
    fake.assert_not_called()
    r = signed_in.post("/api/v1/marketplace/uninstall", json={"plugin_name": name})
    assert r.status_code == 400


def test_uninstall_needs_a_session_too(app):
    r = app.test_client().post(
        "/api/v1/marketplace/uninstall",
        json={"plugin_name": "good-plugin"},
        headers={"X-Api-Key": API_KEY},
    )
    assert r.status_code == 403


def test_the_service_refuses_to_delete_the_plugin_folder(tmp_path):
    from services.marketplace import PluginMarketplace

    (tmp_path / "keep").mkdir()
    with pytest.raises(RuntimeError):
        PluginMarketplace().uninstall_plugin(".", str(tmp_path))
    assert (tmp_path / "keep").is_dir()
