"""Tests for singleton lifecycle via app.extensions."""

from unittest.mock import MagicMock


def test_extensions_populated_after_create_app(app_ctx):
    """Both singletons must be in app.extensions after create_app()."""
    from flask import current_app

    from providers import ProviderManager
    from wanted_scanner import WantedScanner

    assert isinstance(current_app.extensions["wanted_scanner"], WantedScanner)
    assert isinstance(current_app.extensions["provider_manager"], ProviderManager)


def test_get_scanner_returns_extension_value(app_ctx):
    """get_scanner() must return the app.extensions value when inside an app context."""
    from flask import current_app

    from wanted_scanner import get_scanner

    mock = MagicMock()
    current_app.extensions["wanted_scanner"] = mock
    assert get_scanner() is mock


def test_get_provider_manager_returns_extension_value(app_ctx):
    """get_provider_manager() must return the app.extensions value when inside an app context."""
    from flask import current_app

    from providers import get_provider_manager

    mock = MagicMock()
    current_app.extensions["provider_manager"] = mock
    assert get_provider_manager() is mock


def test_invalidate_scanner_clears_extensions(app_ctx):
    """invalidate_scanner() must remove the entry from app.extensions."""
    from flask import current_app

    from wanted_scanner import invalidate_scanner

    current_app.extensions["wanted_scanner"] = MagicMock()
    invalidate_scanner()
    assert "wanted_scanner" not in current_app.extensions


def test_invalidate_manager_clears_extensions(app_ctx):
    """invalidate_manager() must remove the entry from app.extensions."""
    from flask import current_app

    from providers import invalidate_manager

    current_app.extensions["provider_manager"] = MagicMock()
    invalidate_manager()
    assert "provider_manager" not in current_app.extensions


def test_get_scanner_self_heals_after_invalidation(app_ctx):
    """After invalidation, next get_scanner() call must re-populate app.extensions."""
    from flask import current_app

    from wanted_scanner import get_scanner, invalidate_scanner

    invalidate_scanner()
    assert "wanted_scanner" not in current_app.extensions

    # First call after invalidation creates a new scanner and re-populates extensions
    scanner = get_scanner()
    assert "wanted_scanner" in current_app.extensions
    assert current_app.extensions["wanted_scanner"] is scanner


def test_get_provider_manager_self_heals_after_invalidation(app_ctx, monkeypatch):
    """After invalidation, next get_provider_manager() call must re-populate app.extensions."""
    from flask import current_app

    from providers import get_provider_manager, invalidate_manager

    # Patch DB calls so ProviderManager() doesn't hit real DB during recreation
    monkeypatch.setattr("db.providers.is_provider_auto_disabled", lambda name: True)
    monkeypatch.setattr("db.providers.get_provider_stats", lambda: {})

    invalidate_manager()
    assert "provider_manager" not in current_app.extensions

    manager = get_provider_manager()
    assert "provider_manager" in current_app.extensions
    assert current_app.extensions["provider_manager"] is manager
