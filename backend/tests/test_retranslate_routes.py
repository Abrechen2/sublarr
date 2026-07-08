"""Tests for POST /api/v1/retranslate/<id> — job-id vs wanted-item resolution.

Regression coverage for a prod bug: calling /retranslate/<wanted_item_id>
translated the file successfully but never touched the wanted_items row, so
the item sat in "wanted" forever even though its target subtitle already
existed on disk. The fix reuses services.retranslation._finalize_retranslation
(the same helper /wanted/batch-translate already relies on) so both entry
points flag MT output and resolve the wanted item identically.
"""

from unittest.mock import patch

from db.config import save_config_entry
from db.wanted import get_wanted_item, upsert_wanted_item

# `client` fixture comes from conftest.py (temp_db-backed, SUBLARR_MEDIA_PATH
# already pointed at the system temp dir, which pytest's tmp_path nests under).


def _run_sync(monkeypatch):
    """Make submit_background execute inline instead of on the thread pool."""
    monkeypatch.setattr(
        "routes.translate.retranslate.submit_background",
        lambda fn, *a, **k: fn(*a, **k),
    )


class TestRetranslateSingleWithJobId:
    def test_job_id_path_does_not_touch_wanted_items(self, client, tmp_path, monkeypatch):
        """Re-translating a plain job (no associated wanted item) must not
        call the finalize helper at all — there's nothing to resolve."""
        _run_sync(monkeypatch)

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")

        media = tmp_path / "ep.mkv"
        media.write_text("x")
        fake_job = {"id": "j1", "status": "completed", "file_path": str(media)}

        with (
            patch("db.jobs.get_job", return_value=fake_job),
            patch(
                "routes.translate.retranslate._run_job",
                return_value={
                    "success": True,
                    "output_path": str(tmp_path / "ep.de.ass"),
                    "stats": {},
                },
            ),
            patch("services.retranslation._finalize_retranslation") as mock_finalize,
        ):
            resp = client.post("/api/v1/retranslate/1")

        assert resp.status_code == 202
        mock_finalize.assert_not_called()


class TestRetranslateSingleWithWantedItem:
    def test_success_resolves_wanted_item_to_provisional(self, client, tmp_path, monkeypatch):
        """A genuine (non-skip) successful re-translation must flag the MT
        output and flip the wanted item to provisional — mirroring exactly
        what /wanted/batch-translate already does."""
        _run_sync(monkeypatch)

        from services import mt_provisional

        monkeypatch.setattr(mt_provisional, "resolve_keep_seeking", lambda item: True)

        media = tmp_path / "ep.mkv"
        media.write_text("x")

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")
            item_id, _ = upsert_wanted_item(
                item_type="episode", file_path=str(media), target_language="de"
            )

        out_path = str(tmp_path / "ep.de.ass")
        with (
            patch("db.jobs.get_job", return_value=None),
            patch(
                "routes.translate.retranslate._run_job",
                return_value={
                    "success": True,
                    "output_path": out_path,
                    "stats": {"format": "ass", "source": "embedded_ass"},
                },
            ),
        ):
            resp = client.post(f"/api/v1/retranslate/{item_id}")

        assert resp.status_code == 202
        with client.application.app_context():
            assert get_wanted_item(item_id)["status"] == "provisional"

    def test_skip_result_leaves_wanted_item_untouched(self, client, tmp_path, monkeypatch):
        """A skip (target already exists) must not flip the item to
        provisional and must not record an MT row — same contract as
        _finalize_retranslation's existing unit tests."""
        _run_sync(monkeypatch)

        media = tmp_path / "ep.mkv"
        media.write_text("x")

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")
            item_id, _ = upsert_wanted_item(
                item_type="episode", file_path=str(media), target_language="de"
            )

        with (
            patch("db.jobs.get_job", return_value=None),
            patch(
                "routes.translate.retranslate._run_job",
                return_value={
                    "success": True,
                    "output_path": str(tmp_path / "ep.de.ass"),
                    "stats": {"skipped": True, "reason": "already exists"},
                },
            ),
        ):
            resp = client.post(f"/api/v1/retranslate/{item_id}")

        assert resp.status_code == 202
        with client.application.app_context():
            assert get_wanted_item(item_id)["status"] == "wanted"

    def test_failed_result_leaves_wanted_item_untouched(self, client, tmp_path, monkeypatch):
        _run_sync(monkeypatch)

        media = tmp_path / "ep.mkv"
        media.write_text("x")

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")
            item_id, _ = upsert_wanted_item(
                item_type="episode", file_path=str(media), target_language="de"
            )

        with (
            patch("db.jobs.get_job", return_value=None),
            patch(
                "routes.translate.retranslate._run_job",
                return_value={"success": False, "error": "boom"},
            ),
        ):
            resp = client.post(f"/api/v1/retranslate/{item_id}")

        assert resp.status_code == 202
        with client.application.app_context():
            assert get_wanted_item(item_id)["status"] == "wanted"

    def test_unknown_id_returns_404(self, client):
        with client.application.app_context():
            save_config_entry("translation_enabled", "true")
        with patch("db.jobs.get_job", return_value=None):
            resp = client.post("/api/v1/retranslate/999999")
        assert resp.status_code == 404


class TestRetranslateBatch:
    """Regression: /retranslate/batch called translate_file() directly and
    skipped services.mt_provisional.record_mt_output entirely -- unlike
    /retranslate/<id> and the wanted_search translate paths, a successful
    batch re-translation produced no History entry and no MT-flagged
    subtitle_downloads row (bug found 2026-07-08, same class as the single-
    retranslate gap this file's other tests cover)."""

    def test_success_records_mt_row_and_history_entry(self, client, tmp_path, monkeypatch):
        _run_sync(monkeypatch)

        media = tmp_path / "ep.mkv"
        media.write_text("x")
        out_path = str(tmp_path / "ep.de.ass")

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")

        with (
            patch(
                "db.jobs.get_outdated_jobs",
                return_value=[{"file_path": str(media)}],
            ),
            patch(
                "translator.translate_file",
                return_value={
                    "success": True,
                    "output_path": out_path,
                    "stats": {"format": "ass"},
                },
            ),
        ):
            resp = client.post("/api/v1/retranslate/batch")

        assert resp.status_code == 202
        with client.application.app_context():
            from db.models.activity import EVENT_TRANSLATE, ActivityLog
            from db.models.providers import SubtitleDownload
            from extensions import db

            row = db.session.query(SubtitleDownload).filter_by(source="machine_translation").one()
            # file_path must be the VIDEO path -- see test_mt_provisional_record.py.
            assert row.file_path == str(media)

            activity_row = (
                db.session.query(ActivityLog)
                .filter_by(event_type=EVENT_TRANSLATE, file_path=str(media))
                .first()
            )
            assert activity_row is not None

    def test_skip_result_records_no_mt_row(self, client, tmp_path, monkeypatch):
        _run_sync(monkeypatch)

        media = tmp_path / "ep.mkv"
        media.write_text("x")

        with client.application.app_context():
            save_config_entry("translation_enabled", "true")

        with (
            patch(
                "db.jobs.get_outdated_jobs",
                return_value=[{"file_path": str(media)}],
            ),
            patch(
                "translator.translate_file",
                return_value={
                    "success": True,
                    "output_path": str(tmp_path / "ep.de.ass"),
                    "stats": {"skipped": True, "reason": "already exists"},
                },
            ),
        ):
            resp = client.post("/api/v1/retranslate/batch")

        assert resp.status_code == 202
        with client.application.app_context():
            from db.models.providers import SubtitleDownload
            from extensions import db

            count = (
                db.session.query(SubtitleDownload).filter_by(source="machine_translation").count()
            )
            assert count == 0
