"""Tests for marketplace_cache and installed_plugins DB tables."""

import os

import pytest

from app import create_app
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Create a Flask app with an isolated SQLite DB for testing."""
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


def test_marketplace_cache_table_exists(app):
    """marketplace_cache table is created by create_all."""
    from db.models.plugins import MarketplaceCache

    with app.app_context():
        # inspect via SQLAlchemy — table must be present in metadata
        assert MarketplaceCache.__table__ is not None
        assert MarketplaceCache.__tablename__ == "marketplace_cache"


def test_installed_plugins_table_exists(app):
    """installed_plugins table is created by create_all."""
    from db.models.plugins import InstalledPlugin

    with app.app_context():
        assert InstalledPlugin.__table__ is not None
        assert InstalledPlugin.__tablename__ == "installed_plugins"


def test_insert_marketplace_cache_row(app):
    """Can insert a row into marketplace_cache and retrieve it."""
    from db.models.plugins import MarketplaceCache

    with app.app_context():
        entry = MarketplaceCache(
            name="test-provider",
            display_name="Test Provider",
            author="testauthor",
            version="1.2.3",
            description="A test subtitle provider plugin.",
            github_url="https://github.com/testauthor/test-provider",
            zip_url="https://github.com/testauthor/test-provider/archive/v1.2.3.zip",
            sha256="a" * 64,
            capabilities='["provider"]',
            min_sublarr_version="0.22.0",
            is_official=0,
            last_fetched="2026-03-11T00:00:00Z",
        )
        sa_db.session.add(entry)
        sa_db.session.commit()

        fetched = sa_db.session.get(MarketplaceCache, "test-provider")
        assert fetched is not None
        assert fetched.display_name == "Test Provider"
        assert fetched.author == "testauthor"
        assert fetched.version == "1.2.3"
        assert fetched.is_official == 0
        assert fetched.sha256 == "a" * 64


def test_insert_installed_plugin_row(app):
    """Can insert a row into installed_plugins and retrieve it."""
    from db.models.plugins import InstalledPlugin

    with app.app_context():
        plugin = InstalledPlugin(
            name="test-provider",
            display_name="Test Provider",
            version="1.2.3",
            plugin_dir="/config/plugins/test-provider",
            sha256="b" * 64,
            capabilities='["provider"]',
            enabled=1,
            installed_at="2026-03-11T00:00:00Z",
        )
        sa_db.session.add(plugin)
        sa_db.session.commit()

        fetched = sa_db.session.get(InstalledPlugin, "test-provider")
        assert fetched is not None
        assert fetched.display_name == "Test Provider"
        assert fetched.version == "1.2.3"
        assert fetched.plugin_dir == "/config/plugins/test-provider"
        assert fetched.enabled == 1
        assert fetched.sha256 == "b" * 64


def test_marketplace_cache_defaults(app):
    """marketplace_cache columns with defaults produce expected values."""
    from db.models.plugins import MarketplaceCache

    with app.app_context():
        entry = MarketplaceCache(
            name="minimal-plugin",
            display_name="Minimal Plugin",
            last_fetched="2026-03-11T00:00:00Z",
        )
        sa_db.session.add(entry)
        sa_db.session.commit()

        fetched = sa_db.session.get(MarketplaceCache, "minimal-plugin")
        assert fetched.author == ""
        assert fetched.version == "0.0.0"
        assert fetched.description == ""
        assert fetched.capabilities == "[]"
        assert fetched.is_official == 0


def test_installed_plugin_defaults(app):
    """installed_plugins columns with defaults produce expected values."""
    from db.models.plugins import InstalledPlugin

    with app.app_context():
        plugin = InstalledPlugin(
            name="minimal-plugin",
            installed_at="2026-03-11T00:00:00Z",
        )
        sa_db.session.add(plugin)
        sa_db.session.commit()

        fetched = sa_db.session.get(InstalledPlugin, "minimal-plugin")
        assert fetched.display_name == ""
        assert fetched.version == "0.0.0"
        assert fetched.plugin_dir == ""
        assert fetched.capabilities == "[]"
        assert fetched.enabled == 1
