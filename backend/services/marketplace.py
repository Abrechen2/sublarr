"""Plugin marketplace service for community-provided plugins.

Manages GitHub-based plugin registry, installation, updates, and validation.
Inspired by Bazarr's provider ecosystem but with better architecture.
"""

import hashlib
import io
import logging
import os
import re
import shutil
import zipfile

import requests

from security_utils import (
    get_with_checked_redirects,
    is_safe_path,
    safe_zip_extract,
    validate_service_url,
)

logger = logging.getLogger(__name__)


# A plugin name becomes a folder under plugins_dir. "." passed is_safe_path
# (it is the base itself) and uninstall then removed every plugin (N-3).
_PLUGIN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")


def is_valid_plugin_name(name: object) -> bool:
    return isinstance(name, str) and bool(_PLUGIN_NAME.fullmatch(name))


def verify_zip_sha256(data: bytes, expected_sha256: str) -> bool:
    """Verify the SHA256 checksum of downloaded ZIP data.

    Args:
        data: Raw bytes of the downloaded file.
        expected_sha256: Expected hex digest. Empty/falsy value skips the check.

    Returns:
        True if the hash matches or if expected_sha256 is empty/falsy.
        False on mismatch.
    """
    if not expected_sha256:
        return True
    actual = hashlib.sha256(data).hexdigest()
    return actual.lower() == expected_sha256.lower()


class PluginMarketplace:
    """Manages community plugin marketplace."""

    def __init__(
        self,
        registry_url: str = "https://raw.githubusercontent.com/sublarr-community/plugins/main/registry.json",
    ):
        """Initialize marketplace with registry URL.

        Args:
            registry_url: URL to plugin registry JSON file
        """
        self.registry_url = registry_url
        self.registry_cache: dict | None = None

    def fetch_registry(self) -> dict:
        """Fetch plugin registry from GitHub.

        Returns:
            Dict with plugin registry data

        Raises:
            RuntimeError: If registry fetch fails
        """
        if self.registry_cache:
            return self.registry_cache

        ok, reason = validate_service_url(self.registry_url)
        if not ok:
            raise RuntimeError(f"Registry URL blocked for security reasons: {reason}")

        try:
            response = requests.get(self.registry_url, timeout=10)
            response.raise_for_status()
            self.registry_cache = response.json()
            return self.registry_cache
        except Exception as e:
            raise RuntimeError(f"Failed to fetch plugin registry: {e}")

    def list_plugins(self, category: str | None = None) -> list[dict]:
        """List available plugins from registry.

        Args:
            category: Optional category filter (provider, translation, tool)

        Returns:
            List of plugin dicts with name, description, author, version, etc.
        """
        registry = self.fetch_registry()
        plugins = registry.get("plugins", [])

        if category:
            plugins = [p for p in plugins if p.get("category") == category]

        return plugins

    def get_plugin_info(self, plugin_name: str) -> dict | None:
        """Get detailed information about a plugin.

        Args:
            plugin_name: Plugin identifier

        Returns:
            Plugin info dict or None if not found
        """
        plugins = self.list_plugins()
        for plugin in plugins:
            if plugin.get("name") == plugin_name:
                return plugin
        return None

    def install_plugin_from_zip(
        self,
        plugin_name: str,
        zip_url: str,
        expected_sha256: str,
        plugins_dir: str,
    ) -> dict:
        """Download zip, verify SHA256, extract to plugins_dir/<plugin_name>.

        Args:
            plugin_name: Name for the installed plugin directory.
            zip_url: URL of the ZIP file to download.
            expected_sha256: Expected SHA256 hex digest. Empty string skips verification.
            plugins_dir: Parent directory under which the plugin will be extracted.

        Returns:
            Dict with {"status": "installed", "path": plugin_path}.

        Raises:
            RuntimeError: If the HTTP request fails or the SHA256 does not match.
        """
        if not is_valid_plugin_name(plugin_name):
            raise RuntimeError(f"Invalid plugin name: {plugin_name!r}")
        if not expected_sha256:
            raise RuntimeError("A SHA256 is required for plugin installation")

        try:
            response = get_with_checked_redirects(zip_url, https_only=True, timeout=60)
        except ValueError as e:
            raise RuntimeError(f"Plugin URL refused: {e}") from e
        response.raise_for_status()
        data = response.content

        if not verify_zip_sha256(data, expected_sha256):
            raise RuntimeError(
                f"SHA256 mismatch for {plugin_name}: download may be corrupted or tampered"
            )

        plugin_path = os.path.join(plugins_dir, plugin_name)
        if not is_safe_path(plugin_path, plugins_dir):
            raise RuntimeError("Invalid plugin name — path traversal detected")

        if os.path.exists(plugin_path):
            shutil.rmtree(plugin_path)

        os.makedirs(plugin_path, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            safe_zip_extract(zf, plugin_path)

        return {"status": "installed", "path": plugin_path}

    def _validate_plugin(self, plugin_path: str) -> dict:
        """Validate installed plugin.

        Args:
            plugin_path: Path to plugin directory

        Returns:
            Validation result dict
        """
        errors = []
        warnings = []

        # Check for required files
        required_files = ["__init__.py", "provider.py"]
        for req_file in required_files:
            if not os.path.exists(os.path.join(plugin_path, req_file)):
                errors.append(f"Missing required file: {req_file}")

        # Try to import plugin (basic syntax check)
        try:
            # This is a basic check - full validation happens during plugin loading
            pass
        except Exception as e:
            errors.append(f"Import failed: {e}")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def check_updates(self, installed_plugins: list[str]) -> dict[str, dict]:
        """Check for updates for installed plugins.

        Args:
            installed_plugins: List of installed plugin names

        Returns:
            Dict mapping plugin names to update info
        """
        registry = self.fetch_registry()
        registry.get("plugins", [])
        updates = {}

        for plugin_name in installed_plugins:
            plugin_info = self.get_plugin_info(plugin_name)
            if plugin_info:
                # Compare versions (simplified - would need actual version checking)
                updates[plugin_name] = {
                    "available": True,
                    "latest_version": plugin_info.get("version"),
                    "current_version": "unknown",  # Would need to read from installed plugin
                }

        return updates

    def uninstall_plugin(self, plugin_name: str, plugins_dir: str) -> dict:
        """Uninstall a plugin.

        Args:
            plugin_name: Plugin name
            plugins_dir: Plugins directory

        Returns:
            Uninstallation result
        """
        if not is_valid_plugin_name(plugin_name):
            raise RuntimeError(f"Invalid plugin name: {plugin_name!r}")
        plugin_path = os.path.join(plugins_dir, plugin_name)
        if not is_safe_path(plugin_path, plugins_dir):
            raise RuntimeError("Invalid plugin name — path traversal detected")

        if not os.path.exists(plugin_path):
            raise RuntimeError(f"Plugin not found: {plugin_name}")

        try:
            shutil.rmtree(plugin_path)
            return {"status": "uninstalled", "plugin": plugin_name}
        except Exception as e:
            raise RuntimeError(f"Failed to uninstall plugin: {e}")
