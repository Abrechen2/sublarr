"""GET /logs used to decode the whole 5MB file per 10s poll (100-300ms CPU on
a NAS Celeron, GIL-held). Tail-read only what is needed. Also fixes: level
filter used to run AFTER truncation, returning fewer than `lines` entries."""


def test_logs_returns_requested_lines(client, tmp_path, monkeypatch):
    log = tmp_path / "sublarr.log"
    log.write_text(
        "\n".join(f"2026-07-17 10:00:{i:02d},000 [INFO] a.b: line {i}" for i in range(300)),
        encoding="utf-8",
    )
    from config import get_settings

    monkeypatch.setattr(get_settings(), "log_file", str(log), raising=False)

    resp = client.get("/api/v1/logs?lines=50")
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["entries"]) == 50
    assert data["entries"][-1].endswith("line 299")


def test_logs_level_filter_fills_up_to_lines(client, tmp_path, monkeypatch):
    log = tmp_path / "sublarr.log"
    rows = []
    for i in range(200):
        lvl = "ERROR" if i % 10 == 0 else "INFO"
        rows.append(f"2026-07-17 10:00:00,000 [{lvl}] a.b: line {i}")
    log.write_text("\n".join(rows), encoding="utf-8")
    from config import get_settings

    monkeypatch.setattr(get_settings(), "log_file", str(log), raising=False)

    resp = client.get("/api/v1/logs?lines=10&level=ERROR")
    data = resp.get_json()
    assert len(data["entries"]) == 10, "filter must fill the requested count from older lines"
    assert all("[ERROR]" in e for e in data["entries"])
