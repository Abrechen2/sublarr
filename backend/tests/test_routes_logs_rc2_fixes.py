"""/logs and /logs/rotation fixes for 1.15.0-rc.2 (I1, I5, N2, N4)."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler


def _point_at(tmp_path, monkeypatch, text: str):
    log = tmp_path / "sublarr.log"
    log.write_text(text, encoding="utf-8")
    from config import get_settings

    monkeypatch.setattr(get_settings(), "log_file", str(log), raising=False)
    return log


class TestLevelFilterUnderstandsJson:
    """I1: `level=ERROR` matched `[ERROR]` only, so JSON logs filtered to nothing."""

    def test_json_lines_are_filtered_by_level(self, client, tmp_path, monkeypatch):
        rows = [
            json.dumps({"timestamp": "t", "level": lvl, "logger": "a", "message": f"m{i}"})
            for i, lvl in enumerate(["INFO", "ERROR", "INFO", "ERROR"])
        ]
        _point_at(tmp_path, monkeypatch, "\n".join(rows))

        data = client.get("/api/v1/logs?level=ERROR").get_json()

        assert [json.loads(e)["message"] for e in data["entries"]] == ["m1", "m3"]


class TestLevelIsValidated:
    """N2: an unknown level matched nothing and forced a full-file read."""

    def test_unknown_level_is_400(self, client, tmp_path, monkeypatch):
        _point_at(tmp_path, monkeypatch, "2026-07-17 10:00:00,000 [INFO] a.b: x\n")

        resp = client.get("/api/v1/logs?level=VERBOSE")

        assert resp.status_code == 400
        assert "level" in resp.get_json()["error"]

    def test_lowercase_known_level_still_works(self, client, tmp_path, monkeypatch):
        _point_at(tmp_path, monkeypatch, "2026-07-17 10:00:00,000 [WARNING] a.b: x\n")

        resp = client.get("/api/v1/logs?level=warning")

        assert resp.status_code == 200
        assert len(resp.get_json()["entries"]) == 1


class TestRotationGetIsDefensive:
    """N4: `int()` on the raw config row — 500 on junk."""

    def test_non_numeric_row_falls_back_to_default(self, client):
        from app_logging import LOG_BACKUP_COUNT_DEFAULT, LOG_MAX_SIZE_MB_DEFAULT
        from db.config import save_config_entry

        with client.application.app_context():
            save_config_entry("log_max_size_mb", "lots")
            save_config_entry("log_backup_count", "true")

        resp = client.get("/api/v1/logs/rotation")

        assert resp.status_code == 200
        assert resp.get_json() == {
            "max_size_mb": LOG_MAX_SIZE_MB_DEFAULT,
            "backup_count": LOG_BACKUP_COUNT_DEFAULT,
        }

    def test_out_of_range_row_is_clamped(self, client):
        from app_logging import LOG_MAX_SIZE_MB_MAX
        from db.config import save_config_entry

        with client.application.app_context():
            save_config_entry("log_max_size_mb", "5000")

        assert client.get("/api/v1/logs/rotation").get_json()["max_size_mb"] == LOG_MAX_SIZE_MB_MAX


class TestRotationPutAppliesLive:
    """I5: PUT saved the rows and said so, but the handler kept the old window."""

    def _file_handler(self):
        for h in logging.getLogger().handlers:
            if isinstance(h, RotatingFileHandler):
                return h
        return None

    def test_new_window_is_live_without_a_restart(self, client, tmp_path, monkeypatch):
        from config import reload_settings

        monkeypatch.setenv("SUBLARR_LOG_FILE", str(tmp_path / "live.log"))
        reload_settings()
        root = logging.getLogger()
        before = list(root.handlers)
        try:
            resp = client.put("/api/v1/logs/rotation", json={"max_size_mb": 7, "backup_count": 2})
            data = resp.get_json()

            assert resp.status_code == 200
            assert data["live"] is True
            handler = self._file_handler()
            assert handler is not None
            assert handler.maxBytes == 7 * 1024 * 1024
            assert handler.backupCount == 2
        finally:
            for h in list(root.handlers):
                if h not in before:
                    root.removeHandler(h)
                    h.close()
            for h in before:
                if h not in root.handlers:
                    root.addHandler(h)

    def test_failed_reapply_is_reported_honestly(self, client, monkeypatch):
        import app_logging

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(app_logging, "_setup_logging", _boom)

        resp = client.put("/api/v1/logs/rotation", json={"max_size_mb": 3})
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["live"] is False
        assert data["max_size_mb"] == 3


class TestDownloadRateLimit:
    """/logs/download builds the same bundle by calling the export view as a
    function, which bypasses that view's limit."""

    def test_bundle_path_is_limited(self, client, tmp_path, monkeypatch):
        _point_at(tmp_path, monkeypatch, "")
        codes = [client.get("/api/v1/logs/download").status_code for _ in range(7)]
        assert codes[6] == 429

    def test_raw_path_is_not_limited(self, client, tmp_path, monkeypatch):
        _point_at(tmp_path, monkeypatch, "x\n")
        codes = [client.get("/api/v1/logs/download?raw=1").status_code for _ in range(8)]
        assert set(codes) == {200}
