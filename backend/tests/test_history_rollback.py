"""Tests for the History rollback feature.

Covers:
- services.subtitle_restore.backup_before_replace (single-slot semantics)
- save_subtitle preserving an existing sidecar into the bak slot
- POST /api/v1/history/<id>/rollback (same-format swap, cross-format
  upgrade rollback, missing entry/backup)
- get_download_history enrichment with previous_score/previous_format
"""

import os
from unittest.mock import MagicMock, patch

from subtitle_filename import bak_path_for

# ── backup_before_replace ─────────────────────────────────────────────────────


class TestBackupBeforeReplace:
    def test_creates_bak_when_slot_free(self, tmp_path):
        from services.subtitle_restore import backup_before_replace

        active = tmp_path / "ep.de.srt"
        active.write_text("old content", encoding="utf-8")

        bak = backup_before_replace(str(active))

        assert bak == bak_path_for(str(active))
        assert open(bak, encoding="utf-8").read() == "old content"
        # Active file itself is untouched (copy, not move).
        assert active.read_text(encoding="utf-8") == "old content"

    def test_never_overwrites_existing_bak(self, tmp_path):
        """The bak is a single-slot undo — an existing one must survive."""
        from services.subtitle_restore import backup_before_replace

        active = tmp_path / "ep.de.srt"
        active.write_text("second version", encoding="utf-8")
        existing_bak = bak_path_for(str(active))
        os.makedirs(os.path.dirname(existing_bak), exist_ok=True)
        with open(existing_bak, "w", encoding="utf-8") as f:
            f.write("pristine original")

        assert backup_before_replace(str(active)) is None
        assert open(existing_bak, encoding="utf-8").read() == "pristine original"

    def test_noop_when_active_missing(self, tmp_path):
        from services.subtitle_restore import backup_before_replace

        assert backup_before_replace(str(tmp_path / "missing.de.srt")) is None


# ── save_subtitle writes a bak before replacing ──────────────────────────────


def _make_result(content: bytes = b"1\n00:00:01,000 --> 00:00:02,000\nNeu\n"):
    from providers.base import SubtitleFormat, SubtitleResult

    r = SubtitleResult.__new__(SubtitleResult)
    r.content = content
    r.format = SubtitleFormat.SRT
    r.provider_name = "test_provider"
    r.language = "de"
    r.score = 100
    r.subtitle_id = "sub123"
    return r


def _make_manager():
    from providers import ProviderManager

    mgr = ProviderManager.__new__(ProviderManager)
    mgr._providers = {}
    return mgr


class TestSaveSubtitleBackupOnReplace:
    def test_existing_sidecar_is_preserved_into_bak(self, tmp_path):
        mgr = _make_manager()
        result = _make_result()
        output = str(tmp_path / "episode.de.srt")
        with open(output, "w", encoding="utf-8") as f:
            f.write("previous version")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
        ):
            saved = mgr.save_subtitle(result, output)

        assert os.path.isfile(saved)
        bak = bak_path_for(output)
        assert os.path.isfile(bak), "replaced sidecar must be preserved in the bak slot"
        assert open(bak, encoding="utf-8").read() == "previous version"

    def test_fresh_save_creates_no_bak(self, tmp_path):
        mgr = _make_manager()
        result = _make_result()
        output = str(tmp_path / "episode.de.srt")

        mock_settings = MagicMock(media_path=str(tmp_path), dedup_on_download=False)
        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("security_utils.is_safe_path", return_value=True),
        ):
            mgr.save_subtitle(result, output)

        assert not os.path.exists(bak_path_for(output))


# ── Rollback route ───────────────────────────────────────────────────────────


def _record_download(client, file_path, fmt="srt", lang="de", score=100, upgraded_from_id=None):
    from db.providers import record_subtitle_download

    with client.application.app_context():
        record_subtitle_download(
            "test_provider",
            "sub123",
            lang,
            fmt,
            file_path,
            score,
            upgraded_from_id=upgraded_from_id,
        )
        from db.providers import get_latest_download_id

        return get_latest_download_id(file_path)


class TestRollbackRoute:
    def test_entry_not_found(self, client):
        resp = client.post("/api/v1/history/999999/rollback")
        assert resp.status_code == 404

    def test_no_backup_returns_404(self, client, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        sidecar = tmp_path / "ep.de.srt"
        sidecar.write_text("current", encoding="utf-8")
        dl_id = _record_download(client, str(mkv))

        resp = client.post(f"/api/v1/history/{dl_id}/rollback")
        assert resp.status_code == 404
        assert "backup" in resp.get_json()["error"].lower()

    def test_same_format_rollback_swaps_active_and_bak(self, client, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        sidecar = tmp_path / "ep.de.srt"
        sidecar.write_text("new version", encoding="utf-8")
        bak = bak_path_for(str(sidecar))
        os.makedirs(os.path.dirname(bak), exist_ok=True)
        with open(bak, "w", encoding="utf-8") as f:
            f.write("old version")
        dl_id = _record_download(client, str(mkv))

        resp = client.post(f"/api/v1/history/{dl_id}/rollback")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "restored"
        assert sidecar.read_text(encoding="utf-8") == "old version"
        # Swap semantics: invoking rollback again flips back.
        assert open(bak, encoding="utf-8").read() == "new version"

    def test_cross_format_rollback_restores_old_and_retires_new(self, client, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        # The upgrade replaced ep.de.srt with ep.de.ass; the old SRT was
        # preserved in its bak slot at upgrade time.
        old_srt_active = tmp_path / "ep.de.srt"
        old_bak = bak_path_for(str(old_srt_active))
        os.makedirs(os.path.dirname(old_bak), exist_ok=True)
        with open(old_bak, "w", encoding="utf-8") as f:
            f.write("old srt version")
        new_ass = tmp_path / "ep.de.ass"
        new_ass.write_text("new ass version", encoding="utf-8")

        prev_id = _record_download(client, str(mkv), fmt="srt", score=100)
        new_id = _record_download(client, str(mkv), fmt="ass", score=180, upgraded_from_id=prev_id)

        resp = client.post(f"/api/v1/history/{new_id}/rollback")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "restored"
        assert old_srt_active.read_text(encoding="utf-8") == "old srt version"
        assert not new_ass.exists(), "the upgraded ASS must be retired"
        # The retired ASS is itself recoverable from its bak slot.
        assert open(bak_path_for(str(new_ass)), encoding="utf-8").read() == "new ass version"


# ── History listing enrichment ───────────────────────────────────────────────


class TestHistoryPreviousFields:
    def test_upgrade_entry_carries_previous_score_and_format(self, client, tmp_path):
        mkv = tmp_path / "ep.mkv"
        mkv.touch()
        prev_id = _record_download(client, str(mkv), fmt="srt", score=90)
        _record_download(client, str(mkv), fmt="ass", score=150, upgraded_from_id=prev_id)

        resp = client.get("/api/v1/history")
        assert resp.status_code == 200
        entries = resp.get_json()["data"]
        by_format = {e["format"]: e for e in entries}
        assert by_format["ass"]["upgraded_from_id"] == prev_id
        assert by_format["ass"]["previous_score"] == 90
        assert by_format["ass"]["previous_format"] == "srt"
        assert by_format["srt"]["previous_score"] is None
