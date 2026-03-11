"""Tests for GitHubRegistry — GitHub topic search + DB cache."""

import json
import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app import create_app
from extensions import db as sa_db


@pytest.fixture()
def app(tmp_path):
    """Flask app with isolated SQLite DB."""
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


def _make_registry(github_token: str = "") -> "GitHubRegistry":  # noqa: F821
    from services.github_registry import GitHubRegistry

    return GitHubRegistry(github_token=github_token)


def _fresh_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _stale_timestamp() -> str:
    return (datetime.now(UTC) - timedelta(hours=2)).isoformat()


def _insert_cache_entry(app_ctx, name: str, last_fetched: str) -> None:
    from db.models.plugins import MarketplaceCache

    with app_ctx.app_context():
        entry = MarketplaceCache(
            name=name,
            display_name="Test Plugin",
            author="testauthor",
            version="1.0.0",
            description="A test plugin",
            github_url="https://github.com/testauthor/test-plugin",
            zip_url="https://github.com/testauthor/test-plugin/archive/v1.0.0.zip",
            sha256="abc123",
            capabilities=json.dumps(["provider"]),
            min_sublarr_version="0.22.0",
            is_official=0,
            last_fetched=last_fetched,
        )
        sa_db.session.add(entry)
        sa_db.session.commit()


# ---------------------------------------------------------------------------
# Test 1: cache hit — GitHub API NOT called when cache is fresh
# ---------------------------------------------------------------------------


def test_search_uses_cache_when_fresh(app):
    with app.app_context():
        _insert_cache_entry(app, "cached-plugin", _fresh_timestamp())

        registry = _make_registry()
        with patch.object(registry.session, "get") as mock_get:
            results = registry.search(force_refresh=False)

        mock_get.assert_not_called()
        assert len(results) == 1
        assert results[0]["name"] == "cached-plugin"


# ---------------------------------------------------------------------------
# Test 2: cache miss — GitHub API fetched, results stored in DB
# ---------------------------------------------------------------------------


def _make_search_response(repos: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"items": repos}
    return resp


def _make_manifest_response(manifest: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = manifest
    return resp


def test_search_fetches_github_when_stale(app):
    repo = {
        "full_name": "testauthor/my-provider",
        "html_url": "https://github.com/testauthor/my-provider",
        "description": "A great provider",
        "owner": {"login": "testauthor"},
    }
    manifest = {
        "name": "my-provider",
        "display_name": "My Provider",
        "version": "1.2.0",
        "entry_point": "provider.py",
        "class_name": "MyProvider",
        "author": "testauthor",
        "capabilities": ["provider"],
        "min_sublarr_version": "0.22.0",
        "zip_url": "https://example.com/my-provider.zip",
        "sha256": "deadbeef",
    }

    search_resp = _make_search_response([repo])
    manifest_resp = _make_manifest_response(manifest)

    with app.app_context():
        registry = _make_registry()
        # Map side_effect: first call = GitHub search, second = manifest fetch
        registry.session.get = MagicMock(side_effect=[search_resp, manifest_resp])

        with patch.object(registry, "_load_official_names", return_value=set()):
            results = registry.search(force_refresh=True)

        assert len(results) == 1
        assert results[0]["name"] == "my-provider"
        assert results[0]["version"] == "1.2.0"

        # Verify stored in DB
        from db.models.plugins import MarketplaceCache

        row = sa_db.session.get(MarketplaceCache, "my-provider")
        assert row is not None
        assert row.version == "1.2.0"


# ---------------------------------------------------------------------------
# Test 3: sha256 flows from manifest into result dict
# ---------------------------------------------------------------------------


def test_sha256_included_in_result(app):
    repo = {
        "full_name": "author/sha-plugin",
        "html_url": "https://github.com/author/sha-plugin",
        "description": "",
        "owner": {"login": "author"},
    }
    manifest = {
        "name": "sha-plugin",
        "display_name": "SHA Plugin",
        "version": "0.1.0",
        "entry_point": "provider.py",
        "class_name": "ShaPlugin",
        "sha256": "cafebabe1234567890abcdef",
    }

    search_resp = _make_search_response([repo])
    manifest_resp = _make_manifest_response(manifest)

    with app.app_context():
        registry = _make_registry()
        registry.session.get = MagicMock(side_effect=[search_resp, manifest_resp])

        with patch.object(registry, "_load_official_names", return_value=set()):
            results = registry.search(force_refresh=True)

        assert len(results) == 1
        assert results[0]["sha256"] == "cafebabe1234567890abcdef"


# ---------------------------------------------------------------------------
# Test 4: manifest missing required field — plugin skipped
# ---------------------------------------------------------------------------


def test_missing_required_field_skipped(app):
    repo = {
        "full_name": "author/bad-plugin",
        "html_url": "https://github.com/author/bad-plugin",
        "description": "",
        "owner": {"login": "author"},
    }
    # Missing 'class_name'
    manifest = {
        "name": "bad-plugin",
        "display_name": "Bad Plugin",
        "version": "0.1.0",
        "entry_point": "provider.py",
        # class_name intentionally absent
    }

    search_resp = _make_search_response([repo])
    manifest_resp = _make_manifest_response(manifest)

    with app.app_context():
        registry = _make_registry()
        registry.session.get = MagicMock(side_effect=[search_resp, manifest_resp])

        with patch.object(registry, "_load_official_names", return_value=set()):
            results = registry.search(force_refresh=True)

        assert results == []


# ---------------------------------------------------------------------------
# Test 5: official badge — is_official=True for names in official registry
# ---------------------------------------------------------------------------


def test_official_badge(app):
    repo = {
        "full_name": "community/opensubtitles-enhanced",
        "html_url": "https://github.com/community/opensubtitles-enhanced",
        "description": "Enhanced OpenSubtitles provider",
        "owner": {"login": "community"},
    }
    manifest = {
        "name": "opensubtitles-enhanced",
        "display_name": "OpenSubtitles Enhanced",
        "version": "2.0.0",
        "entry_point": "provider.py",
        "class_name": "OpenSubtitlesEnhancedProvider",
    }

    search_resp = _make_search_response([repo])
    manifest_resp = _make_manifest_response(manifest)

    with app.app_context():
        registry = _make_registry()
        registry.session.get = MagicMock(side_effect=[search_resp, manifest_resp])

        with patch.object(
            registry,
            "_load_official_names",
            return_value={"opensubtitles-enhanced"},
        ):
            results = registry.search(force_refresh=True)

        assert len(results) == 1
        assert results[0]["is_official"] is True
