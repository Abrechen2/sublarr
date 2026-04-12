"""Extended tests for services/cleanup_scanner.py — dedup, orphan, rule execution."""

import json
import os
import threading
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# get_scan_state / get_orphan_state edge cases
# ---------------------------------------------------------------------------


def test_get_scan_state_snapshot_is_independent():
    """Mutating returned dict does not affect internal state."""
    from services.cleanup_scanner import get_scan_state

    state = get_scan_state()
    state["running"] = True
    state["scan_id"] = "mutated"
    fresh = get_scan_state()
    assert fresh["running"] is False
    assert fresh["scan_id"] != "mutated"


def test_get_orphan_state_snapshot_is_independent():
    """Mutating returned dict does not affect internal state."""
    from services.cleanup_scanner import get_orphan_state

    state = get_orphan_state()
    state["running"] = True
    fresh = get_orphan_state()
    assert fresh["running"] is False


# ---------------------------------------------------------------------------
# start_dedup_scan
# ---------------------------------------------------------------------------


def test_start_dedup_scan_returns_scan_id(monkeypatch):
    """Non-running state returns new scan_id and already_running=False."""
    from services import cleanup_scanner

    monkeypatch.setattr(
        "services.cleanup_scanner._scan_state",
        {"running": False, "scan_id": None, "progress": 0, "total": 0, "result": None},
    )
    monkeypatch.setattr("services.cleanup_scanner._scan_lock", threading.Lock())

    threads = []

    class FakeThread:
        def __init__(self, target, daemon=False):
            self._target = target
            threads.append(self)

        def start(self):
            pass

    monkeypatch.setattr("services.cleanup_scanner.threading.Thread", FakeThread)

    scan_id, already_running = cleanup_scanner.start_dedup_scan("/media", MagicMock())
    assert already_running is False
    assert scan_id is not None
    assert len(threads) == 1


def test_start_dedup_scan_already_running(monkeypatch):
    """When scan is already running, returns existing scan_id and already_running=True."""
    from services import cleanup_scanner

    monkeypatch.setattr(
        "services.cleanup_scanner._scan_state",
        {
            "running": True,
            "scan_id": "existing-id",
            "progress": 0,
            "total": 0,
            "result": None,
        },
    )
    monkeypatch.setattr("services.cleanup_scanner._scan_lock", threading.Lock())

    scan_id, already_running = cleanup_scanner.start_dedup_scan("/media", MagicMock())
    assert already_running is True
    assert scan_id == "existing-id"


# ---------------------------------------------------------------------------
# run_orphan_scan
# ---------------------------------------------------------------------------


def test_run_orphan_scan_already_running(monkeypatch):
    """Returns error when orphan scan is already running."""
    from services import cleanup_scanner

    monkeypatch.setattr("services.cleanup_scanner._orphan_state", {"running": True, "result": None})
    monkeypatch.setattr("services.cleanup_scanner._orphan_lock", threading.Lock())

    result, error = cleanup_scanner.run_orphan_scan("/media")
    assert result is None
    assert error == "already_running"


def test_run_orphan_scan_error(monkeypatch):
    """Returns error message when scan function raises."""
    from services import cleanup_scanner

    monkeypatch.setattr(
        "services.cleanup_scanner._orphan_state", {"running": False, "result": None}
    )
    monkeypatch.setattr("services.cleanup_scanner._orphan_lock", threading.Lock())
    monkeypatch.setattr(
        "services.cleanup_scanner.scan_orphaned_subtitles",
        MagicMock(side_effect=RuntimeError("scan boom")),
    )

    result, error = cleanup_scanner.run_orphan_scan("/media")
    assert result is None
    assert "scan boom" in error


# ---------------------------------------------------------------------------
# validate_delete_groups
# ---------------------------------------------------------------------------


def test_validate_multiple_groups_all_valid():
    """Multiple valid groups return None."""
    from services.cleanup_scanner import validate_delete_groups

    groups = [
        {"keep": "/a/keep.srt", "delete": ["/a/del1.srt"]},
        {"keep": "/b/keep.srt", "delete": ["/b/del1.srt", "/b/del2.srt"]},
    ]
    assert validate_delete_groups(groups) is None


def test_validate_group_keep_in_delete_list():
    """keep path inside delete list returns error."""
    from services.cleanup_scanner import validate_delete_groups

    groups = [{"keep": "/a/same.srt", "delete": ["/a/same.srt", "/a/other.srt"]}]
    error = validate_delete_groups(groups)
    assert error is not None
    assert "keep path" in error.lower() or "delete" in error.lower()


# ---------------------------------------------------------------------------
# delete_orphan_files
# ---------------------------------------------------------------------------


def test_delete_orphan_files_success(tmp_path):
    """Deletes file inside media_root and returns correct counts."""
    from services.cleanup_scanner import delete_orphan_files

    sub = tmp_path / "orphan.srt"
    sub.write_text("orphaned subtitle")
    media_root = str(tmp_path)

    mock_repo = MagicMock()
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result = delete_orphan_files([str(sub)], media_root)
    assert result["deleted"] == 1
    assert result["bytes_freed"] > 0
    assert len(result["errors"]) == 0
    assert not sub.exists()


def test_delete_orphan_files_outside_media_root(tmp_path):
    """Rejects files outside media_root."""
    from services.cleanup_scanner import delete_orphan_files

    other = tmp_path / "other" / "sub.srt"
    other.parent.mkdir()
    other.write_text("outside")
    media_root = str(tmp_path / "media")
    os.makedirs(media_root)

    mock_repo = MagicMock()
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result = delete_orphan_files([str(other)], media_root)
    assert result["deleted"] == 0
    assert len(result["errors"]) == 1
    assert "Rejected" in result["errors"][0]


def test_delete_orphan_files_not_found(tmp_path):
    """Non-existent file returns error."""
    from services.cleanup_scanner import delete_orphan_files

    media_root = str(tmp_path)
    fake_path = os.path.join(media_root, "missing.srt")

    mock_repo = MagicMock()
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result = delete_orphan_files([fake_path], media_root)
    assert result["deleted"] == 0
    assert any("not found" in e.lower() for e in result["errors"])


def test_delete_orphan_files_logs_cleanup(tmp_path):
    """Cleanup is logged to repository."""
    from services.cleanup_scanner import delete_orphan_files

    sub = tmp_path / "orphan.srt"
    sub.write_text("data")
    media_root = str(tmp_path)

    mock_repo = MagicMock()
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        delete_orphan_files([str(sub)], media_root)
    mock_repo.log_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# execute_rule
# ---------------------------------------------------------------------------


def test_execute_rule_not_found():
    """Returns error when rule does not exist."""
    from services.cleanup_scanner import execute_rule

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = None
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result, error = execute_rule(999, "/media", MagicMock())
    assert result is None
    assert error == "not_found"


def test_execute_rule_dedup():
    """Dedup rule type triggers scan_for_duplicates."""
    from services.cleanup_scanner import execute_rule

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = {"rule_type": "dedup", "name": "Dedup Rule"}
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch("dedup_engine.scan_for_duplicates", return_value={"groups": []}),
    ):
        result, error = execute_rule(1, "/media", MagicMock())
    assert error is None
    assert result["status"] == "completed"
    assert result["rule"] == "Dedup Rule"


def test_execute_rule_orphaned():
    """Orphaned rule type triggers scan_orphaned_subtitles."""
    from services.cleanup_scanner import execute_rule

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = {"rule_type": "orphaned", "name": "Orphan Rule"}
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch("dedup_engine.scan_orphaned_subtitles", return_value=[]),
    ):
        result, error = execute_rule(2, "/media", MagicMock())
    assert error is None
    assert result["count"] == 0


def test_execute_rule_old_backups(tmp_path):
    """old_backups rule type scans for .bak files."""
    from services.cleanup_scanner import execute_rule

    bak = tmp_path / "sub.de.ass.bak"
    bak.write_text("backup")

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = {"rule_type": "old_backups", "name": "Backup Rule"}
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch("dedup_engine.scan_for_duplicates"),
        patch("dedup_engine.scan_orphaned_subtitles"),
    ):
        result, error = execute_rule(3, str(tmp_path), MagicMock())
    assert error is None
    assert result["count"] == 1
    assert result["total_size"] > 0


def test_execute_rule_unknown_type():
    """Unknown rule type returns error."""
    from services.cleanup_scanner import execute_rule

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = {"rule_type": "magic", "name": "Magic Rule"}
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch("dedup_engine.scan_for_duplicates"),
        patch("dedup_engine.scan_orphaned_subtitles"),
    ):
        result, error = execute_rule(4, "/media", MagicMock())
    assert result is None
    assert "unknown_type" in error


# ---------------------------------------------------------------------------
# collect_cleanup_stats
# ---------------------------------------------------------------------------


def test_collect_stats_dict_format(monkeypatch):
    """by_format dict is reshaped to list."""
    from services.cleanup_scanner import collect_cleanup_stats

    monkeypatch.setattr(
        "services.cleanup_scanner.CleanupRepository",
        lambda: MagicMock(
            get_disk_stats=lambda: {
                "total_files": 10,
                "total_size_bytes": 5000,
                "by_format": {"ass": {"count": 5, "size": 3000}, "srt": {"count": 5, "size": 2000}},
                "duplicate_count": 2,
                "duplicate_size_bytes": 500,
                "potential_savings_bytes": 500,
                "recent_cleanups": [],
            }
        ),
    )
    stats = collect_cleanup_stats("/media")
    assert stats["total_files"] == 10
    assert len(stats["by_format"]) == 2
    assert stats["by_format"][0]["format"] in ("ass", "srt")


def test_collect_stats_list_format_passthrough(monkeypatch):
    """by_format already a list is passed through."""
    from services.cleanup_scanner import collect_cleanup_stats

    by_format_list = [{"format": "ass", "count": 3, "size_bytes": 1000}]
    monkeypatch.setattr(
        "services.cleanup_scanner.CleanupRepository",
        lambda: MagicMock(
            get_disk_stats=lambda: {
                "total_files": 3,
                "total_size_bytes": 1000,
                "by_format": by_format_list,
                "duplicate_count": 0,
                "duplicate_size_bytes": 0,
                "potential_savings_bytes": 0,
                "recent_cleanups": [],
            }
        ),
    )
    stats = collect_cleanup_stats("/media")
    assert stats["by_format"] is by_format_list


# ---------------------------------------------------------------------------
# calculate_preview
# ---------------------------------------------------------------------------


def test_preview_invalid_action():
    """Invalid action returns error."""
    from services.cleanup_scanner import calculate_preview

    result, error = calculate_preview("invalid", {}, "/media")
    assert result is None
    assert "action must be one of" in error


def test_preview_dedup():
    """Dedup preview returns affected files."""
    from services.cleanup_scanner import calculate_preview

    mock_repo = MagicMock()
    mock_repo.get_duplicate_groups.return_value = [
        {"files": [{"path": "/a.srt", "size": 100}, {"path": "/b.srt", "size": 50}]}
    ]
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result, error = calculate_preview("dedup", {}, "/media")
    assert error is None
    assert result["action"] == "dedup"
    assert result["groups"] == 1
    # Only the smaller file should be affected (sorted by size desc, [1:])
    assert len(result["affected_files"]) == 1


def test_preview_orphaned():
    """Orphaned preview returns orphaned files."""
    from services.cleanup_scanner import calculate_preview

    mock_repo = MagicMock()
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch(
            "dedup_engine.scan_orphaned_subtitles",
            return_value=[{"path": "/orphan.srt", "size": 200}],
        ),
    ):
        result, error = calculate_preview("orphaned", {}, "/media")
    assert error is None
    assert result["count"] == 1


def test_preview_rule_missing_id():
    """Rule preview without rule_id returns error."""
    from services.cleanup_scanner import calculate_preview

    mock_repo = MagicMock()
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result, error = calculate_preview("rule", {}, "/media")
    assert result is None
    assert "rule_id" in error


def test_preview_rule_not_found():
    """Rule preview with nonexistent rule returns error."""
    from services.cleanup_scanner import calculate_preview

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = None
    with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
        result, error = calculate_preview("rule", {"rule_id": 999}, "/media")
    assert result is None
    assert "not_found" in error


def test_preview_rule_unsupported_type():
    """Rule preview for unsupported type returns message."""
    from services.cleanup_scanner import calculate_preview

    mock_repo = MagicMock()
    mock_repo.get_rule.return_value = {"rule_type": "custom", "name": "Custom"}
    with (
        patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo),
        patch("dedup_engine.scan_orphaned_subtitles"),
    ):
        result, error = calculate_preview("rule", {"rule_id": 1}, "/media")
    assert error is None
    assert "not available" in result.get("message", "").lower()
