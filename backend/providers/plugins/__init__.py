"""Plugin manager for subtitle provider plugins.

Manages the lifecycle of plugin providers: discovery, loading, validation,
registration into the global _PROVIDER_CLASSES registry, and reloading.

Usage:
    from providers.plugins import init_plugin_manager, get_plugin_manager

    # At app startup:
    manager = init_plugin_manager("/config/plugins")
    loaded, errors = manager.discover()

    # Later, to reload:
    manager = get_plugin_manager()
    loaded, errors = manager.reload()
"""

import logging
from dataclasses import asdict

from providers.plugins.loader import discover_plugins, unload_plugin
from providers.plugins.manifest import extract_manifest

logger = logging.getLogger(__name__)


class PluginManager:
    """Manages subtitle provider plugins from a plugins directory."""

    def __init__(self, plugins_dir: str):
        """Initialize the plugin manager.

        Args:
            plugins_dir: Absolute path to the directory containing plugin .py files.
        """
        self.plugins_dir = plugins_dir
        self._loaded: dict[str, type] = {}  # name -> class
        self._errors: list[dict] = []  # [{"file": str, "error": str}]

    def discover(self) -> tuple[list[str], list[dict]]:
        """Discover and register plugin providers.

        Scans plugins_dir for .py files, validates SubtitleProvider subclasses,
        and registers valid ones in _PROVIDER_CLASSES with is_plugin=True.

        Returns:
            (loaded_names, errors) where:
                loaded_names: list of successfully loaded provider names
                errors: list of {"file": str, "error": str} dicts
        """
        from providers import _PROVIDER_CLASSES

        # Get existing (built-in) provider names
        existing_names = set(_PROVIDER_CLASSES.keys())

        discovered, errors = discover_plugins(self.plugins_dir, existing_names)

        loaded_names = []
        for name, cls in discovered.items():
            # Mark as plugin
            cls.is_plugin = True

            # Register directly in the global registry (not via decorator)
            _PROVIDER_CLASSES[name] = cls
            self._loaded[name] = cls
            loaded_names.append(name)

        self._errors = errors
        return loaded_names, errors

    def reload(self) -> tuple[list[str], list[dict]]:
        """Unload all currently loaded plugins and re-discover.

        Removes loaded plugins from _PROVIDER_CLASSES and sys.modules,
        then calls discover() again.

        Returns:
            (loaded_names, errors) -- same as discover().
        """
        from providers import _PROVIDER_CLASSES

        # Unload all currently loaded plugins
        for name, cls in list(self._loaded.items()):
            if name in _PROVIDER_CLASSES:
                del _PROVIDER_CLASSES[name]
            # Unload the module from sys.modules
            module_name = getattr(cls, "__module__", "")
            if module_name:
                unload_plugin(module_name)

        self._loaded.clear()
        self._errors.clear()

        # Re-discover
        return self.discover()

    def get_plugin_info(self) -> list[dict]:
        """Get information about all loaded plugins.

        Returns:
            List of dicts with plugin info (from PluginManifest), plus
            'enabled' and 'is_loaded' status fields.
        """
        infos = []
        for name, cls in self._loaded.items():
            manifest = extract_manifest(cls)
            info = asdict(manifest)
            info["enabled"] = True
            info["is_loaded"] = True
            infos.append(info)
        return infos

    def get_errors(self) -> list[dict]:
        """Get errors from the last discover/reload."""
        return list(self._errors)


# Module-level singleton
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager | None:
    """Get the current plugin manager instance (may be None if not initialized)."""
    return _plugin_manager


def init_plugin_manager(plugins_dir: str) -> PluginManager:
    """Initialize the global plugin manager singleton.

    Args:
        plugins_dir: Absolute path to the plugins directory.

    Returns:
        The initialized PluginManager instance.
    """
    global _plugin_manager
    _plugin_manager = PluginManager(plugins_dir)
    return _plugin_manager
