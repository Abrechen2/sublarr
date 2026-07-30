"""Tests for the per-series subtitle format requirement (require_ass)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


def _set_requirement(series_id: int, value: str | None) -> None:
    from db.models.core import SeriesSettings
    from extensions import db

    now = datetime.now(UTC)
    row = db.session.get(SeriesSettings, series_id)
    if row is None:
        row = SeriesSettings(
            sonarr_series_id=series_id,
            absolute_order=0,
            min_attempts_per_day=0,
            updated_at=now,
        )
        db.session.add(row)
    row.subtitle_format_requirement = value
    row.updated_at = now
    db.session.commit()


class TestGetSeriesFormatRequirement:
    def test_none_for_unknown_series(self, app_ctx):
        from services.series_format import get_series_format_requirement

        assert get_series_format_requirement(987654) is None

    def test_none_for_missing_series_id(self, app_ctx):
        from services.series_format import get_series_format_requirement

        assert get_series_format_requirement(None) is None
        assert get_series_format_requirement(0) is None

    def test_returns_require_ass_when_set(self, app_ctx):
        from services.series_format import get_series_format_requirement

        _set_requirement(500, "require_ass")
        assert get_series_format_requirement(500) == "require_ass"

    def test_unknown_value_treated_as_none(self, app_ctx):
        from services.series_format import get_series_format_requirement

        _set_requirement(501, "require_vtt")
        assert get_series_format_requirement(501) is None

    def test_null_value_is_none(self, app_ctx):
        from services.series_format import get_series_format_requirement

        _set_requirement(502, None)
        assert get_series_format_requirement(502) is None


class TestPatchRoute:
    def test_patch_sets_requirement(self, client):
        r = client.patch(
            "/api/v1/series/600/settings",
            json={"subtitle_format_requirement": "require_ass"},
        )
        assert r.status_code == 200
        assert r.get_json()["subtitle_format_requirement"] == "require_ass"

    def test_patch_clears_requirement_with_null(self, client):
        client.patch(
            "/api/v1/series/601/settings",
            json={"subtitle_format_requirement": "require_ass"},
        )
        r = client.patch(
            "/api/v1/series/601/settings",
            json={"subtitle_format_requirement": None},
        )
        assert r.status_code == 200
        assert r.get_json()["subtitle_format_requirement"] is None

    def test_patch_rejects_unknown_value(self, client):
        r = client.patch(
            "/api/v1/series/602/settings",
            json={"subtitle_format_requirement": "require_vtt"},
        )
        assert r.status_code == 400

    def test_patch_without_field_leaves_value_untouched(self, client):
        client.patch(
            "/api/v1/series/603/settings",
            json={"subtitle_format_requirement": "require_ass"},
        )
        r = client.patch("/api/v1/series/603/settings", json={"min_attempts_per_day": 3})
        assert r.status_code == 200
        assert r.get_json()["subtitle_format_requirement"] == "require_ass"


class TestWantedSearchEnforcement:
    """search_wanted_item must skip the SRT searches for require_ass series."""

    def _run_search(self, app_ctx, monkeypatch, requirement):
        from wanted_search import search as search_mod

        series_id = 700
        _set_requirement(series_id, requirement)

        item = {
            "id": 1,
            "sonarr_series_id": series_id,
            "file_path": "/media/show/S01E01.mkv",
            "target_language": "de",
        }
        monkeypatch.setattr(search_mod, "get_wanted_item", lambda _id: item)
        monkeypatch.setattr(search_mod, "update_wanted_search", lambda _id: None)
        monkeypatch.setattr(search_mod, "build_query_from_wanted", lambda _item: MagicMock())

        manager = MagicMock()
        manager.search.return_value = []
        with patch.object(search_mod, "get_provider_manager", return_value=manager):
            result = search_mod.search_wanted_item(1)

        assert "error" not in result
        from providers.base import SubtitleFormat

        formats = [kwargs.get("format_filter") for _args, kwargs in manager.search.call_args_list]
        return formats

    def test_require_ass_skips_srt_searches(self, app_ctx, monkeypatch):
        from providers.base import SubtitleFormat

        formats = self._run_search(app_ctx, monkeypatch, "require_ass")
        assert formats.count(SubtitleFormat.ASS) == 2
        assert SubtitleFormat.SRT not in formats

    def test_no_requirement_runs_all_four_searches(self, app_ctx, monkeypatch):
        from providers.base import SubtitleFormat

        formats = self._run_search(app_ctx, monkeypatch, None)
        assert formats.count(SubtitleFormat.ASS) == 2
        assert formats.count(SubtitleFormat.SRT) == 2
