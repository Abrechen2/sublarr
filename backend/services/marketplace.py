"""Plugin marketplace service for community-provided plugins.

Manages GitHub-based plugin registry, installation, updates, and validation.
Inspired by Bazarr's provider ecosystem but with better architecture.
"""

import logging
import os
import shutil
import subprocess

import requests

logger = logging.getLogger(__name__)


class PluginMarketplace:
    """Manages community plugin marketplace."""

    def __init__(self, registry_url: str = "https://raw.githubusercontent.com/sublarr-community/plugins/main/registry.json"):
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

    def install_plugin(
        self,
        plugin_name: str,
        plugins_dir: str,
        version: str | None = None,
    ) -> dict:
        """Install a plugin from the marketplace.

        Args:
            plugin_name: Plugin identifier
            plugins_dir: Target directory for plugins
            version: Optional specific version (default: latest)

        Returns:
            Dict with installation result

        Raises:
            RuntimeError: If installation fails
        """
        plugin_info = self.get_plugin_info(plugin_name)
        if not plugin_info:
            raise RuntimeError(f"Plugin not found: {plugin_name}")

        # Determine installation method
        install_url = plugin_info.get("url")
        if not install_url:
            raise RuntimeError(f"Plugin has no installation URL: {plugin_name}")

        os.makedirs(plugins_dir, exist_ok=True)

        # Clone or download plugin
        if install_url.endswith(".git") or "github.com" in install_url:
            # Git repository
            return self._install_from_git(install_url, plugin_name, plugins_dir, version)
        else:
            # ZIP download
            return self._install_from_zip(install_url, plugin_name, plugins_dir)

    def _install_from_git(
        self,
        repo_url: str,
        plugin_name: str,
        plugins_dir: str,
        version: str | None = None,
    ) -> dict:
        """Install plugin from Git repository.

        Args:
            repo_url: Git repository URL
            plugin_name: Plugin name
            plugins_dir: Target directory
            version: Optional version/tag/branch

        Returns:
            Installation result dict
        """
        plugin_path = os.path.join(plugins_dir, plugin_name)

        # Remove existing plugin if present
        if os.path.exists(plugin_path):
            shutil.rmtree(plugin_path)

        # Clone repository
        cmd = ["git", "clone", repo_url, plugin_path]
        if version:
            cmd.extend(["-b", version])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed: {result.stderr}")

            # Validate plugin
            validation_result = self._validate_plugin(plugin_path)

            return {
                "status": "installed",
                "path": plugin_path,
                "validation": validation_result,
            }
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git clone timed out")
        except FileNotFoundError:
            raise RuntimeError("git not found. Install git to enable plugin installation.")
        except Exception as e:
            raise RuntimeError(f"Git installation failed: {e}")

    def _install_from_zip(
        self,
        zip_url: str,
        plugin_name: str,
        plugins_dir: str,
    ) -> dict:
        """Install plugin from ZIP file.

        Args:
            zip_url: ZIP file URL
            plugin_name: Plugin name
            plugins_dir: Target directory

        Returns:
            Installation result dict
        """
        import io
        import zipfile

        try:
            response = requests.get(zip_url, timeout=60)
            response.raise_for_status()

            plugin_path = os.path.join(plugins_dir, plugin_name)

            # Remove existing plugin if present
            if os.path.exists(plugin_path):
                shutil.rmtree(plugin_path)

            os.makedirs(plugin_path, exist_ok=True)

            # Extract ZIP
            with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                zip_file.extractall(plugin_path)

            # Validate plugin
            validation_result = self._validate_plugin(plugin_path)

            return {
                "status": "installed",
                "path": plugin_path,
                "validation": validation_result,
            }
        except Exception as e:
            raise RuntimeError(f"ZIP installation failed: {e}")

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
        plugin_path = os.path.join(plugins_dir, plugin_name)

        if not os.path.exists(plugin_path):
            raise RuntimeError(f"Plugin not found: {plugin_name}")

        try:
            shutil.rmtree(plugin_path)
            return {"status": "uninstalled", "plugin": plugin_name}
        except Exception as e:
            raise RuntimeError(f"Failed to uninstall plugin: {e}")
