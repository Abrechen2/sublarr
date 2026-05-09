"""Tests for StandaloneManager service layer."""

import os
from unittest.mock import MagicMock, patch

import pytest


def test_validate_folder_path_requires_path():
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": "", "media_type": "auto"})
    assert error is not None
    assert "path" in error.lower()


def test_validate_folder_input_rejects_invalid_media_type():
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": "/tmp", "media_type": "invalid"})
    assert error is not None
    assert "media_type" in error.lower()


def test_validate_folder_input_accepts_valid():
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": os.getcwd(), "media_type": "tv"})
    assert error is None


def test_validate_folder_input_rejects_nonexistent_path():
    from services.standalone_manager import validate_folder_input

    error = validate_folder_input({"path": "/does/not/exist/ever", "media_type": "auto"})
    assert error is not None
    assert "exist" in error.lower() or "directory" in error.lower()


def test_launch_full_scan_starts_thread(monkeypatch):
    from services.standalone_manager import launch_full_scan

    started = []

    class FakeThread:
        def __init__(self, target, daemon):
            self._target = target
            started.append(self)

        def start(self):
            pass

    monkeypatch.setattr("services.standalone_manager.threading.Thread", FakeThread)
    launch_full_scan(app=MagicMock())
    assert len(started) == 1


def test_launch_folder_scan_returns_404_for_missing_folder(monkeypatch):
    from services.standalone_manager import validate_folder_exists_for_scan

    monkeypatch.setattr("services.standalone_manager.get_watched_folder", lambda fid: None)
    result = validate_folder_exists_for_scan(folder_id=999)
    assert result is None


# ---------------------------------------------------------------------------
# standalone_scan_tick — module-level APScheduler tick (picklable)
# ---------------------------------------------------------------------------


def test_standalone_scan_tick_skips_when_mode_inactive(monkeypatch):
    """Tick is a no-op when is_standalone_mode() returns False."""
    import standalone

    monkeypatch.setattr("config.is_standalone_mode", lambda: False)

    called = {"scan": False}

    class _FakeScanner:
        def scan_all_folders(self):
            called["scan"] = True
            return {}

    # Patch the singleton-getter so the tick picks up our fake. Patching the
    # class directly no longer works because every entry point now calls
    # ``get_scanner()`` (audit S1-3).
    monkeypatch.setattr("standalone.scanner.get_scanner", lambda: _FakeScanner())
    standalone.standalone_scan_tick()
    assert called["scan"] is False


def test_standalone_scan_tick_runs_full_scan_when_active(monkeypatch):
    """Tick delegates to scan_all_folders via the scanner singleton when mode is active."""
    import standalone

    monkeypatch.setattr("config.is_standalone_mode", lambda: True)

    called = {"scan": False, "summary": None}

    class _FakeScanner:
        def scan_all_folders(self):
            called["scan"] = True
            return {"folders_scanned": 1, "wanted_added": 2}

    monkeypatch.setattr("standalone.scanner.get_scanner", lambda: _FakeScanner())
    standalone.standalone_scan_tick()
    assert called["scan"] is True


def test_standalone_scan_tick_swallows_scanner_exceptions(monkeypatch):
    """Scanner failure inside tick must not propagate to APScheduler."""
    import standalone

    monkeypatch.setattr("config.is_standalone_mode", lambda: True)

    class _FailingScanner:
        def scan_all_folders(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("standalone.scanner.get_scanner", lambda: _FailingScanner())
    standalone.standalone_scan_tick()  # must not raise


# ---------------------------------------------------------------------------
# reload_standalone_manager — invalidate + start
# ---------------------------------------------------------------------------


def test_reload_standalone_manager_invalidates_then_starts(monkeypatch):
    """Reload calls invalidate, then start() on a fresh singleton."""
    import standalone

    invalidated = {"v": False}
    started = {"v": False}

    def _fake_invalidate():
        invalidated["v"] = True

    fake_mgr = MagicMock()
    fake_mgr.start = MagicMock(side_effect=lambda **kw: started.update({"v": True}))

    monkeypatch.setattr(standalone, "invalidate_standalone_manager", _fake_invalidate)
    monkeypatch.setattr(standalone, "get_standalone_manager", lambda: fake_mgr)

    standalone.reload_standalone_manager(socketio=None, app=None)

    assert invalidated["v"] is True
    assert started["v"] is True


def test_reload_standalone_manager_swallows_start_failure(monkeypatch):
    """If start() raises, reload still returns cleanly."""
    import standalone

    monkeypatch.setattr(standalone, "invalidate_standalone_manager", lambda: None)

    fake_mgr = MagicMock()
    fake_mgr.start.side_effect = RuntimeError("watchdog boom")
    monkeypatch.setattr(standalone, "get_standalone_manager", lambda: fake_mgr)

    # Must not raise
    standalone.reload_standalone_manager(socketio=None, app=None)


# ---------------------------------------------------------------------------
# update_watched_folder_last_scan — DB wrapper used by scanner end-of-folder
# ---------------------------------------------------------------------------


def test_update_watched_folder_last_scan_calls_repo(monkeypatch):
    """The wrapper delegates to StandaloneRepository.update_last_scan."""
    from db import standalone as db_standalone

    fake_repo = MagicMock()
    monkeypatch.setattr(db_standalone, "_get_repo", lambda: fake_repo)

    db_standalone.update_watched_folder_last_scan(42)

    fake_repo.update_last_scan.assert_called_once_with(42)
