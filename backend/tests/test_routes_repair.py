"""The repair API. Scanning must be free; running must be exclusive."""

from unittest.mock import patch

from services.repair.scanner import RepairCandidate, ScanReport


def _report(candidates=()):
    return ScanReport(
        candidates=list(candidates),
        untouched=5,
        missing_from_disk=2,
        unresolvable=1,
        already_repaired=0,
    )


def test_scan_reports_damage_and_where_the_originals_come_from(client, tmp_path):
    sidecar = tmp_path / "Show - S01E01.de.srt"
    sidecar.write_text("damaged", encoding="utf-8")
    candidate = RepairCandidate(
        file_path=str(sidecar),
        language="de",
        fmt="srt",
        original_hash="deadbeef",
        provider="opensubtitles",
        subtitle_id="1",
    )

    with patch("services.repair.scanner.scan", return_value=_report([candidate])):
        resp = client.get("/api/v1/repair/scan?language=de")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["damaged"] == 1
    assert body["needs_download"] == 1
    assert body["needs_download_by_provider"] == {"opensubtitles": 1}
    assert body["recoverable_from_backup"] == 0


def test_scan_does_not_download_anything(client, tmp_path):
    """A scan must never cost provider quota — it is a local hash comparison."""
    sidecar = tmp_path / "Show - S01E02.de.srt"
    sidecar.write_text("damaged", encoding="utf-8")
    candidate = RepairCandidate(
        file_path=str(sidecar),
        language="de",
        fmt="srt",
        original_hash="deadbeef",
        provider="opensubtitles",
        subtitle_id="1",
    )

    with (
        patch("services.repair.scanner.scan", return_value=_report([candidate])),
        patch("services.repair.runner.fetch_original") as download,
    ):
        resp = client.get("/api/v1/repair/scan")

    assert resp.status_code == 200
    download.assert_not_called()


def test_run_starts_a_pass(client):
    with patch("services.repair.job.start", return_value=True) as start:
        resp = client.post("/api/v1/repair/run", json={"language": "de", "dry_run": True})

    assert resp.status_code == 202
    assert resp.get_json()["dry_run"] is True
    assert start.call_args.kwargs["language"] == "de"


def test_a_second_pass_is_refused(client):
    """Two passes would race on the same files and spend the quota twice."""
    with patch("services.repair.job.start", return_value=False):
        resp = client.post("/api/v1/repair/run", json={})

    assert resp.status_code == 409


def test_status_reports_progress(client):
    with patch(
        "services.repair.job.get_state",
        return_value={"running": True, "total": 2413, "done": 17, "repaired": 15},
    ):
        resp = client.get("/api/v1/repair/status")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 2413
    assert body["done"] == 17
