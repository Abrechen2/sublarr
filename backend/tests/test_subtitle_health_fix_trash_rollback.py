import os
import shutil

from services.subtitle_health import store
from services.subtitle_health.fixers import quarantine_sidecar, rollback, trash_sidecar


def test_quarantine_moves_file(tmp_path, app_ctx):
    p = tmp_path / "x.de.srt"
    p.write_bytes(b"english content tagged de")
    res = quarantine_sidecar.apply(str(p))
    assert res["changed"] is True
    assert not p.exists()  # moved to quarantine
    assert os.path.exists(res["quarantined_path"])


def test_trash_sidecar_records_manifest(tmp_path, app_ctx, monkeypatch):
    p = tmp_path / "x.de.srt"
    p.write_bytes(b"bogus de content")
    monkeypatch.setattr(
        "services.subtitle_health.fixers.trash_sidecar.backup_sidecar",
        lambda path: str(tmp_path / "trash_x.de.srt"),
    )
    res = trash_sidecar.apply(str(p))
    assert res["changed"] is True
    assert res["fix_id"]


def test_rollback_restores_original(tmp_path, app_ctx):
    orig = tmp_path / "x.de.srt"
    orig.write_bytes(b"ORIGINAL")
    trashed = tmp_path / "trash" / "x.de.srt"
    trashed.parent.mkdir()
    shutil.move(str(orig), str(trashed))
    orig.write_bytes(b"FIXED")  # simulate the fixed file in place
    fix_id = store.record_fix(
        finding_id=None,
        fixer="repair_escapes",
        action="repair_escapes",
        target_path=str(orig),
        trashed_original_path=str(trashed),
        original_hash="o",
        fixed_hash="f",
        reversible=True,
    )
    res = rollback.apply(fix_id)
    assert res["restored"] is True
    assert orig.read_bytes() == b"ORIGINAL"
