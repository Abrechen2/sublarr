"""HTTP tests for routes/system/backup.py -- database health, backup, restore, full ZIP."""

import io
import json
import os
import sys
import zipfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# GET /api/v1/database/health
# ---------------------------------------------------------------------------


class TestDatabaseHealth:
    """GET /api/v1/database/health"""

    @patch("database_health.get_pool_stats", return_value=None)
    @patch(
        "database_health.get_health_report",
        return_value={
            "status": "healthy",
            "backend": "sqlite",
            "details": {"integrity": "ok"},
        },
    )
    def test_healthy_returns_200(self, mock_report, mock_pool, client):
        rv = client.get("/api/v1/database/health")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["healthy"] is True
        assert data["message"] == "healthy"
        assert data["backend"] == "sqlite"
        assert data["stats"] == {"integrity": "ok"}
        assert "pool" not in data

    @patch(
        "database_health.get_pool_stats",
        return_value={"size": 5, "checked_in": 3, "checked_out": 2},
    )
    @patch(
        "database_health.get_health_report",
        return_value={
            "status": "healthy",
            "backend": "postgresql",
            "details": {},
        },
    )
    def test_healthy_with_pool_stats(self, mock_report, mock_pool, client):
        rv = client.get("/api/v1/database/health")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["healthy"] is True
        assert data["pool"] == {"size": 5, "checked_in": 3, "checked_out": 2}

    @patch("database_health.get_pool_stats", return_value=None)
    @patch(
        "database_health.get_health_report",
        return_value={
            "status": "unhealthy",
            "backend": "sqlite",
            "details": {"error": "integrity check failed"},
        },
    )
    def test_unhealthy_returns_503(self, mock_report, mock_pool, client):
        rv = client.get("/api/v1/database/health")
        assert rv.status_code == 503
        data = rv.get_json()
        assert data["healthy"] is False
        assert data["message"] == "unhealthy"


# ---------------------------------------------------------------------------
# POST /api/v1/database/backup
# ---------------------------------------------------------------------------


class TestCreateBackup:
    """POST /api/v1/database/backup"""

    @patch("database_backup.DatabaseBackup")
    def test_create_backup_default_label(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.create_backup.return_value = {
            "path": "/config/backups/sublarr_daily_20260412.db",
            "size_bytes": 4096,
            "label": "daily",
        }
        mock_instance.rotate.return_value = 0
        mock_backup_class.return_value = mock_instance

        rv = client.post(
            "/api/v1/database/backup",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["label"] == "daily"
        assert data["size_bytes"] == 4096
        mock_instance.create_backup.assert_called_once_with(label="daily")
        mock_instance.rotate.assert_called_once()

    @patch("database_backup.DatabaseBackup")
    def test_create_backup_weekly_label(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.create_backup.return_value = {
            "path": "/config/backups/sublarr_weekly_20260412.db",
            "size_bytes": 4096,
            "label": "weekly",
        }
        mock_instance.rotate.return_value = 0
        mock_backup_class.return_value = mock_instance

        rv = client.post(
            "/api/v1/database/backup",
            json={"label": "weekly"},
            content_type="application/json",
        )
        assert rv.status_code == 201
        data = rv.get_json()
        assert data["label"] == "weekly"
        mock_instance.create_backup.assert_called_once_with(label="weekly")

    @patch("database_backup.DatabaseBackup")
    def test_create_backup_monthly_label(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.create_backup.return_value = {
            "path": "/config/backups/sublarr_monthly_20260412.db",
            "size_bytes": 4096,
            "label": "monthly",
        }
        mock_instance.rotate.return_value = 0
        mock_backup_class.return_value = mock_instance

        rv = client.post(
            "/api/v1/database/backup",
            json={"label": "monthly"},
            content_type="application/json",
        )
        assert rv.status_code == 201
        mock_instance.create_backup.assert_called_once_with(label="monthly")

    @patch("database_backup.DatabaseBackup")
    def test_create_backup_invalid_label_falls_back_to_daily(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.create_backup.return_value = {
            "path": "/config/backups/sublarr_daily_20260412.db",
            "size_bytes": 4096,
            "label": "daily",
        }
        mock_instance.rotate.return_value = 0
        mock_backup_class.return_value = mock_instance

        rv = client.post(
            "/api/v1/database/backup",
            json={"label": "invalid_label"},
            content_type="application/json",
        )
        assert rv.status_code == 201
        mock_instance.create_backup.assert_called_once_with(label="daily")

    @patch("database_backup.DatabaseBackup")
    def test_create_backup_empty_json_body(self, mock_backup_class, client):
        """Empty JSON body defaults to daily label."""
        mock_instance = MagicMock()
        mock_instance.create_backup.return_value = {
            "path": "/tmp/backup.db",
            "size_bytes": 1024,
            "label": "daily",
        }
        mock_instance.rotate.return_value = 0
        mock_backup_class.return_value = mock_instance

        rv = client.post(
            "/api/v1/database/backup",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 201
        mock_instance.create_backup.assert_called_once_with(label="daily")


# ---------------------------------------------------------------------------
# GET /api/v1/database/backups
# ---------------------------------------------------------------------------


class TestListBackups:
    """GET /api/v1/database/backups"""

    @patch("database_backup.DatabaseBackup")
    def test_list_backups_empty(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.list_backups.return_value = []
        mock_backup_class.return_value = mock_instance

        rv = client.get("/api/v1/database/backups")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["backups"] == []

    @patch("database_backup.DatabaseBackup")
    def test_list_backups_returns_entries(self, mock_backup_class, client):
        mock_instance = MagicMock()
        mock_instance.list_backups.return_value = [
            {
                "filename": "sublarr_daily_20260412_030000.db",
                "size_bytes": 4096,
                "label": "daily",
                "timestamp": "20260412_030000",
            },
            {
                "filename": "sublarr_weekly_20260405_030000.db",
                "size_bytes": 8192,
                "label": "weekly",
                "timestamp": "20260405_030000",
            },
        ]
        mock_backup_class.return_value = mock_instance

        rv = client.get("/api/v1/database/backups")
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["backups"]) == 2
        assert data["backups"][0]["filename"] == "sublarr_daily_20260412_030000.db"


# ---------------------------------------------------------------------------
# POST /api/v1/database/restore
# ---------------------------------------------------------------------------


class TestRestoreBackup:
    """POST /api/v1/database/restore"""

    def test_restore_missing_filename(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"confirm": True},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "filename is required"

    def test_restore_empty_filename(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "", "confirm": True},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "filename is required"

    def test_restore_missing_confirm(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "sublarr_daily_20260412.db"},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Add confirm: true to proceed"

    def test_restore_confirm_false(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "sublarr_daily_20260412.db", "confirm": False},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Add confirm: true to proceed"

    def test_restore_path_traversal_dotdot(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "../../etc/passwd", "confirm": True},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Invalid filename"

    def test_restore_path_traversal_slash(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "/etc/passwd", "confirm": True},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Invalid filename"

    def test_restore_path_traversal_backslash(self, client):
        rv = client.post(
            "/api/v1/database/restore",
            json={"filename": "..\\windows\\system32", "confirm": True},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Invalid filename"

    @patch("db.get_db")
    @patch("db.close_db")
    @patch("database_backup.DatabaseBackup")
    def test_restore_success(self, mock_backup_class, mock_close, mock_get_db, client, tmp_path):
        """Successful restore with a valid filename that passes path validation."""
        mock_instance = MagicMock()
        mock_instance.restore_backup.return_value = {
            "restored_from": str(tmp_path / "sublarr_daily_20260412.db"),
            "status": "ok",
        }
        mock_backup_class.return_value = mock_instance

        # Patch get_settings so backup_dir points to tmp_path
        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.db_path = str(tmp_path / "sublarr.db")
            mock_settings.backup_dir = str(tmp_path)
            mock_gs.return_value = mock_settings

            rv = client.post(
                "/api/v1/database/restore",
                json={"filename": "sublarr_daily_20260412.db", "confirm": True},
                content_type="application/json",
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert "restored_from" in data
        mock_close.assert_called_once()
        mock_get_db.assert_called_once()

    def test_restore_empty_json_body(self, client):
        """Empty JSON object triggers 'filename is required' error."""
        rv = client.post(
            "/api/v1/database/restore",
            json={},
            content_type="application/json",
        )
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "filename is required"


# ---------------------------------------------------------------------------
# POST /api/v1/backup/full
# ---------------------------------------------------------------------------


class TestCreateFullBackup:
    """POST /api/v1/backup/full"""

    def test_create_full_backup_success(self, client, tmp_path):
        backup_dir = str(tmp_path / "backups")
        os.makedirs(backup_dir, exist_ok=True)

        # Create a fake DB file so zipfile.ZipFile.write() can read it
        fake_db = str(tmp_path / "sublarr_manual_20260412.db")
        with open(fake_db, "wb") as f:
            f.write(b"fake-sqlite-db")

        mock_backup_instance = MagicMock()
        mock_backup_instance.create_backup.return_value = {
            "path": fake_db,
            "size_bytes": 14,
            "label": "manual",
            "backend": "sqlite",
        }

        with (
            patch("database_backup.DatabaseBackup", return_value=mock_backup_instance),
            patch("config.get_settings") as mock_gs,
        ):
            mock_settings = MagicMock()
            mock_settings.db_path = str(tmp_path / "sublarr.db")
            mock_settings.backup_dir = backup_dir
            mock_settings.backup_retention_daily = 7
            mock_settings.backup_retention_weekly = 4
            mock_settings.backup_retention_monthly = 3
            mock_settings.get_safe_config.return_value = {"log_level": "INFO"}
            mock_gs.return_value = mock_settings

            rv = client.post("/api/v1/backup/full")

        assert rv.status_code == 201
        data = rv.get_json()
        assert data["filename"].startswith("sublarr_full_")
        assert data["filename"].endswith(".zip")
        assert data["size_bytes"] > 0
        assert "created_at" in data
        assert "manifest.json" in data["contents"]
        assert "config.json" in data["contents"]
        assert "sublarr.db" in data["contents"]


# ---------------------------------------------------------------------------
# GET /api/v1/backup/full/download/<filename>
# ---------------------------------------------------------------------------


class TestDownloadFullBackup:
    """GET /api/v1/backup/full/download/<filename>"""

    def test_download_invalid_extension(self, client):
        rv = client.get("/api/v1/backup/full/download/backup.tar.gz")
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Invalid filename"

    def test_download_path_traversal_dotdot_in_filename(self, client):
        """Filename containing '..' is rejected as invalid."""
        rv = client.get("/api/v1/backup/full/download/..backup..evil.zip")
        assert rv.status_code == 400
        data = rv.get_json()
        assert data["error"] == "Invalid filename"

    def test_download_not_found(self, client, tmp_path):
        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = str(tmp_path)
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/download/sublarr_full_20260412_030000.zip")
        assert rv.status_code == 404
        data = rv.get_json()
        assert data["error"] == "Backup file not found"

    def test_download_success(self, client, tmp_path):
        # Create an actual ZIP file on disk
        zip_path = tmp_path / "sublarr_full_20260412_030000.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("manifest.json", "{}")
        assert zip_path.exists()

        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = str(tmp_path)
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/download/sublarr_full_20260412_030000.zip")

        assert rv.status_code == 200
        assert rv.content_type == "application/zip"


# ---------------------------------------------------------------------------
# POST /api/v1/backup/full/restore
# ---------------------------------------------------------------------------


class TestRestoreFullBackup:
    """POST /api/v1/backup/full/restore"""

    def test_restore_full_no_file(self, client):
        rv = client.post("/api/v1/backup/full/restore")
        assert rv.status_code == 400
        data = rv.get_json()
        assert "No file uploaded" in data["error"]

    def test_restore_full_not_a_zip(self, client):
        data = {"file": (io.BytesIO(b"this is not a zip"), "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        resp = rv.get_json()
        assert "not a valid ZIP" in resp["error"]

    def _make_zip(self, manifest=None, config=None, db_content=None, db_name="sublarr.db"):
        """Helper to build an in-memory ZIP archive for testing."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if manifest is not None:
                zf.writestr("manifest.json", json.dumps(manifest))
            if config is not None:
                zf.writestr("config.json", json.dumps(config))
            if db_content is not None:
                zf.writestr(db_name, db_content)
        buf.seek(0)
        return buf

    def test_restore_full_missing_manifest(self, client):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        buf.seek(0)

        data = {"file": (buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        resp = rv.get_json()
        assert "missing manifest.json" in resp["error"]

    def test_restore_full_unsupported_schema_version(self, client):
        zip_buf = self._make_zip(
            manifest={"schema_version": 99, "contents": []},
        )
        data = {"file": (zip_buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        resp = rv.get_json()
        assert "Unsupported schema_version" in resp["error"]

    @patch("config.reload_settings")
    @patch("db.config.get_all_config_entries", return_value={})
    @patch("db.config.save_config_entry")
    def test_restore_full_config_only(self, mock_save, mock_get_all, mock_reload, client):
        """Restore a ZIP with config.json but no DB -- only config is imported."""
        zip_buf = self._make_zip(
            manifest={
                "schema_version": 1,
                "contents": ["manifest.json", "config.json"],
                "version": "0.50.0-beta",
                "created_at": "2026-04-12T00:00:00",
                "db_backend": "sqlite",
            },
            config={"log_level": "DEBUG", "scan_interval": "60"},
        )
        data = {"file": (zip_buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 200
        resp = rv.get_json()
        assert resp["status"] == "restored"
        assert resp["db_restored"] is False

    @patch("config.reload_settings")
    @patch("db.config.get_all_config_entries", return_value={})
    @patch("db.config.save_config_entry")
    def test_restore_full_skips_secrets(self, mock_save, mock_get_all, mock_reload, client):
        """Secret keys and masked values must be skipped during config import."""
        zip_buf = self._make_zip(
            manifest={
                "schema_version": 1,
                "contents": ["manifest.json", "config.json"],
                "version": "0.50.0-beta",
                "created_at": "2026-04-12T00:00:00",
                "db_backend": "sqlite",
            },
            config={
                "api_key": "super_secret_123",
                "sonarr_api_key": "secret_sonarr",
                "log_level": "DEBUG",
                "jimaku_api_key": "secret_jimaku",
                "some_field": "***configured***",
            },
        )
        data = {"file": (zip_buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 200
        resp = rv.get_json()
        assert resp["status"] == "restored"
        imported = resp["config_imported"]
        # Secret keys must NOT appear in imported list
        assert "api_key" not in imported
        assert "sonarr_api_key" not in imported
        assert "jimaku_api_key" not in imported
        # Masked values must be skipped
        assert "some_field" not in imported

    @patch("config.reload_settings")
    @patch("db.config.get_all_config_entries", return_value={})
    @patch("db.config.save_config_entry")
    @patch("db.get_db")
    @patch("db.close_db")
    @patch("database_backup.DatabaseBackup")
    def test_restore_full_with_db(
        self,
        mock_backup_class,
        mock_close_db,
        mock_get_db,
        mock_save,
        mock_get_all,
        mock_reload,
        client,
    ):
        """Restore a ZIP with both config and DB -- DB restore is called."""
        mock_instance = MagicMock()
        mock_instance.restore_backup.return_value = {
            "restored_from": "/tmp/some.db",
            "backend": "sqlite",
        }
        mock_backup_class.return_value = mock_instance

        zip_buf = self._make_zip(
            manifest={
                "schema_version": 1,
                "contents": ["manifest.json", "config.json", "sublarr.db"],
                "version": "0.50.0-beta",
                "created_at": "2026-04-12T00:00:00",
                "db_backend": "sqlite",
            },
            config={"log_level": "DEBUG"},
            db_content=b"fake-sqlite-db-bytes",
        )
        data = {"file": (zip_buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 200
        resp = rv.get_json()
        assert resp["status"] == "restored"
        assert resp["db_restored"] is True
        mock_close_db.assert_called_once()
        mock_get_db.assert_called_once()
        mock_instance.restore_backup.assert_called_once()

    def test_restore_full_invalid_json_in_manifest(self, client):
        """ZIP with corrupt manifest.json returns 400."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", "{invalid json!!!")
        buf.seek(0)

        data = {"file": (buf, "backup.zip")}
        rv = client.post(
            "/api/v1/backup/full/restore",
            data=data,
            content_type="multipart/form-data",
        )
        assert rv.status_code == 400
        resp = rv.get_json()
        assert "Invalid backup file" in resp["error"]


# ---------------------------------------------------------------------------
# GET /api/v1/backup/full/list
# ---------------------------------------------------------------------------


class TestListFullBackups:
    """GET /api/v1/backup/full/list"""

    def test_list_full_backups_no_dir(self, client, tmp_path):
        nonexistent = str(tmp_path / "nonexistent")
        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = nonexistent
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/list")
        assert rv.status_code == 200
        data = rv.get_json()
        assert data["backups"] == []

    def test_list_full_backups_filters_and_parses(self, client, tmp_path):
        """Only .zip files are listed; timestamps are parsed from filename."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        # Create ZIP files
        for name in [
            "sublarr_full_20260412_030000.zip",
            "sublarr_full_20260411_030000.zip",
            "not_a_backup.txt",
        ]:
            (backup_dir / name).write_bytes(b"x" * 100)

        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = str(backup_dir)
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/list")

        assert rv.status_code == 200
        data = rv.get_json()
        # Only .zip files should be listed (not_a_backup.txt excluded)
        filenames = [b["filename"] for b in data["backups"]]
        assert "not_a_backup.txt" not in filenames
        assert len(data["backups"]) == 2
        # Timestamps should be parsed
        for backup in data["backups"]:
            assert backup["created_at"] != ""
            assert backup["size_bytes"] > 0

    def test_list_full_backups_invalid_timestamp(self, client, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "sublarr_full_INVALID.zip").write_bytes(b"x" * 50)

        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = str(backup_dir)
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/list")

        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data["backups"]) == 1
        # Invalid timestamp means created_at is empty
        assert data["backups"][0]["created_at"] == ""

    def test_list_full_backups_empty_dir(self, client, tmp_path):
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        with patch("config.get_settings") as mock_gs:
            mock_settings = MagicMock()
            mock_settings.backup_dir = str(backup_dir)
            mock_gs.return_value = mock_settings

            rv = client.get("/api/v1/backup/full/list")

        assert rv.status_code == 200
        data = rv.get_json()
        assert data["backups"] == []
