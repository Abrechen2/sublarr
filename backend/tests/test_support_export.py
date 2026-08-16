"""Tests for support export anonymization and diagnostic builder."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTopErrorsLineParsing:
    """The top-errors list groups by message, so the message must be exact.

    `_msg_re` skipped the bracketed id slot with `[^:]+`, which holds as long as
    that slot contains no colon — true for a request id and for the `-`
    placeholder. The scheduler run label added in 1.12.1 is `job_id:hex`, and
    against that the capture started mid-id: every line came back as
    `<hex>] <logger>: <message>`. Two harms, not one — the 80-char budget lost a
    third of itself to a prefix, and since the hex differs per run, repeated
    occurrences of one error stopped aggregating and the list degenerated into
    one row per run. Precisely the errors worth counting are the scheduler's.
    """

    def _extract(self, tmp_path, monkeypatch, lines):
        import app_logging
        from routes.system.support import _extract_top_errors

        log = tmp_path / "sublarr.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setattr(app_logging, "rotated_log_candidates", lambda: [str(log)])
        return _extract_top_errors()

    def _line(self, slot, message):
        import datetime as dt

        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{stamp},123 [ERROR] {slot} wanted_search.process: {message}"

    def test_a_run_label_does_not_bleed_into_the_message(self, tmp_path, monkeypatch):
        errors = self._extract(
            tmp_path, monkeypatch, [self._line("[wanted_search:a1b2c3d4]", "provider timed out")]
        )

        assert [e["message"] for e in errors] == ["provider timed out"]

    def test_two_runs_of_one_job_aggregate_into_one_row(self, tmp_path, monkeypatch):
        errors = self._extract(
            tmp_path,
            monkeypatch,
            [
                self._line("[wanted_search:a1b2c3d4]", "provider timed out"),
                self._line("[wanted_search:99887766]", "provider timed out"),
            ],
        )

        assert len(errors) == 1
        assert errors[0]["count"] == 2

    def test_the_placeholder_slot_still_parses(self, tmp_path, monkeypatch):
        errors = self._extract(tmp_path, monkeypatch, [self._line("[-]", "provider timed out")])

        assert [e["message"] for e in errors] == ["provider timed out"]

    def test_a_line_predating_the_id_slot_still_parses(self, tmp_path, monkeypatch):
        import datetime as dt

        stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        errors = self._extract(
            tmp_path,
            monkeypatch,
            [f"{stamp},123 [ERROR] wanted_search.process: provider timed out"],
        )

        assert [e["message"] for e in errors] == ["provider timed out"]


class TestAnonymize:
    """Test the _anonymize() helper function."""

    def _fn(self, *args, **kwargs):
        from routes.system import _anonymize

        return _anonymize(*args, **kwargs)

    def test_private_ip_192_168(self):
        assert self._fn("Connected to 192.168.178.194") == "Connected to 192.168.xxx.xxx"

    def test_private_ip_10_x(self):
        assert self._fn("Host: 10.0.0.1") == "Host: 10.0.xxx.xxx"

    def test_private_ip_172_16(self):
        assert self._fn("Addr: 172.16.5.20") == "Addr: 172.16.xxx.xxx"

    def test_public_ip_fully_redacted(self):
        assert self._fn("Remote: 85.214.132.17") == "Remote: xxx.xxx.xxx.xxx"

    def test_localhost_preserved(self):
        line = "Listening on 127.0.0.1:5765"
        assert self._fn(line) == line

    def test_api_key_redacted(self):
        line = 'api_key: "3bdcc724abcdef1234567890abcdef12"'
        result = self._fn(line)
        assert "3bdcc724" not in result
        assert "***REDACTED***" in result

    def test_path_keeps_filename_only(self):
        line = "Subtitle for /media/Anime/86 Eighty Six/S01E01.mkv"
        result = self._fn(line)
        assert "86 Eighty Six" not in result
        assert "S01E01.mkv" in result

    def test_email_redacted(self):
        line = "User: somebody@example.com logged in"
        result = self._fn(line)
        assert "***USER***" in result
        assert "somebody@example.com" not in result

    def test_hostname_parameter_redacted(self):
        """Pass hostname explicitly — simulates what export time does."""
        result = self._fn("Request from my-server", hostname="my-server")
        assert "***HOST***" in result
        assert "my-server" not in result

    def test_unix_home_path_shortened(self):
        line = "Config at /home/dennis/sublarr/config.db"
        result = self._fn(line)
        assert "/home/dennis" not in result
        assert "~/sublarr/config.db" in result

    def test_root_path_shortened(self):
        line = "Config at /root/.bashrc"
        result = self._fn(line)
        assert "/root" not in result
        assert "~/.bashrc" in result


class TestBuildDiagnostic:
    """Test the _build_diagnostic() shared helper."""

    def _call(self):
        from routes.system import _build_diagnostic

        return _build_diagnostic()

    def test_returns_version(self):
        result = self._call()
        assert "version" in result
        assert isinstance(result["version"], str)

    def test_wanted_counts_present(self):
        result = self._call()
        # Either wanted dict exists, or db_stats_error is set — both are valid
        assert "wanted" in result or result.get("db_stats_error") == "unavailable"

    def test_translations_present(self):
        result = self._call()
        assert "translations" in result or result.get("db_stats_error") == "unavailable"

    def test_top_errors_is_list(self):
        result = self._call()
        assert isinstance(result.get("top_errors", []), list)

    def test_provider_status_is_list(self):
        result = self._call()
        assert isinstance(result.get("provider_status", []), list)
        for p in result.get("provider_status", []):
            assert "name" in p
            assert "active" in p

    def test_memory_mb_present(self):
        result = self._call()
        assert "memory_mb" in result  # may be None if psutil absent

    def test_db_error_handled_gracefully(self):
        from unittest.mock import MagicMock, patch

        from routes.system import _build_diagnostic

        # Simulate DB failure by patching get_db so it raises
        with patch("db.get_db", side_effect=Exception("locked")):
            result = _build_diagnostic()
        assert "db_stats_error" in result


class TestSupportPreviewEndpoint:
    """Test GET /api/v1/logs/support-preview."""

    @pytest.fixture
    def client(self, temp_db):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def _headers(self):
        from config import get_settings

        return {"X-Api-Key": get_settings().api_key or ""}

    def test_returns_200(self, client):
        resp = client.get("/api/v1/logs/support-preview", headers=self._headers())
        assert resp.status_code == 200

    def test_response_shape(self, client):
        data = client.get("/api/v1/logs/support-preview", headers=self._headers()).get_json()
        assert "diagnostic" in data
        assert "redaction_summary" in data

    def test_redaction_summary_fields(self, client):
        rs = client.get("/api/v1/logs/support-preview", headers=self._headers()).get_json()[
            "redaction_summary"
        ]
        for key in (
            "log_files_found",
            "ips_redacted",
            "api_keys_redacted",
            "paths_redacted",
            "example_path_before",
            "example_ip_before",
        ):
            assert key in rs


class TestSupportExportEndpoint:
    """Test GET /api/v1/logs/support-export."""

    @pytest.fixture
    def client(self, temp_db):
        from app import create_app

        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    def _headers(self):
        from config import get_settings

        return {"X-Api-Key": get_settings().api_key or ""}

    def test_returns_zip(self, client):
        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        assert resp.status_code == 200
        assert "application/zip" in resp.content_type

    def test_zip_contains_required_files(self, client):
        import io
        import zipfile

        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        z = zipfile.ZipFile(io.BytesIO(resp.data))
        names = z.namelist()
        assert "diagnostic-report.md" in names
        assert "db-stats.json" in names
        assert "config-snapshot.json" in names
        assert "system-info.txt" in names

    def test_config_snapshot_redacts_api_key(self, client):
        import io
        import json
        import zipfile

        resp = client.get("/api/v1/logs/support-export", headers=self._headers())
        z = zipfile.ZipFile(io.BytesIO(resp.data))
        cfg = json.loads(z.read("config-snapshot.json"))
        # api_key field must be redacted — the snapshot now delegates to
        # Settings.get_safe_config() which uses the ``***configured***``
        # marker (was ``***REDACTED***`` before audit 2026-04-30).
        if cfg.get("api_key"):
            assert cfg["api_key"] == "***configured***"
