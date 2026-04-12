"""Extended tests for services/marketplace.py — PluginMarketplace operations."""

import hashlib
import io
import os
import zipfile
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_zip_bytes(files=None):
    """Create a minimal ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if files:
            for name, content in files.items():
                zf.writestr(name, content)
        else:
            zf.writestr("provider.py", "class P: pass")
    return buf.getvalue()


FAKE_REGISTRY = {
    "plugins": [
        {
            "name": "test-plugin",
            "category": "provider",
            "description": "A test plugin",
            "author": "tester",
            "version": "1.0.0",
            "url": "https://github.com/test/test-plugin.git",
        },
        {
            "name": "zip-plugin",
            "category": "tool",
            "description": "A zip plugin",
            "author": "tester",
            "version": "2.0.0",
            "url": "https://example.com/plugin.zip",
        },
        {
            "name": "no-url-plugin",
            "category": "provider",
            "description": "No URL",
            "author": "tester",
            "version": "1.0.0",
        },
    ]
}


# ---------------------------------------------------------------------------
# verify_zip_sha256
# ---------------------------------------------------------------------------


def test_sha256_none_value_skips():
    """None expected_sha256 skips check."""
    from services.marketplace import verify_zip_sha256

    assert verify_zip_sha256(b"data", None) is True


# ---------------------------------------------------------------------------
# PluginMarketplace.fetch_registry
# ---------------------------------------------------------------------------


def test_fetch_registry_success():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with patch("services.marketplace.requests.get") as mock_get:
        resp = MagicMock()
        resp.json.return_value = FAKE_REGISTRY
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        result = marketplace.fetch_registry()
    assert "plugins" in result
    assert len(result["plugins"]) == 3


def test_fetch_registry_cached():
    """Second call uses cache."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    result = marketplace.fetch_registry()
    assert result is FAKE_REGISTRY


def test_fetch_registry_failure():
    """Raises RuntimeError on network failure."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with (
        patch("services.marketplace.requests.get", side_effect=Exception("network error")),
        pytest.raises(RuntimeError, match="Failed to fetch"),
    ):
        marketplace.fetch_registry()


def test_fetch_registry_blocked_url():
    """Raises RuntimeError when URL is blocked by security."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace(registry_url="http://169.254.169.254/metadata")
    with (
        patch("services.marketplace.validate_service_url", return_value=(False, "blocked")),
        pytest.raises(RuntimeError, match="blocked for security"),
    ):
        marketplace.fetch_registry()


# ---------------------------------------------------------------------------
# list_plugins
# ---------------------------------------------------------------------------


def test_list_plugins_all():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    plugins = marketplace.list_plugins()
    assert len(plugins) == 3


def test_list_plugins_by_category():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    plugins = marketplace.list_plugins(category="provider")
    assert len(plugins) == 2
    assert all(p["category"] == "provider" for p in plugins)


def test_list_plugins_unknown_category():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    plugins = marketplace.list_plugins(category="nonexistent")
    assert len(plugins) == 0


# ---------------------------------------------------------------------------
# get_plugin_info
# ---------------------------------------------------------------------------


def test_get_plugin_info_found():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    info = marketplace.get_plugin_info("test-plugin")
    assert info is not None
    assert info["name"] == "test-plugin"


def test_get_plugin_info_not_found():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    assert marketplace.get_plugin_info("nonexistent") is None


# ---------------------------------------------------------------------------
# install_plugin
# ---------------------------------------------------------------------------


def test_install_plugin_not_found():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = {"plugins": []}
    with pytest.raises(RuntimeError, match="Plugin not found"):
        marketplace.install_plugin("nonexistent", "/tmp/plugins")


def test_install_plugin_no_url():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    with pytest.raises(RuntimeError, match="no installation URL"):
        marketplace.install_plugin("no-url-plugin", "/tmp/plugins")


def test_install_plugin_git(tmp_path):
    """Git-based plugin triggers _install_from_git."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    marketplace._install_from_git = MagicMock(return_value={"status": "installed"})

    result = marketplace.install_plugin("test-plugin", str(tmp_path))
    assert result["status"] == "installed"
    marketplace._install_from_git.assert_called_once()


def test_install_plugin_zip(tmp_path):
    """ZIP-based plugin triggers _install_from_zip."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    marketplace._install_from_zip = MagicMock(return_value={"status": "installed"})

    result = marketplace.install_plugin("zip-plugin", str(tmp_path))
    assert result["status"] == "installed"
    marketplace._install_from_zip.assert_called_once()


# ---------------------------------------------------------------------------
# _install_from_git
# ---------------------------------------------------------------------------


def test_install_from_git_success(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    str(tmp_path / "test-plugin")

    with (
        patch("services.marketplace.subprocess.run", return_value=MagicMock(returncode=0)),
        patch("services.marketplace.validate_git_url"),
    ):
        result = marketplace._install_from_git(
            "https://github.com/test/test-plugin.git",
            "test-plugin",
            str(tmp_path),
        )
    assert result["status"] == "installed"


def test_install_from_git_timeout(tmp_path):
    import subprocess

    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with (
        patch(
            "services.marketplace.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 60)
        ),
        patch("services.marketplace.validate_git_url"),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        marketplace._install_from_git(
            "https://github.com/test/test-plugin.git",
            "test-plugin",
            str(tmp_path),
        )


def test_install_from_git_not_found(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with (
        patch("services.marketplace.subprocess.run", side_effect=FileNotFoundError),
        patch("services.marketplace.validate_git_url"),
        pytest.raises(RuntimeError, match="git not found"),
    ):
        marketplace._install_from_git(
            "https://github.com/test/test-plugin.git",
            "test-plugin",
            str(tmp_path),
        )


def test_install_from_git_path_traversal(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with (
        patch("services.marketplace.is_safe_path", return_value=False),
        patch("services.marketplace.validate_git_url"),
        pytest.raises(RuntimeError, match="path traversal"),
    ):
        marketplace._install_from_git(
            "https://github.com/test/test-plugin.git",
            "../escape",
            str(tmp_path),
        )


# ---------------------------------------------------------------------------
# _install_from_zip
# ---------------------------------------------------------------------------


def test_install_from_zip_http_rejected(tmp_path):
    """Non-HTTPS URL is rejected."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with pytest.raises(RuntimeError, match="HTTPS"):
        marketplace._install_from_zip(
            "http://example.com/plugin.zip",
            "test-plugin",
            str(tmp_path),
        )


def test_install_from_zip_success(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    data = _make_zip_bytes()

    with (
        patch("services.marketplace.requests.get") as mock_get,
        patch("services.marketplace.safe_zip_extract"),
    ):
        resp = MagicMock()
        resp.content = data
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp
        result = marketplace._install_from_zip(
            "https://example.com/plugin.zip",
            "test-plugin",
            str(tmp_path),
        )
    assert result["status"] == "installed"


# ---------------------------------------------------------------------------
# _validate_plugin
# ---------------------------------------------------------------------------


def test_validate_plugin_valid(tmp_path):
    """Plugin with required files is valid."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "__init__.py").write_text("")
    (plugin_dir / "provider.py").write_text("class P: pass")

    result = marketplace._validate_plugin(str(plugin_dir))
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_validate_plugin_missing_files(tmp_path):
    """Plugin missing required files is invalid."""
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()

    result = marketplace._validate_plugin(str(plugin_dir))
    assert result["valid"] is False
    assert len(result["errors"]) == 2


# ---------------------------------------------------------------------------
# check_updates
# ---------------------------------------------------------------------------


def test_check_updates_found():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    updates = marketplace.check_updates(["test-plugin"])
    assert "test-plugin" in updates
    assert updates["test-plugin"]["available"] is True
    assert updates["test-plugin"]["latest_version"] == "1.0.0"


def test_check_updates_not_in_registry():
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    marketplace.registry_cache = FAKE_REGISTRY
    updates = marketplace.check_updates(["nonexistent"])
    assert "nonexistent" not in updates


# ---------------------------------------------------------------------------
# uninstall_plugin
# ---------------------------------------------------------------------------


def test_uninstall_plugin_success(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "provider.py").write_text("class P: pass")

    result = marketplace.uninstall_plugin("test-plugin", str(tmp_path))
    assert result["status"] == "uninstalled"
    assert not plugin_dir.exists()


def test_uninstall_plugin_not_found(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with pytest.raises(RuntimeError, match="Plugin not found"):
        marketplace.uninstall_plugin("nonexistent", str(tmp_path))


def test_uninstall_plugin_path_traversal(tmp_path):
    from services.marketplace import PluginMarketplace

    marketplace = PluginMarketplace()
    with (
        patch("services.marketplace.is_safe_path", return_value=False),
        pytest.raises(RuntimeError, match="path traversal"),
    ):
        marketplace.uninstall_plugin("../escape", str(tmp_path))
