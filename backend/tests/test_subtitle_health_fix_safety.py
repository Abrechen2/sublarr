"""Regression tests for Fix 1: backup-abort safety (data-loss prevention)."""

from unittest.mock import patch

from services.subtitle_health.fixers import reencode, repair_escapes


def test_repair_aborts_when_backup_fails(tmp_path):
    p = tmp_path / "x.de.srt"
    p.write_bytes(b"1\n00:00:01,000 --> 00:00:02,000\nA\\NB\n")
    before = p.read_bytes()
    with patch("services.subtitle_health.fixers.repair_escapes.backup_sidecar", return_value=None):
        res = repair_escapes.apply_to_sidecar(str(p), "srt")
    assert res["changed"] is False
    assert p.read_bytes() == before  # original NOT overwritten


def test_reencode_aborts_when_backup_fails(tmp_path):
    p = tmp_path / "x.de.srt"
    p.write_bytes("Schön".encode("cp1252"))
    before = p.read_bytes()
    with patch("services.subtitle_health.fixers.reencode.backup_sidecar", return_value=None):
        res = reencode.apply_to_sidecar(str(p))
    assert res["changed"] is False
    assert p.read_bytes() == before
