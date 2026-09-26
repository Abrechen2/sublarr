"""Support bundle 1.15.0-rc.2 fixes: streaming + cap, rate limit, preview cache,
proxy auth, JSON-format parsing, hostname redaction, and the new sections."""

from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fresh_preview_cache():
    import routes.system.support as support

    # getattr: this file also runs against pre-fix code as a positive control.
    reset = getattr(support, "_reset_preview_cache", lambda: None)
    reset()
    yield
    reset()


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    """Point the app at a log file we control (rotation depth 1)."""
    from config import reload_settings

    path = tmp_path / "sublarr.log"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("SUBLARR_LOG_FILE", str(path))
    reload_settings()
    return path


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _zip(resp) -> zipfile.ZipFile:
    assert resp.status_code == 200, resp.data[:300]
    return zipfile.ZipFile(io.BytesIO(resp.data))


# ─── C1 in the bundle ────────────────────────────────────────────────────────


class TestExportedLogsAreRedacted:
    def test_secret_shapes_in_old_log_lines_do_not_survive(self, client, log_file):
        # Lines written before 1.15.0-rc.2 were never scrubbed at write time.
        log_file.write_text(
            f"{_stamp()},1 [ERROR] [-] db: connect postgresql://sublarr:S3cretPw@db:5432/x\n"
            f"{_stamp()},2 [ERROR] [-] auth: password=hunter2pass rejected\n"
            f"{_stamp()},3 [INFO] [-] notify: POST /api/webhooks/1234567/WebhookTok-9 ok\n",
            encoding="utf-8",
        )
        z = _zip(client.get("/api/v1/logs/support-export"))
        text = z.read("logs/sublarr.log").decode("utf-8")

        for secret in ("S3cretPw", "hunter2pass", "WebhookTok-9"):
            assert secret not in text


# ─── I3: streaming, cap, rate limit, preview cache ───────────────────────────


class TestLogPayloadCap:
    def test_plan_keeps_the_newest_bytes_and_says_so(self, tmp_path):
        from routes.system.support_logs import payload_summary, plan_log_payload

        newest = tmp_path / "a.log"
        older = tmp_path / "a.log.1"
        newest.write_bytes(b"x" * 600)
        older.write_bytes(b"y" * 600)

        plan = plan_log_payload([str(newest), str(older)], cap=1000)
        summary = payload_summary(plan)

        assert plan["files"][0] == {"path": str(newest), "start": 0, "size": 600}
        assert plan["files"][1]["start"] == 200  # only the newest 400 bytes of the older file
        assert summary["truncated"] is True
        assert summary["included_bytes"] == 1000
        assert summary["partial_files"] == ["a.log.1"]

    def test_files_beyond_the_cap_are_listed_as_skipped(self, tmp_path):
        from routes.system.support_logs import plan_log_payload

        files = []
        for i in range(3):
            p = tmp_path / f"b{i}.log"
            p.write_bytes(b"z" * 500)
            files.append(str(p))

        plan = plan_log_payload(files, cap=500)
        assert [f["path"] for f in plan["files"]] == [files[0]]
        assert plan["skipped_files"] == ["b1.log", "b2.log"]

    def test_truncated_export_notes_it_in_the_report(self, client, log_file, monkeypatch):
        import routes.system.support_logs as support_logs

        line = f"{_stamp()},1 [INFO] [-] x: " + "a" * 100 + "\n"
        log_file.write_text(line * 200, encoding="utf-8")
        monkeypatch.setattr(support_logs, "LOG_PAYLOAD_CAP_BYTES", 5_000)

        z = _zip(client.get("/api/v1/logs/support-export"))

        assert "Truncated" in z.read("diagnostic-report.md").decode("utf-8")
        exported = z.read("logs/sublarr.log").decode("utf-8")
        assert len(exported) <= 5_000
        # The cut starts on a line boundary.
        assert exported.startswith(line[:10])


class TestRateLimit:
    def test_seventh_export_in_a_minute_is_refused(self, client, log_file):
        codes = [client.get("/api/v1/logs/support-export").status_code for _ in range(7)]
        assert codes[:6] == [200] * 6
        assert codes[6] == 429

    def test_seventh_preview_in_a_minute_is_refused(self, client, log_file):
        codes = [client.get("/api/v1/logs/support-preview").status_code for _ in range(7)]
        assert codes[6] == 429


class TestPreviewCache:
    def test_second_open_is_served_from_cache(self, client, log_file):
        import routes.system.support as support

        with patch.object(support, "_build_preview", wraps=support._build_preview) as build:
            first = client.get("/api/v1/logs/support-preview").get_json()
            second = client.get("/api/v1/logs/support-preview").get_json()

        assert build.call_count == 1
        assert first["cached"] is False
        assert second["cached"] is True


# ─── I4: reverse-proxy auth ───────────────────────────────────────────────────


class TestProxyAuth:
    def test_sso_user_without_api_key_can_export(self, client, log_file, monkeypatch):
        from config import reload_settings

        monkeypatch.setenv("SUBLARR_API_KEY", "configured-key-123")
        reload_settings()
        with patch("proxy_auth.request_has_valid_proxy_auth", return_value=True):
            resp = client.get("/api/v1/logs/support-export")
        assert resp.status_code == 200, resp.data[:200]

    def test_no_credentials_still_refused(self, client, log_file, monkeypatch):
        from config import reload_settings

        monkeypatch.setenv("SUBLARR_API_KEY", "configured-key-123")
        reload_settings()
        resp = client.get("/api/v1/logs/support-export")
        assert resp.status_code == 401


# ─── I1: JSON log format ──────────────────────────────────────────────────────


def _json_line(level: str, message: str) -> str:
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ",123"
    return json.dumps(
        {"timestamp": stamp, "level": level, "logger": "providers.jimaku", "message": message}
    )


class TestJsonFormatLogs:
    def test_top_errors_understand_json_lines(self, tmp_path, monkeypatch):
        import app_logging
        from routes.system.support import _extract_top_errors

        log = tmp_path / "sublarr.log"
        log.write_text(
            "\n".join(
                [
                    _json_line("ERROR", "provider timed out"),
                    _json_line("ERROR", "provider timed out"),
                    _json_line("INFO", "all good"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(app_logging, "rotated_log_candidates", lambda: [str(log)])

        errors = _extract_top_errors()

        assert errors == [
            {"message": "provider timed out", "count": 2, "last_seen": errors[0]["last_seen"]}
        ]

    def test_recent_warnings_keep_json_and_text_warnings_with_traceback(self, tmp_path):
        from routes.system.support_logs import recent_warnings

        log = tmp_path / "sublarr.log"
        log.write_text(
            f"{_stamp()},1 [INFO] [-] a: fine\n"
            f"{_stamp()},2 [ERROR] [-] a: broke\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1\n'
            f"{_stamp()},3 [INFO] [-] a: fine again\n" + _json_line("WARNING", "json warn") + "\n",
            encoding="utf-8",
        )

        lines = recent_warnings([str(log)], hostname=None)

        joined = "".join(lines)
        assert "broke" in joined
        assert "Traceback" in joined
        assert "json warn" in joined
        assert "fine" not in joined

    def test_recent_warnings_are_capped(self, tmp_path, monkeypatch):
        import routes.system.support_logs as support_logs

        monkeypatch.setattr(support_logs, "RECENT_WARNINGS_MAX", 3)
        log = tmp_path / "sublarr.log"
        log.write_text(
            "".join(f"{_stamp()},1 [WARNING] [-] a: w{i}\n" for i in range(10)), encoding="utf-8"
        )

        lines = support_logs.recent_warnings([str(log)], hostname=None)

        assert [ln.strip().rsplit(" ", 1)[-1] for ln in lines] == ["w7", "w8", "w9"]


# ─── N3: hostname redaction ───────────────────────────────────────────────────


class TestHostnameRedaction:
    def test_generic_hostname_does_not_mangle_filenames(self):
        from routes.system.support_logs import _anonymize

        line = "sublarr-instance: db=sublarr.db"
        assert _anonymize(line, hostname="sublarr") == line

    def test_hostname_is_matched_case_insensitively_and_whole_word(self):
        from routes.system.support_logs import _anonymize

        out = _anonymize("Host CARDINAL up; cardinalfish swims", hostname="cardinal")
        assert out == "Host ***HOST*** up; cardinalfish swims"


# ─── Bundle content additions ────────────────────────────────────────────────

_SECTION_KEYS = {"database", "scheduler", "providers", "queues", "foreign_tracks", "environment"}


class TestBundleSections:
    def test_zip_carries_sections_and_recent_warnings(self, client, log_file):
        log_file.write_text(f"{_stamp()},1 [WARNING] [-] a: careful\n", encoding="utf-8")

        z = _zip(client.get("/api/v1/logs/support-export"))
        names = z.namelist()

        assert "recent-warnings.log" in names
        assert "careful" in z.read("recent-warnings.log").decode("utf-8")
        sections = json.loads(z.read("sections.json"))
        assert set(sections) == _SECTION_KEYS
        for name, data in sections.items():
            assert "unavailable" not in data, (name, data)

    def test_section_contents(self, client, log_file):
        sections = client.get("/api/v1/logs/support-preview").get_json()["sections"]

        db = sections["database"]
        assert db["backend"] == "sqlite"
        assert db["alembic"]["tracked"] in (True, False)
        assert "pending" in db["untracked_data_repairs"]
        assert "recent_runs" in sections["scheduler"]
        assert "interval_zero_settings" in sections["scheduler"]
        assert isinstance(sections["providers"]["providers"], list)
        assert "subtitle_automation_queue" in sections["queues"]
        ft = sections["foreign_tracks"]
        assert {"phase", "generation", "enumeration_complete", "paused_reason"} <= set(
            ft["sweep_state"]
        )
        assert set(ft["track_policy"]) == {
            "cleanup_track_variant_mode",
            "cleanup_keep_forced",
            "cleanup_keep_sdh",
            "cleanup_sidecar_policy",
            "foreign_track_sweep_enabled",
            "cleanup_foreign_tracks_default",
        }
        env = sections["environment"]
        assert {"ffmpeg", "ffprobe", "mkvmerge"} <= set(env["tools"])
        assert "container" in env
        assert "utc_offset" in env["timezone"]

    def test_a_failing_section_is_reported_not_fatal(self, client, log_file, monkeypatch):
        import routes.system.support_sections as sections_mod

        def _boom():
            raise RuntimeError("table gone password=Leak123")

        monkeypatch.setitem(sections_mod.SECTIONS, "queues", _boom)

        z = _zip(client.get("/api/v1/logs/support-export"))

        sections = json.loads(z.read("sections.json"))
        assert sections["queues"]["unavailable"].startswith("RuntimeError: table gone")
        assert "Leak123" not in sections["queues"]["unavailable"]
        assert "unavailable" not in sections["database"]
        assert "queues: unavailable" in z.read("diagnostic-report.md").decode("utf-8")

    def test_preview_shape(self, client, log_file):
        data = client.get("/api/v1/logs/support-preview").get_json()

        assert {
            "diagnostic",
            "redaction_summary",
            "log_payload",
            "recent_warnings_count",
            "sections",
            "generated_at",
            "cached",
        } <= set(data)
        assert set(data["sections"]) == _SECTION_KEYS
        assert {"truncated", "included_bytes", "total_bytes", "cap_bytes"} <= set(
            data["log_payload"]
        )


class TestProviderActive:
    """An empty providers_enabled means 'all allowed', not 'all active'."""

    def test_unconfigured_providers_are_not_active(self, app_ctx):
        from providers import _PROVIDER_CLASSES, get_provider_manager
        from routes.system.support_sections import provider_rows

        rows = provider_rows()
        live = set(get_provider_manager()._providers)

        assert {r["name"] for r in rows} == set(_PROVIDER_CLASSES)
        assert {r["name"] for r in rows if r["active"]} == live
        assert all(r["enabled"] for r in rows)  # empty setting = all allowed
        assert len(live) < len(_PROVIDER_CLASSES), "test needs an unconfigured provider"


class TestDiagnosticStatsActuallyLoad:
    """The repositories take no arguments; passing a session made every
    bundle report its wanted/translation stats as "unavailable"."""

    def test_wanted_and_translation_stats_are_present(self, app_ctx):
        from routes.system.support import _build_diagnostic

        diag = _build_diagnostic()

        assert "db_stats_error" not in diag
        assert diag["wanted"]["total"] == 0
        assert "total_requests" in diag["translations"]

    def test_last_scan_minutes_reads_the_timestamp(self, app_ctx):
        from db.config import save_config_entry
        from routes.system.support import _get_last_scan_minutes

        stamp = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=30)).isoformat()
        save_config_entry("last_scan_timestamp", stamp)

        assert _get_last_scan_minutes() in (29, 30, 31)
