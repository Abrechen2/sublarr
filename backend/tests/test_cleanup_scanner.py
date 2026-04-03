"""Tests for CleanupScanner service layer."""

import threading
from unittest.mock import MagicMock, patch


def test_get_scan_state_initial():
    from services.cleanup_scanner import get_scan_state

    state = get_scan_state()
    assert state["running"] is False
    assert state["scan_id"] is None
    assert state["result"] is None


def test_get_orphan_state_initial():
    from services.cleanup_scanner import get_orphan_state

    state = get_orphan_state()
    assert state["running"] is False
    assert state["result"] is None


def test_validate_delete_groups_requires_keep():
    from services.cleanup_scanner import validate_delete_groups

    groups = [{"keep": "", "delete": ["/a/b.srt"]}]
    error = validate_delete_groups(groups)
    assert error is not None
    assert "keep" in error.lower()


def test_validate_delete_groups_requires_delete_list():
    from services.cleanup_scanner import validate_delete_groups

    groups = [{"keep": "/a/keep.srt", "delete": []}]
    error = validate_delete_groups(groups)
    assert error is not None
    assert "delete" in error.lower()


def test_validate_delete_groups_keep_not_in_delete():
    from services.cleanup_scanner import validate_delete_groups

    groups = [{"keep": "/a/file.srt", "delete": ["/a/file.srt"]}]
    error = validate_delete_groups(groups)
    assert error is not None


def test_validate_delete_groups_ok():
    from services.cleanup_scanner import validate_delete_groups

    groups = [{"keep": "/a/file.srt", "delete": ["/a/other.srt"]}]
    error = validate_delete_groups(groups)
    assert error is None


def test_run_orphan_scan_sets_state(monkeypatch):
    from services import cleanup_scanner

    monkeypatch.setattr(
        "services.cleanup_scanner._orphan_state", {"running": False, "result": None}
    )
    monkeypatch.setattr("services.cleanup_scanner._orphan_lock", threading.Lock())
    mock_result = [{"file_path": "/a/orphan.srt"}]
    monkeypatch.setattr(
        "services.cleanup_scanner.scan_orphaned_subtitles",
        lambda path: mock_result,
    )
    result, error = cleanup_scanner.run_orphan_scan("/media")
    assert error is None
    assert result == mock_result


def test_collect_stats_returns_dict(monkeypatch, tmp_path):
    from services.cleanup_scanner import collect_cleanup_stats

    monkeypatch.setattr(
        "services.cleanup_scanner.CleanupRepository",
        lambda: MagicMock(
            get_disk_stats=lambda: {
                "total_files": 5,
                "total_size_bytes": 1000,
                "by_format": [],
                "duplicate_files": 1,
                "duplicate_size_bytes": 200,
                "potential_savings_bytes": 200,
                "trends": [],
            }
        ),
    )
    stats = collect_cleanup_stats(str(tmp_path))
    assert "total_files" in stats
    assert "total_size_bytes" in stats
