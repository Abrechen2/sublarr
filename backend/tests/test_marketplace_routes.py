"""Tests for marketplace routes — /installed, /refresh, /install."""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Flask app with isolated SQLite DB and SQLAlchemy tables created."""
    db_path = str(tmp_path / "test.db")
    os.environ["SUBLARR_DB_PATH"] = db_path
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"

    from config import reload_settings

    reload_settings()

    application = create_app(testing=True)
    application.config["TESTING"] = True

    with application.app_context():
        sa_db.create_all()
        yield application

    os.environ.pop("SUBLARR_DB_PATH", None)
    os.environ.pop("SUBLARR_API_KEY", None)
    os.environ.pop("SUBLARR_LOG_LEVEL", None)


@pytest.fixture()
def client(app):
    """Test client bound to the SQLAlchemy-aware app fixture."""
    return app.test_client()


# ---------------------------------------------------------------------------
# GET /api/v1/marketplace/installed
# ---------------------------------------------------------------------------


def test_get_installed_empty(client):
    """GET /marketplace/installed returns empty list when no rows exist."""
    resp = client.get("/api/v1/marketplace/installed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {"installed": []}


def test_get_installed_with_data(app, client):
    """GET /marketplace/installed returns inserted plugin rows."""
    from db.models.plugins import InstalledPlugin

    with app.app_context():
        plugin = InstalledPlugin(
            name="my-provider",
            display_name="My Provider",
            version="1.0.0",
            plugin_dir="/config/plugins/my-provider",
            sha256="a" * 64,
            capabilities='["provider"]',
            enabled=1,
            installed_at=datetime(2026, 3, 11, 0, 0, 0, tzinfo=UTC),
        )
        sa_db.session.add(plugin)
        sa_db.session.commit()

    resp = client.get("/api/v1/marketplace/installed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["installed"]) == 1
    entry = data["installed"][0]
    assert entry["name"] == "my-provider"
    assert entry["display_name"] == "My Provider"
    assert entry["version"] == "1.0.0"
    assert entry["capabilities"] == ["provider"]
    assert entry["enabled"] is True


# ---------------------------------------------------------------------------
# POST /api/v1/marketplace/refresh
# ---------------------------------------------------------------------------


def test_refresh_calls_github_registry(client):
    """POST /marketplace/refresh calls GitHubRegistry.search(force_refresh=True)."""
    fake_plugins = [{"name": "plugin-a", "version": "1.0.0"}]

    mock_instance = MagicMock()
    mock_instance.search.return_value = fake_plugins

    with (
        patch("routes.marketplace.GitHubRegistry", return_value=mock_instance, create=True),
        patch("services.github_registry.GitHubRegistry") as mock_cls,
    ):
        # Patch within the module namespace where it is imported at call time
        mock_cls.return_value = mock_instance
        # The route does a local import, so patch the source module
        resp = client.post("/api/v1/marketplace/refresh")

    # Verify via a direct patch of the route's import path
    mock_registry = MagicMock()
    mock_registry.search.return_value = fake_plugins
    with patch("services.github_registry.GitHubRegistry", return_value=mock_registry):
        resp = client.post("/api/v1/marketplace/refresh")

    assert resp.status_code == 200
    data = resp.get_json()
    assert "plugins" in data
    assert "count" in data
    mock_registry.search.assert_called_once_with(force_refresh=True)


# ---------------------------------------------------------------------------
# POST /api/v1/marketplace/install
# ---------------------------------------------------------------------------


def test_install_rejects_missing_fields(client):
    """POST /marketplace/install with no body returns 400."""
    resp = client.post("/api/v1/marketplace/install", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data
    assert "zip_url" in data["error"] or "name" in data["error"]


def test_install_sha256_mismatch_returns_500(client):
    """Mock install_plugin_from_zip to raise RuntimeError; route must return 500."""
    with patch(
        "services.marketplace.PluginMarketplace.install_plugin_from_zip",
        side_effect=RuntimeError("SHA256 mismatch"),
    ):
        resp = client.post(
            "/api/v1/marketplace/install",
            json={
                "name": "bad-plugin",
                "zip_url": "https://example.com/bad-plugin.zip",
                "sha256": "wronghash",
            },
        )

    assert resp.status_code == 500
    data = resp.get_json()
    assert "error" in data
    assert "SHA256 mismatch" in data["error"]


# ---------------------------------------------------------------------------
# POST /api/v1/marketplace/uninstall
# ---------------------------------------------------------------------------


def test_uninstall_route_deletes_db_row_and_reloads(app, client):
    """Regression: pre-2026-04-30 the uninstall route only removed files
    from disk. The InstalledPlugin row stayed, so /marketplace/installed
    kept showing a ghost entry, and the manager kept the plugin live in
    memory until restart. Now the route must delete the DB row and call
    manager.reload()/invalidate_manager()."""
    from db.models.plugins import InstalledPlugin

    with app.app_context():
        sa_db.session.add(
            InstalledPlugin(
                name="ghost-plugin",
                display_name="Ghost",
                version="1.0.0",
                plugin_dir="/config/plugins/ghost-plugin",
                sha256="b" * 64,
                capabilities="[]",
                enabled=1,
                installed_at=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
            )
        )
        sa_db.session.commit()
        assert InstalledPlugin.query.filter_by(name="ghost-plugin").first() is not None

    fake_manager = MagicMock()
    with (
        patch(
            "services.marketplace.PluginMarketplace.uninstall_plugin",
            return_value={"status": "uninstalled", "plugin": "ghost-plugin"},
        ),
        patch("providers.plugins.get_plugin_manager", return_value=fake_manager),
        patch("providers.invalidate_manager") as mock_invalidate,
    ):
        resp = client.post(
            "/api/v1/marketplace/uninstall",
            json={"plugin_name": "ghost-plugin"},
        )

    assert resp.status_code == 200
    fake_manager.reload.assert_called_once()
    mock_invalidate.assert_called_once()

    with app.app_context():
        assert InstalledPlugin.query.filter_by(name="ghost-plugin").first() is None


def test_uninstall_route_missing_plugin_name(client):
    """Empty body returns 400."""
    resp = client.post("/api/v1/marketplace/uninstall", json={})
    assert resp.status_code == 400
    assert "plugin_name" in resp.get_json()["error"]


def test_uninstall_route_works_without_db_row(app, client):
    """If the DB row is already gone (e.g. previous failed cleanup), the
    delete is a no-op and uninstall still succeeds."""
    fake_manager = MagicMock()
    with (
        patch(
            "services.marketplace.PluginMarketplace.uninstall_plugin",
            return_value={"status": "uninstalled", "plugin": "ghostier"},
        ),
        patch("providers.plugins.get_plugin_manager", return_value=fake_manager),
        patch("providers.invalidate_manager"),
    ):
        resp = client.post(
            "/api/v1/marketplace/uninstall",
            json={"plugin_name": "ghostier"},
        )

    assert resp.status_code == 200
