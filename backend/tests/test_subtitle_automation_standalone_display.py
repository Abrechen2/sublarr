"""Standalone-series display alignment (Phase 8).

The Sonarr path in routes/library/series.py already merges
`wanted_items.existing_sub` (embedded_srt/embedded_ass) as a fallback
when filesystem sidecars are absent. Standalone lagged and showed red
pills for languages whose only evidence was an embedded track.

This test pins the fix: a standalone series whose wanted_items have
`existing_sub='embedded_srt'` for German must render DE as present
(non-empty `subtitles['ger']`).
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest


@pytest.fixture
def api(client):
    return client


class TestStandaloneEmbeddedFallback:
    def test_wanted_embedded_sub_populates_subtitles_field(self, api, tmp_path):
        """A standalone wanted_item with existing_sub='embedded_srt' must
        surface as `subtitles['ger'] != ''` in the series detail payload."""
        with api.application.app_context():
            from db.models.core import WantedItem
            from db.models.standalone import StandaloneSeries
            from extensions import db

            series = StandaloneSeries(
                id=9001,
                title="Standalone Anime",
                year=2024,
                folder_path=str(tmp_path / "series1"),
                season_count=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.session.add(series)
            db.session.flush()

            now = datetime.now(UTC)
            item = WantedItem(
                title="Episode 1",
                file_path=str(tmp_path / "ep01.mkv"),
                standalone_series_id=9001,
                target_language="de",
                missing_languages='["de"]',
                status="wanted",
                existing_sub="embedded_srt",
                instance_name="",
                item_type="series",
                season_episode="S01E01",
                added_at=now,
                updated_at=now,
            )
            db.session.add(item)
            db.session.commit()

        r = api.get("/api/v1/library/series/9001")
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["source"] == "standalone"
        eps = payload["episodes"]
        assert len(eps) == 1
        assert eps[0]["subtitles"].get("de") == "embedded_srt", (
            "standalone path must fall back to wanted_items.existing_sub for "
            "embedded tracks, matching the Sonarr path"
        )

    def test_filesystem_sidecar_still_wins_over_embedded_fallback(self, api, tmp_path, monkeypatch):
        """If the filesystem sidecar exists, it is the ground truth and wins
        over any embedded_srt fallback."""
        # detect_existing_target_for_lang returns 'srt' → filesystem says yes.
        monkeypatch.setattr(
            "translator.detect_existing_target_for_lang",
            lambda fp, lang: "srt",
        )
        with api.application.app_context():
            from db.models.core import WantedItem
            from db.models.standalone import StandaloneSeries
            from extensions import db

            series = StandaloneSeries(
                id=9002,
                title="Standalone Movie",
                year=2024,
                folder_path=str(tmp_path / "series2"),
                season_count=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.session.add(series)
            db.session.flush()

            now = datetime.now(UTC)
            item = WantedItem(
                title="Episode 1",
                file_path=str(tmp_path / "ep01.mkv"),
                standalone_series_id=9002,
                target_language="de",
                missing_languages='["de"]',
                status="wanted",
                existing_sub="embedded_srt",
                instance_name="",
                item_type="series",
                season_episode="S01E01",
                added_at=now,
                updated_at=now,
            )
            db.session.add(item)
            db.session.commit()

        r = api.get("/api/v1/library/series/9002")
        payload = r.get_json()
        assert payload["episodes"][0]["subtitles"]["de"] == "srt"
