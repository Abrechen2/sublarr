"""Tests for encryption master-key handling in full ZIP backups.

The master key lives outside the DB at ``{SUBLARR_CONFIG_DIR}/.encryption_key``
(see ``config_crypto``). Full backups already bundle ``config.json``, which now
contains ``enc:v1:`` ciphertext for secrets — without the key file in the
backup, a restore would leave those values permanently undecryptable.
"""

import io
import json
import os
import sys
import zipfile
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config_crypto


@pytest.fixture(autouse=True)
def _reset_crypto_cache():
    """Isolate the module-level cipher cache from other tests in the suite."""
    config_crypto.reset_cipher_cache()
    yield
    config_crypto.reset_cipher_cache()


def _make_manifest(contents):
    return {
        "version": "1.5.0",
        "created_at": "2026-07-03T00:00:00",
        "schema_version": 1,
        "contents": contents,
        "db_backend": "sqlite",
    }


def _make_zip(manifest, config=None, key_bytes=None):
    """Build an in-memory full-backup ZIP with an optional .encryption_key member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        if config is not None:
            zf.writestr("config.json", json.dumps(config))
        if key_bytes is not None:
            zf.writestr(".encryption_key", key_bytes)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# POST /api/v1/backup/full — creation must bundle the master key
# ---------------------------------------------------------------------------


class TestBackupIncludesMasterKey:
    def test_backup_zip_contains_master_key(self, client, tmp_path, monkeypatch):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(config_dir))
        config_crypto.reset_cipher_cache()
        config_crypto.encrypt("force-key-creation")  # ensures .encryption_key exists

        key_path = config_dir / ".encryption_key"
        assert key_path.exists()
        expected_key_bytes = key_path.read_bytes()

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        fake_db = tmp_path / "sublarr_manual.db"
        fake_db.write_bytes(b"fake-sqlite-db")

        mock_backup_instance = MagicMock()
        mock_backup_instance.create_backup.return_value = {
            "path": str(fake_db),
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
            mock_settings.backup_dir = str(backup_dir)
            mock_settings.backup_retention_daily = 7
            mock_settings.backup_retention_weekly = 4
            mock_settings.backup_retention_monthly = 3
            mock_settings.get_safe_config.return_value = {"log_level": "INFO"}
            mock_gs.return_value = mock_settings

            rv = client.post("/api/v1/backup/full")

        assert rv.status_code == 201
        data = rv.get_json()
        zip_path = os.path.join(str(backup_dir), data["filename"])

        with zipfile.ZipFile(zip_path) as zf:
            assert ".encryption_key" in zf.namelist()
            assert zf.read(".encryption_key") == expected_key_bytes


# ---------------------------------------------------------------------------
# POST /api/v1/backup/full/restore — restore must put the key file back
# ---------------------------------------------------------------------------


class TestRestoreWritesMasterKey:
    @patch("config.reload_settings")
    @patch("db.config.get_all_config_entries", return_value={})
    @patch("db.config.save_config_entry")
    def test_restore_writes_key_file_and_resets_cipher(
        self, mock_save, mock_get_all, mock_reload, client, tmp_path, monkeypatch
    ):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(config_dir))

        # Prime the cipher cache with an ORIGINAL key so the test can prove the
        # restore actually rebuilds the cache, not just the file on disk.
        config_crypto.reset_cipher_cache()
        config_crypto.encrypt("prime-original-key")
        assert (config_dir / ".encryption_key").exists()

        # A different key ships inside the backup ZIP.
        new_key = Fernet.generate_key()
        expected_plaintext = "restored-secret-value"
        expected_ciphertext = config_crypto._PREFIX + Fernet(new_key).encrypt(
            expected_plaintext.encode("utf-8")
        ).decode("ascii")

        zip_buf = _make_zip(
            manifest=_make_manifest(["manifest.json", "config.json"]),
            config={"log_level": "DEBUG"},
            key_bytes=new_key,
        )

        rv = client.post(
            "/api/v1/backup/full/restore",
            data={"file": (zip_buf, "backup.zip")},
            content_type="multipart/form-data",
        )

        assert rv.status_code == 200
        assert rv.get_json()["status"] == "restored"

        key_path = config_dir / ".encryption_key"
        assert key_path.read_bytes() == new_key

        # Cache-reset proof: decrypting a value made with the NEW key only
        # succeeds if the cached Fernet cipher was rebuilt from the freshly
        # restored key file (a stale cached cipher would raise InvalidToken).
        assert config_crypto.decrypt(expected_ciphertext) == expected_plaintext

    @patch("config.reload_settings")
    @patch("db.config.get_all_config_entries", return_value={})
    @patch("db.config.save_config_entry")
    def test_restore_without_key_file_leaves_existing_key_untouched(
        self, mock_save, mock_get_all, mock_reload, client, tmp_path, monkeypatch
    ):
        """Restoring an OLD backup (no .encryption_key member) must not crash
        and must leave whatever key is already on disk untouched."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        monkeypatch.setenv("SUBLARR_CONFIG_DIR", str(config_dir))

        config_crypto.reset_cipher_cache()
        config_crypto.encrypt("keep-me")
        key_path = config_dir / ".encryption_key"
        original_bytes = key_path.read_bytes()

        zip_buf = _make_zip(
            manifest=_make_manifest(["manifest.json", "config.json"]),
            config={"log_level": "DEBUG"},
            key_bytes=None,
        )

        rv = client.post(
            "/api/v1/backup/full/restore",
            data={"file": (zip_buf, "backup.zip")},
            content_type="multipart/form-data",
        )

        assert rv.status_code == 200
        assert key_path.read_bytes() == original_bytes
