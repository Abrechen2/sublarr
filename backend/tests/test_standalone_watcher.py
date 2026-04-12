"""Tests for standalone/watcher.py — filesystem watcher with debounce."""

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# VIDEO_PATTERNS
# ---------------------------------------------------------------------------


def test_video_patterns_includes_common_formats():
    from standalone.watcher import VIDEO_PATTERNS

    expected = ["*.mkv", "*.mp4", "*.avi"]
    for pat in expected:
        assert pat in VIDEO_PATTERNS


# ---------------------------------------------------------------------------
# MediaFileWatcher.__init__
# ---------------------------------------------------------------------------


def test_media_file_watcher_init():
    """MediaFileWatcher initialises with callback and debounce."""
    from standalone.watcher import MediaFileWatcher

    callback = MagicMock()
    watcher = MediaFileWatcher(callback, debounce_seconds=5.0)
    assert watcher.on_new_file is callback
    assert watcher.debounce_seconds == 5.0
    assert watcher._pending == {}


def test_media_file_watcher_default_debounce():
    """Default debounce is 10 seconds."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock())
    assert watcher.debounce_seconds == 10.0


# ---------------------------------------------------------------------------
# on_created / on_moved
# ---------------------------------------------------------------------------


def test_on_created_schedules_process():
    """on_created calls _schedule_process with src_path."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock())
    watcher._schedule_process = MagicMock()

    event = MagicMock()
    event.src_path = "/media/video.mkv"
    watcher.on_created(event)
    watcher._schedule_process.assert_called_once_with("/media/video.mkv")


def test_on_moved_schedules_process():
    """on_moved calls _schedule_process with dest_path."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock())
    watcher._schedule_process = MagicMock()

    event = MagicMock()
    event.dest_path = "/media/renamed.mkv"
    watcher.on_moved(event)
    watcher._schedule_process.assert_called_once_with("/media/renamed.mkv")


# ---------------------------------------------------------------------------
# _schedule_process
# ---------------------------------------------------------------------------


def test_schedule_process_creates_timer():
    """_schedule_process creates a Timer for new paths."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock(), debounce_seconds=1.0)

    with patch("standalone.watcher.threading.Timer") as MockTimer:
        mock_timer_instance = MagicMock()
        MockTimer.return_value = mock_timer_instance
        watcher._schedule_process("/media/video.mkv")

    MockTimer.assert_called_once()
    mock_timer_instance.start.assert_called_once()
    assert "/media/video.mkv" in watcher._pending


def test_schedule_process_cancels_existing_timer():
    """Re-scheduling the same path cancels the previous timer."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock(), debounce_seconds=1.0)

    first_timer = MagicMock()
    watcher._pending["/media/video.mkv"] = first_timer

    with patch("standalone.watcher.threading.Timer") as MockTimer:
        MockTimer.return_value = MagicMock()
        watcher._schedule_process("/media/video.mkv")

    first_timer.cancel.assert_called_once()


# ---------------------------------------------------------------------------
# _check_and_process
# ---------------------------------------------------------------------------


def test_check_and_process_stable_file(tmp_path):
    """Stable file triggers callback."""
    from standalone.watcher import MediaFileWatcher

    callback = MagicMock()
    watcher = MediaFileWatcher(callback, debounce_seconds=0)

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 1000)
    path = str(video)

    # Mock time.sleep to avoid actual wait, and mock getsize to return same size
    with patch("standalone.watcher.time.sleep"):
        watcher._check_and_process(path)

    callback.assert_called_once_with(path)


def test_check_and_process_file_gone(tmp_path):
    """Non-existent file is silently skipped."""
    from standalone.watcher import MediaFileWatcher

    callback = MagicMock()
    watcher = MediaFileWatcher(callback, debounce_seconds=0)

    watcher._check_and_process("/nonexistent/video.mkv")
    callback.assert_not_called()


def test_check_and_process_file_still_changing(tmp_path):
    """File with changing size is rescheduled."""
    from standalone.watcher import MediaFileWatcher

    callback = MagicMock()
    watcher = MediaFileWatcher(callback, debounce_seconds=0)
    watcher._schedule_process = MagicMock()

    video = tmp_path / "video.mkv"
    video.write_bytes(b"\x00" * 1000)
    path = str(video)

    sizes = iter([1000, 2000])
    with (
        patch("standalone.watcher.time.sleep"),
        patch("standalone.watcher.os.path.getsize", side_effect=sizes),
        patch("standalone.watcher.os.path.exists", return_value=True),
    ):
        watcher._check_and_process(path)

    callback.assert_not_called()
    watcher._schedule_process.assert_called_once_with(path)


def test_check_and_process_removes_from_pending():
    """Path is removed from _pending when processing starts."""
    from standalone.watcher import MediaFileWatcher

    watcher = MediaFileWatcher(MagicMock(), debounce_seconds=0)
    watcher._pending["/media/video.mkv"] = MagicMock()

    with patch("standalone.watcher.os.path.exists", return_value=False):
        watcher._check_and_process("/media/video.mkv")

    assert "/media/video.mkv" not in watcher._pending


def test_check_and_process_exception_handled():
    """Exceptions in processing are caught and logged."""
    from standalone.watcher import MediaFileWatcher

    callback = MagicMock()
    watcher = MediaFileWatcher(callback, debounce_seconds=0)

    with patch("standalone.watcher.os.path.exists", side_effect=PermissionError("denied")):
        # Should not raise
        watcher._check_and_process("/media/video.mkv")

    callback.assert_not_called()


# ---------------------------------------------------------------------------
# start_watcher
# ---------------------------------------------------------------------------


def test_start_watcher_no_watchdog(monkeypatch):
    """Returns None when watchdog is not available."""
    import standalone.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", False)
    result = watcher_mod.start_watcher(["/media"], MagicMock())
    assert result is None


def test_start_watcher_empty_folders(monkeypatch):
    """Returns None with empty folder list."""
    import standalone.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", True)
    result = watcher_mod.start_watcher([], MagicMock())
    assert result is None


def test_start_watcher_no_valid_folders(monkeypatch):
    """Returns None when all folders are nonexistent."""
    import standalone.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", True)

    mock_observer = MagicMock()
    monkeypatch.setattr(watcher_mod, "Observer", lambda: mock_observer)

    result = watcher_mod.start_watcher(["/nonexistent/folder"], MagicMock())
    assert result is None


def test_start_watcher_success(tmp_path, monkeypatch):
    """Starts observer with valid folders."""
    import standalone.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", True)

    mock_observer = MagicMock()
    monkeypatch.setattr(watcher_mod, "Observer", lambda: mock_observer)

    result = watcher_mod.start_watcher([str(tmp_path)], MagicMock())
    assert result is mock_observer
    mock_observer.start.assert_called_once()
    mock_observer.schedule.assert_called_once()


# ---------------------------------------------------------------------------
# stop_watcher
# ---------------------------------------------------------------------------


def test_stop_watcher_with_observer(monkeypatch):
    """Stops and joins the observer."""
    import standalone.watcher as watcher_mod

    mock_observer = MagicMock()
    monkeypatch.setattr(watcher_mod, "_observer", mock_observer)

    watcher_mod.stop_watcher()
    mock_observer.stop.assert_called_once()
    mock_observer.join.assert_called_once_with(timeout=5)
    assert watcher_mod._observer is None


def test_stop_watcher_no_observer(monkeypatch):
    """Stopping when no observer is running is a no-op."""
    import standalone.watcher as watcher_mod

    monkeypatch.setattr(watcher_mod, "_observer", None)
    watcher_mod.stop_watcher()  # Should not raise


def test_stop_watcher_exception_handled(monkeypatch):
    """Exception during stop is caught."""
    import standalone.watcher as watcher_mod

    mock_observer = MagicMock()
    mock_observer.stop.side_effect = RuntimeError("stop failed")
    monkeypatch.setattr(watcher_mod, "_observer", mock_observer)

    watcher_mod.stop_watcher()  # Should not raise
    assert watcher_mod._observer is None


# ---------------------------------------------------------------------------
# restart_watcher
# ---------------------------------------------------------------------------


def test_restart_watcher(tmp_path, monkeypatch):
    """Restart stops existing and starts new observer."""
    import standalone.watcher as watcher_mod

    old_observer = MagicMock()
    monkeypatch.setattr(watcher_mod, "_observer", old_observer)
    monkeypatch.setattr(watcher_mod, "_WATCHDOG_AVAILABLE", True)

    new_observer = MagicMock()
    monkeypatch.setattr(watcher_mod, "Observer", lambda: new_observer)

    result = watcher_mod.restart_watcher([str(tmp_path)], MagicMock())
    old_observer.stop.assert_called_once()
    assert result is new_observer
