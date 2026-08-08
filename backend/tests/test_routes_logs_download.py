"""GET /logs/download serves the anonymised support bundle, not the raw log.

Users kept attaching a raw `sublarr.log` to bug reports even though the
anonymised support export existed and was advertised. Two consequences: the
file leaks host paths, IPs and hostnames that the export would have redacted,
and it arrives without the diagnostic context that makes it usable — version,
platform, deployment mode, top errors. The obvious button therefore now yields
the file that is actually worth sending.

`?raw=1` keeps the previous behaviour for anyone scripting the endpoint.
"""


def _point_log_file_at(tmp_path, monkeypatch, content="2026-08-08 10:00:00,000 [INFO] a.b: x\n"):
    log = tmp_path / "sublarr.log"
    log.write_text(content, encoding="utf-8")
    from config import get_settings

    monkeypatch.setattr(get_settings(), "log_file", str(log), raising=False)
    return log


class TestDownloadServesTheBundle:
    def test_default_download_is_a_zip(self, client, tmp_path, monkeypatch):
        _point_log_file_at(tmp_path, monkeypatch)

        resp = client.get("/api/v1/logs/download")

        assert resp.status_code == 200
        assert resp.mimetype == "application/zip"

    def test_default_download_contains_the_diagnostic_report(self, client, tmp_path, monkeypatch):
        # The whole point: context travels with the log.
        import io
        import zipfile

        _point_log_file_at(tmp_path, monkeypatch)

        resp = client.get("/api/v1/logs/download")
        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            names = zf.namelist()

        assert "diagnostic-report.md" in names
        assert any(n.startswith("logs/") for n in names)

    def test_default_download_anonymises_the_log_contents(self, client, tmp_path, monkeypatch):
        import io
        import zipfile

        _point_log_file_at(
            tmp_path,
            monkeypatch,
            content="2026-08-08 10:00:00,000 [ERROR] p: failed talking to 192.168.178.194\n",
        )

        resp = client.get("/api/v1/logs/download")
        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            log_member = next(n for n in zf.namelist() if n.startswith("logs/"))
            body = zf.read(log_member).decode("utf-8")

        assert "192.168.178.194" not in body, "the raw address must not survive the export"
        assert "192.168.xxx.xxx" in body

    def test_raw_escape_hatch_still_serves_the_plain_file(self, client, tmp_path, monkeypatch):
        # Scripted callers predate the change; ?raw=1 is their migration path.
        _point_log_file_at(tmp_path, monkeypatch, content="2026-08-08 10:00:00,000 [INFO] a.b: hi\n")

        resp = client.get("/api/v1/logs/download?raw=1")

        assert resp.status_code == 200
        assert resp.mimetype == "text/plain"
        assert b"hi" in resp.data

    def test_raw_download_reports_a_missing_log_file(self, client, tmp_path, monkeypatch):
        from config import get_settings

        monkeypatch.setattr(
            get_settings(), "log_file", str(tmp_path / "absent.log"), raising=False
        )

        resp = client.get("/api/v1/logs/download?raw=1")

        assert resp.status_code == 404
