"""A download that proves nothing is not repeated while the file stays the same.

Prod 1.17.0-rc.12: the first 19 OpenSubtitles downloads of a repair pass were
all unprovable — no replay of the old pipeline reproduces the file on disk.
Nothing recorded that, so every pass (and the daily auto-resume) fetched the
same files first, and once a day had passed they counted against the quota
again: the pass could stall on files it can never repair.
"""

from unittest.mock import patch

from sqlalchemy import text as sql

from extensions import db
from services.repair import scanner
from services.repair.runner import RepairCandidate, repair_one
from services.repair.scanner import content_hash
from tests.test_repair_runner import ORIGINAL, _srt

ON_DISK = _srt([(1000, 3000, "Meine eigene Übersetzung.")])


def _candidate(path) -> RepairCandidate:
    return RepairCandidate(
        file_path=str(path),
        language="de",
        fmt="srt",
        original_hash="pristine",
        provider="opensubtitles",
        subtitle_id="7440128",
    )


def _recorded(path) -> list[tuple[str, str]]:
    return db.session.execute(
        sql("SELECT status, repaired_hash FROM subtitle_repairs WHERE file_path = :p"),
        {"p": str(path)},
    ).fetchall()


def test_an_unprovable_download_is_recorded(app_ctx, tmp_path):
    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ON_DISK)

    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL):
        outcome = repair_one(_candidate(path))

    assert outcome.status == "unprovable"
    assert path.read_bytes() == ON_DISK
    assert [tuple(r) for r in _recorded(path)] == [("unprovable", content_hash(str(path)))]


def test_an_unprovable_backup_is_not_recorded(app_ctx, tmp_path):
    """A .bak costs nothing to check again, so it keeps no record."""
    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ON_DISK)

    with (
        patch("services.repair.runner._pristine_bak", return_value=ORIGINAL),
        patch("services.repair.runner.fetch_original") as fetch,
    ):
        outcome = repair_one(_candidate(path))

    assert outcome.status == "unprovable"
    fetch.assert_not_called()
    assert _recorded(path) == []


def test_a_dry_run_records_nothing(app_ctx, tmp_path):
    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ON_DISK)

    with patch("services.repair.runner.fetch_original", return_value=ORIGINAL):
        repair_one(_candidate(path), dry_run=True)

    assert _recorded(path) == []


def _scan_recorded(tmp_path, recorded):
    """scanner.scan over the one sidecar, with ``recorded`` as subtitle_repairs."""
    from unittest.mock import MagicMock

    path = tmp_path / "Show - S01E01.de.srt"
    rows = MagicMock()
    rows.fetchall.return_value = [(str(path), "pristine", "de", "srt")]
    index = {(str(tmp_path / "Show - S01E01"), "de"): ("opensubtitles", "7440128", "")}
    with (
        patch.object(scanner.db.session, "execute", return_value=rows),
        patch.object(scanner, "_download_index", return_value=index),
        patch.object(scanner, "_repaired_paths", return_value=recorded),
    ):
        return scanner.scan()


def test_scan_skips_a_file_unchanged_since_its_unprovable_download(app_ctx, tmp_path):
    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ON_DISK)

    report = _scan_recorded(tmp_path, {str(path): (content_hash(str(path)), "unprovable")})

    assert report.candidates == []
    assert report.unprovable_after_download == 1


def test_scan_offers_it_again_once_the_file_changed(app_ctx, tmp_path):
    path = tmp_path / "Show - S01E01.de.srt"
    path.write_bytes(ON_DISK)

    report = _scan_recorded(tmp_path, {str(path): ("hash-before-the-edit", "unprovable")})

    assert [c.file_path for c in report.candidates] == [str(path)]
    assert report.unprovable_after_download == 0
