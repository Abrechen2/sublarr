"""Regression tests for the 2026-04-30 System Logs / Support Export audit.

Pins:
- /api/v1/logs/support-export — config-snapshot.json now goes through
  ``Settings.get_safe_config()`` instead of a local keyword-only loop.
  Pre-fix the loop tokens were ``{"key", "token", "password", "secret",
  "credential"}`` which missed: ``database_url``, ``redis_url``,
  ``notification_urls_json`` (Apprise tokens carried in URL itself), and
  ``sonarr/radarr/media_servers_json`` JSON blobs (nested ``api_key``).
- _extract_top_errors — error-message strings are anonymized before being
  stored, so a SQLAlchemy ``failed to connect to postgresql://user:pass@…``
  (or any provider error containing an IP/API-key) cannot leak into the
  ``diagnostic-report.md`` / ``db-stats.json`` payloads.
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Config-snapshot drift — must mirror Settings.get_safe_config()
# ---------------------------------------------------------------------------


class TestSupportExportConfigSnapshotMasking:
    """Pre-fix the keyword loop only matched names containing
    ``{key, token, password, secret, credential}``. Several real fields with
    embedded credentials sailed through unredacted."""

    def _read_snapshot(self, client) -> dict:
        resp = client.get("/api/v1/logs/support-export")
        assert resp.status_code == 200, resp.data[:200]
        z = zipfile.ZipFile(io.BytesIO(resp.data))
        return json.loads(z.read("config-snapshot.json"))

    def test_database_url_is_masked(self, client):
        """``database_url`` (DSN like ``postgresql://user:pass@host``) used
        to slip through — no keyword in the field name matched the loop."""
        from config import get_settings, reload_settings

        with patch.dict(
            "os.environ",
            {"SUBLARR_DATABASE_URL": "postgresql://sublarr:hunter2@db:5432/sublarr"},
        ):
            reload_settings()
            try:
                cfg = self._read_snapshot(client)
            finally:
                reload_settings()
        # If the field is in the snapshot at all, must be masked.
        if "database_url" in cfg and cfg["database_url"]:
            assert "hunter2" not in str(cfg["database_url"])
            assert cfg["database_url"] in {"***configured***", ""}
        # Settings should still expose the field name itself
        assert hasattr(get_settings(), "database_url")

    def test_redis_url_is_masked(self, client):
        """``redis_url`` (``redis://default:pass@host``) — same story."""
        from config import reload_settings

        with patch.dict(
            "os.environ",
            {"SUBLARR_REDIS_URL": "redis://default:r3disPass@cache:6379/0"},
        ):
            reload_settings()
            try:
                cfg = self._read_snapshot(client)
            finally:
                reload_settings()
        if "redis_url" in cfg and cfg["redis_url"]:
            assert "r3disPass" not in str(cfg["redis_url"])
            assert cfg["redis_url"] in {"***configured***", ""}

    def test_notification_urls_json_is_masked(self, client):
        """Apprise URLs carry the secret in the URL itself
        (``discord://1234/abcd…``, ``slack://tokA/tokB/tokC``,
        ``tgram://botToken/chatId``). The keyword loop missed all of them."""
        from app import create_app
        from db.config import save_config_entry

        app = create_app(testing=True)
        with app.app_context():
            save_config_entry(
                "notification_urls_json",
                json.dumps(
                    ["discord://1234567890/abcdefSECRETtoken12345", "tgram://botSECRET/chatId"]
                ),
            )
        cfg = self._read_snapshot(client)
        snapshot_urls = cfg.get("notification_urls_json")
        if snapshot_urls:
            assert "abcdefSECRETtoken12345" not in str(snapshot_urls)
            assert "botSECRET" not in str(snapshot_urls)

    def test_sonarr_instances_json_nested_api_keys_masked(self, client):
        """``sonarr_instances_json`` is a list of dicts; each dict has its
        own ``api_key`` field. The pre-fix top-level keyword check ignored
        the nested credentials entirely."""
        from app import create_app
        from db.config import save_config_entry

        app = create_app(testing=True)
        with app.app_context():
            save_config_entry(
                "sonarr_instances_json",
                json.dumps(
                    [
                        {
                            "name": "Main",
                            "url": "http://sonarr:8989",
                            "api_key": "PLAIN_INSTANCE_KEY_abcdef1234",
                        }
                    ]
                ),
            )
        cfg = self._read_snapshot(client)
        blob = cfg.get("sonarr_instances_json")
        if blob:
            # Either the whole blob is replaced, or the nested key is masked.
            assert "PLAIN_INSTANCE_KEY_abcdef1234" not in str(blob)


# ---------------------------------------------------------------------------
# top_errors anonymization
# ---------------------------------------------------------------------------


class TestExtractTopErrorsAnonymizes:
    """Pre-fix the captured error message went into Counter raw and shipped
    into both ``diagnostic-report.md`` and ``db-stats.json`` verbatim."""

    def test_top_errors_anonymizes_public_ip(self, tmp_path, monkeypatch):
        """A public-IP-bearing error message must be redacted before counting.
        Otherwise the support bundle leaks remote-host topology."""
        from datetime import datetime

        log = tmp_path / "sublarr.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write_text(
            f"{ts},123 [ERROR] providers: failed to connect to 85.214.132.17:443\n"
            f"{ts},124 [ERROR] providers: failed to connect to 85.214.132.17:443\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("SUBLARR_LOG_FILE", str(log))

        from config import reload_settings

        reload_settings()
        try:
            from routes.system.support import _extract_top_errors

            errors = _extract_top_errors()
        finally:
            reload_settings()

        assert errors, "expected at least one top error"
        for entry in errors:
            assert "85.214.132.17" not in entry["message"], entry

    def test_top_errors_anonymizes_email(self, tmp_path, monkeypatch):
        from datetime import datetime

        log = tmp_path / "sublarr.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write_text(
            f"{ts},001 [ERROR] auth: invalid login for foo@example.com\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("SUBLARR_LOG_FILE", str(log))

        from config import reload_settings

        reload_settings()
        try:
            from routes.system.support import _extract_top_errors

            errors = _extract_top_errors()
        finally:
            reload_settings()

        assert any("foo@example.com" not in e["message"] for e in errors)
        assert errors  # something was captured
        for entry in errors:
            assert "foo@example.com" not in entry["message"]

    def test_top_errors_anonymizes_api_key_in_message(self, tmp_path, monkeypatch):
        from datetime import datetime

        log = tmp_path / "sublarr.log"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log.write_text(
            f'{ts},001 [ERROR] sonarr: bad api_key="abcdef1234567890ABCDEFXYZ987654321"\n',
            encoding="utf-8",
        )
        monkeypatch.setenv("SUBLARR_LOG_FILE", str(log))

        from config import reload_settings

        reload_settings()
        try:
            from routes.system.support import _extract_top_errors

            errors = _extract_top_errors()
        finally:
            reload_settings()

        assert errors
        for entry in errors:
            assert "abcdef1234567890ABCDEFXYZ987654321" not in entry["message"]
            assert "***REDACTED***" in entry["message"]
