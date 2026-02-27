"""Standalone mode package -- folder-watch operation without Sonarr/Radarr.

StandaloneManager is the singleton orchestrator that owns the watcher,
scanner, and metadata resolver. It starts/stops based on standalone_enabled config.

Provides filesystem watching (watcher.py), media file parsing (parser.py),
and directory scanning (scanner.py) for standalone subtitle management.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional["StandaloneManager"] = None
_manager_lock = threading.Lock()


def get_standalone_manager() -> "StandaloneManager":
    """Get or create the StandaloneManager singleton (double-checked locking)."""
    global _manager
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is not None:
            return _manager
        _manager = StandaloneManager()
        return _manager


def invalidate_standalone_manager() -> None:
    """Stop and reset the StandaloneManager singleton (e.g. after config change)."""
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.stop()
        _manager = None


class StandaloneManager:
    """Orchestrates standalone mode: filesystem watching and directory scanning.

    Owns the MediaFileWatcher (via watcher module) and StandaloneScanner.
    Starts/stops based on standalone_enabled config and watched folder list.
    """

    def __init__(self):
        from standalone.scanner import StandaloneScanner

        self._scanner = StandaloneScanner()
        self._watcher_running = False
        self._socketio = None

    def start(self, socketio=None) -> None:
        """Start standalone mode: watcher + initial scan.

        Args:
            socketio: Optional SocketIO instance for WebSocket events.
        """
        self._socketio = socketio

        try:
            from config import get_settings

            settings = get_settings()

            if not getattr(settings, "standalone_enabled", False):
                logger.info("Standalone mode is disabled")
                return

            from db.standalone import get_watched_folders

            folders = get_watched_folders(enabled_only=True)
            if not folders:
                logger.info("Standalone mode enabled but no watched folders configured")
                return

            folder_paths = [f["path"] for f in folders]
            debounce = getattr(settings, "standalone_debounce_seconds", 10)

            # Start filesystem watcher
            from standalone.watcher import start_watcher

            observer = start_watcher(
                folder_paths,
                on_new_file=self._on_new_file,
                debounce_seconds=float(debounce),
            )
            self._watcher_running = observer is not None

            # Run initial scan in background thread
            thread = threading.Thread(target=self._initial_scan, daemon=True)
            thread.start()

            logger.info("Standalone mode started: watching %d folder(s)", len(folder_paths))

        except Exception as e:
            logger.error("Failed to start standalone mode: %s", e)

    def stop(self) -> None:
        """Stop standalone mode: stop watcher."""
        try:
            from standalone.watcher import stop_watcher

            stop_watcher()
        except Exception as e:
            logger.warning("Error stopping standalone watcher: %s", e)
        self._watcher_running = False
        logger.info("Standalone mode stopped")

    def reload(self) -> None:
        """Reload standalone mode with current config (stop + start)."""
        self.stop()
        self.start(socketio=self._socketio)

    def get_status(self) -> dict:
        """Get current standalone mode status.

        Returns:
            Dict with enabled, watcher_running, folders_count, scanner_scanning.
        """
        enabled = False
        folders_count = 0

        try:
            from config import get_settings

            enabled = getattr(get_settings(), "standalone_enabled", False)
        except Exception:
            pass

        try:
            from db.standalone import get_watched_folders

            folders_count = len(get_watched_folders(enabled_only=True))
        except Exception:
            pass

        return {
            "enabled": enabled,
            "watcher_running": self._watcher_running,
            "folders_count": folders_count,
            "scanner_scanning": self._scanner.is_scanning,
        }

    def _initial_scan(self) -> None:
        """Run an initial full scan of all watched folders (background thread)."""
        try:
            summary = self._scanner.scan_all_folders()
            try:
                from events import emit_event

                emit_event("standalone_scan_complete", summary)
            except Exception:
                pass
            logger.info("Initial standalone scan complete: %s", summary)
        except Exception as e:
            logger.error("Initial standalone scan failed: %s", e)

    def _on_new_file(self, path: str) -> None:
        """Callback for the watcher when a new stable video file is detected.

        Processes the file through the scanner and emits an event.
        """
        try:
            result = self._scanner.process_single_file(path)
            try:
                from events import emit_event

                emit_event(
                    "standalone_file_detected",
                    {
                        "path": path,
                        **result,
                    },
                )
            except Exception:
                pass
            logger.info(
                "Processed new file: %s (type=%s, wanted=%s)",
                path,
                result.get("type"),
                result.get("wanted"),
            )
        except Exception as e:
            logger.error("Error processing new file via watcher: %s", e)
