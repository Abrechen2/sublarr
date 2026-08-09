"""Tests for routes/cleanup.py -- dedup scan, orphan detection, rules, stats, history."""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _reset_scan_state():
    import routes.cleanup as cleanup_mod

    cleanup_mod._scan_state["running"] = False
    cleanup_mod._scan_state["scan_id"] = None
    cleanup_mod._scan_state["progress"] = 0
    cleanup_mod._scan_state["total"] = 0
    cleanup_mod._scan_state["result"] = None


def _reset_orphan_state():
    import routes.cleanup as cleanup_mod

    cleanup_mod._orphan_state["running"] = False
    cleanup_mod._orphan_state["result"] = None


# ---- TestScanStatus ------------------------------------------------------------


class TestScanStatus:
    """GET /api/v1/cleanup/scan/status"""

    def setup_method(self):
        _reset_scan_state()

    def test_scan_status_idle(self, client):
        """Returns running=False when no scan is active."""
        rv = client.get("/api/v1/cleanup/scan/status")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["running"] is False
        assert data["scan_id"] is None
        assert data["result"] is None

    def test_scan_status_while_running(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = True
        cleanup_mod._scan_state["scan_id"] = "test-scan-123"

        rv = client.get("/api/v1/cleanup/scan/status")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["running"] is True
        assert data["scan_id"] == "test-scan-123"

    def test_scan_status_with_result(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = False
        cleanup_mod._scan_state["scan_id"] = "done-scan-456"
        cleanup_mod._scan_state["result"] = {"groups": [], "total_files": 0}

        rv = client.get("/api/v1/cleanup/scan/status")
        data = rv.get_json()
        assert data["result"]["total_files"] == 0
        assert data["scan_id"] == "done-scan-456"


# ---- TestStartScan -------------------------------------------------------------


class TestStartScan:
    """POST /api/v1/cleanup/scan"""

    def setup_method(self):
        _reset_scan_state()

    def test_start_scan_returns_scanning_status(self, client):
        """Starts scan, returns status=scanning and a scan_id."""
        mock_socketio = MagicMock()
        with (
            patch(
                "dedup_engine.scan_for_duplicates", return_value={"groups": [], "total_files": 0}
            ),
            patch("extensions.socketio", mock_socketio),
        ):
            rv = client.post("/api/v1/cleanup/scan")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "scanning"
        assert "scan_id" in data
        assert len(data["scan_id"]) > 0

    def test_start_scan_409_when_already_running(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._scan_state["running"] = True
        cleanup_mod._scan_state["scan_id"] = "existing-scan"

        rv = client.post("/api/v1/cleanup/scan")
        assert rv.status_code == 409
        data = rv.get_json()
        assert data["status"] == "already_running"
        assert data["scan_id"] == "existing-scan"

    def test_start_scan_sets_running_state(self, client):
        """After triggering scan, state should reflect a running scan."""
        import routes.cleanup as cleanup_mod

        mock_socketio = MagicMock()
        # Block thread from completing by making scan_for_duplicates block
        import threading

        barrier = threading.Barrier(2)

        def slow_scan(*args, **kwargs):
            barrier.wait(timeout=5)
            return {"groups": [], "total_files": 0}

        with (
            patch("dedup_engine.scan_for_duplicates", side_effect=slow_scan),
            patch("extensions.socketio", mock_socketio),
        ):
            rv = client.post("/api/v1/cleanup/scan")
            # State should be "running" immediately after response
            assert cleanup_mod._scan_state["running"] is True
            barrier.wait(timeout=5)  # release the background thread

        assert rv.status_code == 200


# ---- TestGetDuplicates ---------------------------------------------------------


class TestGetDuplicates:
    """GET /api/v1/cleanup/duplicates"""

    def test_get_duplicates_empty(self, client):
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["groups"] == []
        assert data["total"] == 0

    def test_get_duplicates_with_groups(self, client):
        fake_groups = [
            {"hash": "abc123", "files": ["/media/a.srt", "/media/b.srt"]},
            {"hash": "def456", "files": ["/media/c.srt", "/media/d.srt"]},
        ]
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = fake_groups

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates")

        data = rv.get_json()
        assert data["total"] == 2
        assert len(data["groups"]) == 2

    def test_get_duplicates_pagination(self, client):
        fake_groups = [{"hash": f"hash{i}", "files": [f"/a{i}.srt"]} for i in range(10)]
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = fake_groups

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates?page=2&per_page=3")

        data = rv.get_json()
        assert data["total"] == 10
        assert data["page"] == 2
        assert data["per_page"] == 3
        assert len(data["groups"]) == 3

    def test_get_duplicates_per_page_capped_at_200(self, client):
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates?per_page=9999")

        data = rv.get_json()
        assert data["per_page"] == 200

    def test_get_duplicates_default_page_is_1(self, client):
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/duplicates")

        data = rv.get_json()
        assert data["page"] == 1


# ---- TestDeleteDuplicates ------------------------------------------------------


class TestDeleteDuplicates:
    """POST /api/v1/cleanup/duplicates/delete"""

    def test_delete_duplicates_requires_groups(self, client):
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "groups" in data["error"]

    def test_delete_duplicates_requires_keep_path(self, client):
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": [{"delete": ["/media/b.srt"]}]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "keep" in data["error"]

    def test_delete_duplicates_requires_delete_list(self, client):
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": [{"keep": "/media/a.srt", "delete": []}]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "delete" in data["error"]

    def test_delete_duplicates_rejects_keep_in_delete(self, client):
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": [{"keep": "/media/a.srt", "delete": ["/media/a.srt", "/media/b.srt"]}]},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "keep" in data["error"].lower() or "delete" in data["error"].lower()

    def test_delete_duplicates_success(self, client):
        mock_result = {"deleted": 1, "bytes_freed": 1024}
        with patch("dedup_engine.delete_duplicates", return_value=mock_result):
            rv = client.post(
                "/api/v1/cleanup/duplicates/delete",
                json={"groups": [{"keep": "/media/a.srt", "delete": ["/media/b.srt"]}]},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["total_deleted"] == 1
        assert data["total_bytes_freed"] == 1024

    def test_delete_duplicates_multiple_groups(self, client):
        mock_result = {"deleted": 1, "bytes_freed": 512}
        with patch("dedup_engine.delete_duplicates", return_value=mock_result):
            rv = client.post(
                "/api/v1/cleanup/duplicates/delete",
                json={
                    "groups": [
                        {"keep": "/media/a.srt", "delete": ["/media/b.srt"]},
                        {"keep": "/media/c.srt", "delete": ["/media/d.srt"]},
                    ]
                },
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["total_deleted"] == 2
        assert data["total_bytes_freed"] == 1024
        assert len(data["results"]) == 2

    def test_delete_duplicates_empty_groups_list(self, client):
        """Empty groups array returns 400."""
        rv = client.post(
            "/api/v1/cleanup/duplicates/delete",
            json={"groups": []},
            content_type="application/json",
        )
        assert rv.status_code == 400


# ---- TestOrphanedScan ----------------------------------------------------------


class TestOrphanedScan:
    """POST /api/v1/cleanup/orphaned/scan"""

    def setup_method(self):
        _reset_orphan_state()

    def test_scan_orphaned_success(self, client):
        fake_orphans = [
            {"path": "/media/orphan.srt", "size": 1024},
        ]
        with patch("dedup_engine.scan_orphaned_subtitles", return_value=fake_orphans):
            rv = client.post("/api/v1/cleanup/orphaned/scan")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 1
        assert len(data["orphaned"]) == 1

    def test_scan_orphaned_empty_result(self, client):
        with patch("dedup_engine.scan_orphaned_subtitles", return_value=[]):
            rv = client.post("/api/v1/cleanup/orphaned/scan")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 0
        assert data["orphaned"] == []

    def test_scan_orphaned_409_when_already_running(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._orphan_state["running"] = True

        rv = client.post("/api/v1/cleanup/orphaned/scan")
        assert rv.status_code == 409
        data = rv.get_json()
        assert data["status"] == "already_running"

    def test_scan_orphaned_handles_error(self, client):
        with patch("dedup_engine.scan_orphaned_subtitles", side_effect=RuntimeError("scan failed")):
            rv = client.post("/api/v1/cleanup/orphaned/scan")

        assert rv.status_code == 500
        data = rv.get_json()
        assert "error" in data

    def test_scan_orphaned_resets_running_state_on_error(self, client):
        import routes.cleanup as cleanup_mod

        with patch("dedup_engine.scan_orphaned_subtitles", side_effect=RuntimeError("boom")):
            client.post("/api/v1/cleanup/orphaned/scan")

        assert cleanup_mod._orphan_state["running"] is False


# ---- TestGetOrphaned -----------------------------------------------------------


class TestGetOrphaned:
    """GET /api/v1/cleanup/orphaned"""

    def setup_method(self):
        _reset_orphan_state()

    def test_get_orphaned_no_scan_yet(self, client):
        rv = client.get("/api/v1/cleanup/orphaned")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["orphaned"] == []
        assert data["count"] == 0
        assert "message" in data

    def test_get_orphaned_with_results(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._orphan_state["result"] = [
            {"path": "/media/orphan.srt", "size": 512},
        ]

        rv = client.get("/api/v1/cleanup/orphaned")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["count"] == 1
        assert len(data["orphaned"]) == 1

    def test_get_orphaned_empty_result_set(self, client):
        import routes.cleanup as cleanup_mod

        cleanup_mod._orphan_state["result"] = []

        rv = client.get("/api/v1/cleanup/orphaned")
        data = rv.get_json()
        assert data["count"] == 0
        assert data["orphaned"] == []


# ---- TestDeleteOrphaned --------------------------------------------------------


class TestDeleteOrphaned:
    """POST /api/v1/cleanup/orphaned/delete"""

    def test_delete_orphaned_requires_file_paths(self, client):
        rv = client.post(
            "/api/v1/cleanup/orphaned/delete",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert "file_paths" in data["error"]

    def test_delete_orphaned_empty_paths_list(self, client):
        rv = client.post(
            "/api/v1/cleanup/orphaned/delete",
            json={"file_paths": []},
            content_type="application/json",
        )
        assert rv.status_code == 400

    def test_delete_orphaned_rejects_outside_media_dir(self, client, tmp_path):
        """Files outside the media root should be rejected, not deleted."""
        # tmp_path is a real path; SUBLARR_MEDIA_PATH is tempfile.gettempdir()
        # Create a fake file outside the media path: use a completely separate path
        outside_path = "/etc/passwd"

        rv = client.post(
            "/api/v1/cleanup/orphaned/delete",
            json={"file_paths": [outside_path]},
            content_type="application/json",
        )

        assert rv.status_code == 200
        data = rv.get_json()
        # The file should be rejected (added to errors), not deleted
        assert data["deleted"] == 0
        assert len(data["errors"]) > 0

    def test_delete_orphaned_file_not_found(self, client, tmp_path):
        """Non-existent files inside media dir should produce an error entry."""
        import tempfile

        media_root = os.path.realpath(tempfile.gettempdir())
        nonexistent = os.path.join(media_root, "does_not_exist_xyz.srt")

        rv = client.post(
            "/api/v1/cleanup/orphaned/delete",
            json={"file_paths": [nonexistent]},
            content_type="application/json",
        )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["deleted"] == 0
        assert any("not found" in e.lower() for e in data["errors"])

    def test_delete_orphaned_success(self, client, tmp_path):
        """Files inside the media dir that exist should be deleted successfully."""
        import tempfile

        media_root = os.path.realpath(tempfile.gettempdir())
        # Create a real temp file inside the media root
        target = os.path.join(media_root, "orphan_test_delete.srt")
        with open(target, "w") as f:
            f.write("dummy subtitle content")

        try:
            rv = client.post(
                "/api/v1/cleanup/orphaned/delete",
                json={"file_paths": [target]},
                content_type="application/json",
            )

            assert rv.status_code == 200
            data = rv.get_json()
            assert data["deleted"] == 1
            assert data["bytes_freed"] > 0
            assert data["errors"] == []
            assert not os.path.exists(target)
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_delete_orphaned_logs_to_history(self, client, tmp_path):
        """CleanupRepository.log_cleanup is called after deletion attempt."""
        import tempfile

        media_root = os.path.realpath(tempfile.gettempdir())
        nonexistent = os.path.join(media_root, "no_such_file_xyz.srt")

        mock_repo = MagicMock()
        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            client.post(
                "/api/v1/cleanup/orphaned/delete",
                json={"file_paths": [nonexistent]},
                content_type="application/json",
            )

        mock_repo.log_cleanup.assert_called_once()


# ---- TestCleanupStats ----------------------------------------------------------


class TestCleanupStats:
    """GET /api/v1/cleanup/stats"""

    def test_stats_success(self, client):
        mock_disk_stats = {
            "total_files": 42,
            "total_size_bytes": 1_000_000,
            "by_format": {
                "srt": {"count": 30, "size": 600_000},
                "ass": {"count": 12, "size": 400_000},
            },
            "duplicate_count": 5,
            "duplicate_size_bytes": 50_000,
            "potential_savings_bytes": 40_000,
            "recent_cleanups": [],
        }
        mock_repo = MagicMock()
        mock_repo.get_disk_stats.return_value = mock_disk_stats

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/stats")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["total_files"] == 42
        assert data["total_size_bytes"] == 1_000_000
        assert isinstance(data["by_format"], list)
        assert data["duplicate_files"] == 5
        assert data["potential_savings_bytes"] == 40_000

    def test_stats_by_format_is_array(self, client):
        """by_format is reshaped from dict to list."""
        mock_disk_stats = {
            "total_files": 0,
            "total_size_bytes": 0,
            "by_format": {"srt": {"count": 5, "size": 100}},
            "duplicate_count": 0,
            "duplicate_size_bytes": 0,
            "potential_savings_bytes": 0,
            "recent_cleanups": [],
        }
        mock_repo = MagicMock()
        mock_repo.get_disk_stats.return_value = mock_disk_stats

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/stats")

        data = rv.get_json()
        assert isinstance(data["by_format"], list)
        assert data["by_format"][0]["format"] == "srt"
        assert data["by_format"][0]["count"] == 5
        assert data["by_format"][0]["size_bytes"] == 100

    def test_stats_cleanup_trends_bucket_sqlite_datetime(self, client):
        """Cleanup history trend buckets SQLite datetimes without DATE result processing."""
        from db.models.cleanup import CleanupHistory
        from extensions import db

        performed_at = datetime.now(UTC).replace(hour=12, minute=30, second=0, microsecond=0)
        expected_day = performed_at.strftime("%Y-%m-%d")
        with client.application.app_context():
            db.session.add(
                CleanupHistory(
                    action_type="test_cleanup",
                    files_processed=1,
                    files_deleted=1,
                    bytes_freed=1234,
                    details_json="{}",
                    performed_at=performed_at,
                )
            )
            db.session.commit()

        rv = client.get("/api/v1/cleanup/stats")

        assert rv.status_code == 200
        data = rv.get_json()
        assert {"date": expected_day, "bytes_freed": 1234} in data["trends"]

    def test_stats_handles_repo_error(self, client):
        mock_repo = MagicMock()
        mock_repo.get_disk_stats.side_effect = RuntimeError("DB error")

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/stats")

        assert rv.status_code == 500
        data = rv.get_json()
        assert "error" in data


# ---- TestCleanupHistory --------------------------------------------------------


class TestCleanupHistory:
    """GET /api/v1/cleanup/history"""

    def test_history_success(self, client):
        mock_history = {
            "items": [],
            "total": 0,
            "page": 1,
            "per_page": 50,
        }
        mock_repo = MagicMock()
        mock_repo.get_history.return_value = mock_history

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/history")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_history_pagination_args_forwarded(self, client):
        mock_repo = MagicMock()
        mock_repo.get_history.return_value = {"items": [], "total": 0, "page": 3, "per_page": 10}

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/history?page=3&per_page=10")

        assert rv.status_code == 200
        mock_repo.get_history.assert_called_once_with(3, 10)


# ---- TestCleanupRules ----------------------------------------------------------


class TestCleanupRules:
    """GET/POST/PUT/DELETE /api/v1/cleanup/rules"""

    def test_list_rules_empty(self, client):
        mock_repo = MagicMock()
        mock_repo.get_rules.return_value = []

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.get("/api/v1/cleanup/rules")

        assert rv.status_code == 200
        assert rv.get_json()["rules"] == []

    def test_create_rule_success(self, client):
        mock_repo = MagicMock()
        mock_repo.create_rule.return_value = {
            "id": 1,
            "name": "My Rule",
            "rule_type": "dedup",
            "enabled": True,
        }

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.post(
                "/api/v1/cleanup/rules",
                json={"name": "My Rule", "rule_type": "dedup"},
                content_type="application/json",
            )

        assert rv.status_code == 201
        data = rv.get_json()
        assert data["id"] == 1

    def test_create_rule_requires_name(self, client):
        rv = client.post(
            "/api/v1/cleanup/rules",
            json={"rule_type": "dedup"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "name" in rv.get_json()["error"]

    def test_create_rule_invalid_type(self, client):
        rv = client.post(
            "/api/v1/cleanup/rules",
            json={"name": "Bad Rule", "rule_type": "unknown_type"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "rule_type" in rv.get_json()["error"]

    def test_create_rule_invalid_config_json(self, client):
        rv = client.post(
            "/api/v1/cleanup/rules",
            json={"name": "Bad Rule", "rule_type": "dedup", "config_json": "not-json{{{"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "config_json" in rv.get_json()["error"]

    def test_update_rule_success(self, client):
        mock_repo = MagicMock()
        mock_repo.update_rule.return_value = {
            "id": 1,
            "name": "Updated",
            "rule_type": "dedup",
            "enabled": False,
        }

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.put(
                "/api/v1/cleanup/rules/1",
                json={"name": "Updated", "enabled": False},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["name"] == "Updated"

    def test_update_rule_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.update_rule.return_value = None

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.put(
                "/api/v1/cleanup/rules/999",
                json={"name": "Ghost"},
                content_type="application/json",
            )

        assert rv.status_code == 404

    def test_delete_rule_success(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_rule.return_value = True

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.delete("/api/v1/cleanup/rules/1")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["status"] == "deleted"
        assert data["id"] == 1

    def test_delete_rule_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.delete_rule.return_value = False

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.delete("/api/v1/cleanup/rules/999")

        assert rv.status_code == 404


# ---- TestPreviewCleanup --------------------------------------------------------


class TestPreviewCleanup:
    """POST /api/v1/cleanup/preview"""

    def test_preview_invalid_action(self, client):
        rv = client.post(
            "/api/v1/cleanup/preview",
            json={"action": "nonexistent"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "action" in rv.get_json()["error"]

    def test_preview_dedup_action(self, client):
        fake_groups = [
            {
                "hash": "abc",
                "files": [
                    {"path": "/media/a.srt", "size": 200},
                    {"path": "/media/b.srt", "size": 100},
                ],
            }
        ]
        mock_repo = MagicMock()
        mock_repo.get_duplicate_groups.return_value = fake_groups

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.post(
                "/api/v1/cleanup/preview",
                json={"action": "dedup"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["action"] == "dedup"
        assert "affected_files" in data
        assert "total_size" in data

    def test_preview_orphaned_action(self, client):
        fake_orphans = [{"path": "/media/orphan.srt", "size": 512}]
        with patch("dedup_engine.scan_orphaned_subtitles", return_value=fake_orphans):
            rv = client.post(
                "/api/v1/cleanup/preview",
                json={"action": "orphaned"},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["action"] == "orphaned"
        assert data["count"] == 1

    def test_preview_rule_requires_rule_id(self, client):
        rv = client.post(
            "/api/v1/cleanup/preview",
            json={"action": "rule", "params": {}},
            content_type="application/json",
        )
        assert rv.status_code == 400
        assert "rule_id" in rv.get_json()["error"]

    def test_preview_rule_not_found(self, client):
        mock_repo = MagicMock()
        mock_repo.get_rule.return_value = None

        with patch("db.repositories.cleanup.CleanupRepository", return_value=mock_repo):
            rv = client.post(
                "/api/v1/cleanup/preview",
                json={"action": "rule", "params": {"rule_id": 999}},
                content_type="application/json",
            )

        assert rv.status_code == 404

    def test_preview_missing_action(self, client):
        rv = client.post(
            "/api/v1/cleanup/preview",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400


# ---- TestNonTargetSubs ---------------------------------------------------------


class TestNonTargetSubs:
    """POST /api/v1/cleanup/non-target-subs"""

    def test_body_media_path_override_is_ignored(self, client, tmp_path, monkeypatch):
        """Regression: the route used to honour ``data.get("media_path")`` as
        an override for settings.media_path with no security gate. A caller
        with an API key could walk arbitrary directories and trash sidecars
        outside the configured library. The override is now stripped — only
        the configured settings.media_path is walked."""
        import os

        # Settings media_path points to one tmpdir; the body asks for another.
        configured = tmp_path / "configured_media"
        configured.mkdir()
        attacker_target = tmp_path / "should_not_walk_here"
        attacker_target.mkdir()
        monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(configured))
        from config import reload_settings

        reload_settings()
        try:
            # Sentinel: a stray .mkv under attacker_target. If the override
            # were honoured, the route would walk it (scanned_files > 0).
            (attacker_target / "victim.mkv").write_bytes(b"\x00")

            rv = client.post(
                "/api/v1/cleanup/non-target-subs",
                json={"dry_run": True, "media_path": str(attacker_target)},
                content_type="application/json",
            )
            # The route either returns 200 with scanned_files=0 (configured
            # media is empty) or 400 if no profiles exist. Either way it must
            # NOT have walked attacker_target.
            if rv.status_code == 200:
                body = rv.get_json()
                # Walking attacker_target would have produced scanned_files >= 1
                # because of the sentinel .mkv file we wrote there.
                assert body["scanned_files"] == 0, (
                    "Body media_path override is still being honoured — "
                    "this is the regression we just fixed."
                )
            else:
                # No profiles → 400 / 500. Either way, the override path was
                # never walked: make sure nothing got moved.
                assert (attacker_target / "victim.mkv").exists()
        finally:
            os.environ.pop("SUBLARR_MEDIA_PATH", None)
            reload_settings()
