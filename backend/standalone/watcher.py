"""Filesystem watcher for media directories using watchdog.

Monitors configured watched folders for new/moved video files.
Uses debounce (default 10s) and file stability check to handle
incomplete copies and rapid filesystem events.
"""

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from watchdog.events import PatternMatchingEventHandler
    from watchdog.observers import Observer

    _WATCHDOG_AVAILABLE = True
except ImportError:
    _WATCHDOG_AVAILABLE = False
    Observer = None  # type: ignore[assignment,misc]
    PatternMatchingEventHandler = object  # type: ignore[assignment,misc]


# Video file patterns for watchdog matching (glob-style)
VIDEO_PATTERNS = [
    "*.mkv", "*.mp4", "*.avi", "*.m4v", "*.wmv", "*.flv", "*.webm", "*.ts",
]


class MediaFileWatcher(PatternMatchingEventHandler):
    """Watches media directories for new/moved video files with debounce.

    Uses a per-path threading.Timer to coalesce rapid filesystem events
    and a file stability check (size comparison after 2s) to avoid
    processing incomplete copies.

    Args:
        on_new_file: Callback receiving the absolute path of a new stable video file.
        debounce_seconds: Seconds to wait after the last event for a path before processing.
    """

    def __init__(self, on_new_file: Callable[[str], None],
                 debounce_seconds: float = 10.0):
        if _WATCHDOG_AVAILABLE:
            super().__init__(
                patterns=VIDEO_PATTERNS,
                ignore_directories=True,
                case_sensitive=False,
            )
        self.on_new_file = on_new_file
        self.debounce_seconds = debounce_seconds
        self._pending: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event) -> None:
        """Handle file creation events."""
        self._schedule_process(event.src_path)

    def on_moved(self, event) -> None:
        """Handle file move/rename events (use destination path)."""
        self._schedule_process(event.dest_path)

    def _schedule_process(self, path: str) -> None:
        """Schedule debounced processing for a file path.

        Cancels any existing timer for the same path and starts a new one.
        """
        with self._lock:
            existing_timer = self._pending.get(path)
            if existing_timer is not None:
                existing_timer.cancel()

            timer = threading.Timer(
                self.debounce_seconds,
                self._check_and_process,
                args=(path,),
            )
            timer.daemon = True
            self._pending[path] = timer
            timer.start()

    def _check_and_process(self, path: str) -> None:
        """Check file stability and invoke callback if stable.

        Gets file size, waits 2 seconds, checks again. If sizes differ
        the file is still being written -- reschedule. If stable and
        the file exists, invoke the on_new_file callback.
        """
        # Remove from pending
        with self._lock:
            self._pending.pop(path, None)

        try:
            if not os.path.exists(path):
                return

            size_1 = os.path.getsize(path)
            time.sleep(2)

            if not os.path.exists(path):
                return

            size_2 = os.path.getsize(path)

            if size_1 != size_2:
                # File still being written -- reschedule
                logger.debug("File still changing, rescheduling: %s", path)
                self._schedule_process(path)
                return

            logger.info("Detected new media file: %s", path)
            self.on_new_file(path)

        except Exception as e:
            logger.error("Error processing new file %s: %s", path, e)


# ---------------------------------------------------------------------------
# Module-level singleton observer
# ---------------------------------------------------------------------------

_observer: Optional["Observer"] = None  # type: ignore[assignment]


def start_watcher(folders: list[str], on_new_file: Callable[[str], None],
                  debounce_seconds: float = 10.0):
    """Start the filesystem watcher on the given folders.

    Creates a watchdog Observer, schedules a MediaFileWatcher handler
    for each folder (recursive), and starts the observer thread.

    Args:
        folders: List of absolute directory paths to watch.
        on_new_file: Callback for newly detected stable video files.
        debounce_seconds: Debounce interval in seconds.

    Returns:
        The started Observer instance, or None if watchdog is unavailable
        or no valid folders are provided.
    """
    global _observer

    if not _WATCHDOG_AVAILABLE:
        logger.warning(
            "watchdog package not installed -- filesystem watcher disabled. "
            "Install with: pip install watchdog"
        )
        return None

    if not folders:
        logger.info("No folders to watch")
        return None

    handler = MediaFileWatcher(on_new_file, debounce_seconds=debounce_seconds)
    observer = Observer()
    observer.daemon = True

    watched_count = 0
    for folder in folders:
        if os.path.isdir(folder):
            observer.schedule(handler, path=folder, recursive=True)
            watched_count += 1
            logger.debug("Watching folder: %s", folder)
        else:
            logger.warning("Skipping non-existent folder: %s", folder)

    if watched_count == 0:
        logger.warning("No valid folders to watch")
        return None

    observer.start()
    _observer = observer
    logger.info("Filesystem watcher started on %d folder(s)", watched_count)
    return observer


def stop_watcher() -> None:
    """Stop the running filesystem observer if any."""
    global _observer
    if _observer is not None:
        try:
            _observer.stop()
            _observer.join(timeout=5)
            logger.info("Filesystem watcher stopped")
        except Exception as e:
            logger.warning("Error stopping filesystem watcher: %s", e)
        finally:
            _observer = None


def restart_watcher(folders: list[str], on_new_file: Callable[[str], None],
                    debounce_seconds: float = 10.0):
    """Restart the filesystem watcher with new configuration.

    Stops any running observer, then starts a new one.

    Args:
        folders: List of absolute directory paths to watch.
        on_new_file: Callback for newly detected stable video files.
        debounce_seconds: Debounce interval in seconds.

    Returns:
        The new Observer instance, or None.
    """
    stop_watcher()
    return start_watcher(folders, on_new_file, debounce_seconds)
