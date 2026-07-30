"""Tests for the user-modified trust guard.

An editor save marks the file as hand-edited; the upgrade automation must
refuse to replace marked files while ``upgrade_protect_user_modified`` is on.
"""

import os

import pytest

from db.quality import clear_user_modified, is_user_modified, mark_user_modified
from wanted_search.score_selector import evaluate_upgrade


class _Settings:
    """Minimal settings stand-in for evaluate_upgrade."""

    upgrade_prefer_ass = True
    upgrade_min_score_delta = 50
    upgrade_window_days = 0
    upgrade_protect_user_modified = True


class TestMarkerRoundtrip:
    def test_mark_is_clear_roundtrip(self, app_ctx):
        path = "/media/anime/show/ep01.de.srt"
        assert is_user_modified(path) is False

        mark_user_modified(path)
        assert is_user_modified(path) is True

        assert clear_user_modified(path) == 1
        assert is_user_modified(path) is False

    def test_mark_is_upsert_idempotent(self, app_ctx):
        path = "/media/anime/show/ep02.de.srt"
        first = mark_user_modified(path, source="editor")
        second = mark_user_modified(path, source="editor")
        assert first["id"] == second["id"]
        assert clear_user_modified(path) == 1

    def test_clear_missing_marker_is_noop(self, app_ctx):
        assert clear_user_modified("/media/never/marked.srt") == 0


class TestUpgradeGuard:
    def _evaluate(self, file_path, settings):
        return evaluate_upgrade(
            item_id=1,
            file_path=file_path,
            is_upgrade=True,
            current_score=200,
            new_score=500,
            new_format="ass",
            existing_format="srt",
            provider_name="test",
            settings=settings,
        )

    def test_marked_file_blocks_upgrade(self, app_ctx):
        from translator import get_output_path_for_lang

        video = "/media/anime/show/ep03.mkv"
        existing = get_output_path_for_lang(video, "srt", "")
        mark_user_modified(existing)
        try:
            approved, reason = self._evaluate(video, _Settings())
            assert approved is False
            assert "user-modified" in reason
        finally:
            clear_user_modified(existing)

    def test_unmarked_file_upgrades_normally(self, app_ctx):
        approved, _reason = self._evaluate("/media/anime/show/ep04.mkv", _Settings())
        assert approved is True

    def test_guard_disabled_allows_upgrade(self, app_ctx):
        from translator import get_output_path_for_lang

        video = "/media/anime/show/ep05.mkv"
        existing = get_output_path_for_lang(video, "srt", "")
        mark_user_modified(existing)
        try:
            settings = _Settings()
            settings.upgrade_protect_user_modified = False
            approved, _reason = self._evaluate(video, settings)
            assert approved is True
        finally:
            clear_user_modified(existing)


class TestSaveEndpointMarks:
    def test_save_content_sets_marker(self, client, tmp_path, monkeypatch):
        media = tmp_path / "media"
        media.mkdir()
        monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(media))
        monkeypatch.setenv("SUBLARR_PATH_MAPPING", "")
        from config import reload_settings

        reload_settings()

        sub = media / "episode.de.srt"
        sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHallo\n", encoding="utf-8")
        mtime = os.path.getmtime(str(sub))

        resp = client.put(
            "/api/v1/tools/content",
            json={
                "file_path": str(sub),
                "content": "1\n00:00:01,000 --> 00:00:02,500\nHallo!\n",
                "last_modified": mtime,
            },
        )
        assert resp.status_code == 200, resp.get_json()

        # The endpoint stores the marker under the resolved absolute path.
        with client.application.app_context():
            marked_path = os.path.realpath(str(sub))
            assert is_user_modified(marked_path) or is_user_modified(str(sub))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
