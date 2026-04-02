"""Tests for StandaloneManager service layer."""

import os
import pytest
from unittest.mock import MagicMock, patch


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
