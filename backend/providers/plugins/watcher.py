"""Watchdog-based file watcher for plugin hot-reload.

Monitors the plugins directory for .py file changes and triggers
debounced plugin reload. Optional -- requires the `watchdog` package.
If watchdog is not installed, the watcher cannot be started (graceful
degradation handled in app.py).
"""

import logging
import threading

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class PluginFileWatcher(FileSystemEventHandler):
    """Watches plugins directory for .py file changes and triggers reload.

    Uses a debounce timer to coalesce rapid file system events (e.g.,
    editor save-then-reformat) into a single reload call.
    """

    def __init__(self, plugin_manager, debounce_seconds: float = 2.0):
        """Initialize the watcher.

        Args:
            plugin_manager: The PluginManager instance to call reload() on.
            debounce_seconds: Seconds to wait after last event before reloading.
        """
        super().__init__()
        self.plugin_manager = plugin_manager
        self.debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _is_plugin_file(self, path: str) -> bool:
        """Check if a path is a plugin Python file (not private/hidden)."""
        if not path.endswith(".py"):
            return False
        # Extract filename from path
        import os
        filename = os.path.basename(path)
        return not (filename.startswith("_") or filename.startswith("."))

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        if self._is_plugin_file(event.src_path):
            logger.debug("Plugin file modified: %s", event.src_path)
            self._schedule_reload()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        if self._is_plugin_file(event.src_path):
            logger.debug("Plugin file created: %s", event.src_path)
            self._schedule_reload()

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return
        if self._is_plugin_file(event.src_path):
            logger.debug("Plugin file deleted: %s", event.src_path)
            self._schedule_reload()

    def _schedule_reload(self) -> None:
        """Schedule a debounced reload.

        Cancels any pending timer and starts a new one. Only the last
        event within the debounce window triggers a reload.
        """
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_seconds, self._debounced_reload
            )
            self._timer.daemon = True
            self._timer.start()

    def _debounced_reload(self) -> None:
        """Perform the actual plugin reload after debounce period.

        Never raises -- exceptions are caught and logged to prevent
        crashing the watcher thread.
        """
        try:
            logger.info("Hot-reloading plugins...")
            loaded, errors = self.plugin_manager.reload()

            # Invalidate ProviderManager so new/updated plugins are used
            from providers import invalidate_manager
            invalidate_manager()

            if loaded:
                logger.info("Hot-reload complete: loaded %d plugins: %s", len(loaded), loaded)
            else:
                logger.info("Hot-reload complete: no plugins loaded")

            if errors:
                for err in errors:
                    logger.warning("Hot-reload error: %s -- %s", err["file"], err["error"])

        except Exception as e:
            logger.error("Hot-reload failed: %s", e, exc_info=True)


def start_plugin_watcher(plugin_manager, plugins_dir: str) -> Observer:
    """Start a file system observer watching the plugins directory.

    Args:
        plugin_manager: The PluginManager instance.
        plugins_dir: Absolute path to the plugins directory.

    Returns:
        The started Observer instance (for later cleanup via stop_plugin_watcher).
    """
    handler = PluginFileWatcher(plugin_manager)
    observer = Observer()
    observer.schedule(handler, plugins_dir, recursive=False)
    observer.daemon = True
    observer.start()
    logger.info("Plugin file watcher started on: %s", plugins_dir)
    return observer


def stop_plugin_watcher(observer: Observer) -> None:
    """Stop the file system observer.

    Args:
        observer: The Observer instance returned by start_plugin_watcher.
    """
    try:
        observer.stop()
        observer.join(timeout=5)
        logger.info("Plugin file watcher stopped")
    except Exception as e:
        logger.warning("Error stopping plugin file watcher: %s", e)
