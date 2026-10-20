"""Sonarr's absolute number and AnimeTosho's bare episode numbers.

Clevatess S02E12 is Sonarr absolute 24. ``[SubsPlease] Clevatess - 12`` is
season 1's twelfth episode; without a season it can only be S02E12 when the
query carries no other season than 1.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from providers.animetosho_matching import match_release
from providers.base import VideoQuery

SUBSPLEASE_12 = "[SubsPlease] Clevatess - 12 (1080p) [ABCDEF01].mkv"


def _query(**kwargs) -> VideoQuery:
    kwargs.setdefault("season", 2)
    kwargs.setdefault("episode", 12)
    return VideoQuery(series_title="Clevatess", languages=["en"], **kwargs)


class TestAnimeToshoBareEpisode:
    def test_bare_number_does_not_match_a_later_season_without_absolute(self):
        assert match_release(SUBSPLEASE_12, _query()) is None

    def test_bare_number_does_not_match_when_the_absolute_differs(self):
        assert match_release(SUBSPLEASE_12, _query(absolute_episode=24)) is None

    def test_bare_number_does_not_match_when_the_sonarr_absolute_differs(self):
        assert match_release(SUBSPLEASE_12, _query(sonarr_absolute_episode=24)) is None

    def test_bare_absolute_matches(self):
        title = "[SubsPlease] Clevatess - 24 (1080p).mkv"
        assert {"series", "episode"} <= match_release(title, _query(absolute_episode=24))

    def test_bare_sonarr_absolute_matches(self):
        title = "[SubsPlease] Clevatess - 24 (1080p).mkv"
        assert {"series", "episode"} <= match_release(title, _query(sonarr_absolute_episode=24))

    def test_bare_number_still_matches_season_one(self):
        assert {"series", "episode"} <= match_release(SUBSPLEASE_12, _query(season=1))

    def test_explicit_season_two_still_matches(self):
        title = "[Group] Clevatess S02E12 [1080p].mkv"
        assert {"series", "season", "episode"} <= match_release(title, _query())


class TestSonarrAbsoluteEpisode:
    def test_get_episode_metadata_returns_absolute_number(self):
        from sonarr_client import SonarrClient

        client = SonarrClient("http://sonarr", "key")
        series = {"id": 1084, "title": "Clevatess", "tvdbId": 1, "seriesType": "standard"}
        episode = {"id": 7, "seasonNumber": 2, "episodeNumber": 12, "absoluteEpisodeNumber": 24}
        with (
            patch.object(client, "get_series_by_id", return_value=series),
            patch.object(client, "get_episode_by_id", return_value=episode),
            patch.dict("sys.modules", {"anidb_mapper": MagicMock(get_anidb_id=lambda **k: None)}),
        ):
            meta = client.get_episode_metadata(1084, 7)
        assert meta["absolute_episode"] == 24

    def _enrich(self, meta):
        from wanted_search.metadata_enrichers import _enrich_from_sonarr

        sonarr = MagicMock()
        sonarr.get_episode_metadata.return_value = meta
        query = VideoQuery()
        with patch("sonarr_client.get_sonarr_client", return_value=sonarr):
            assert _enrich_from_sonarr(
                query, {"id": 1, "sonarr_series_id": 1084, "sonarr_episode_id": 7}
            )
        return query

    def test_enrich_keeps_sonarr_absolute_for_matching_only(self):
        # Providers switch to absolute search when absolute_episode is set
        # (Jimaku, SubDL, OpenSubtitles collapse); Sonarr's continuous number
        # must not flip that switch for every series.
        query = self._enrich(
            {"series_title": "Clevatess", "season": 2, "episode": 12, "absolute_episode": 24}
        )
        assert query.sonarr_absolute_episode == 24
        assert query.absolute_episode is None
        assert query.matching_absolute_episode == 24

    def test_matching_absolute_prefers_the_authoritative_number(self):
        query = VideoQuery(absolute_episode=13, sonarr_absolute_episode=24)
        assert query.matching_absolute_episode == 13

    @pytest.fixture
    def anidb_repo(self, monkeypatch):
        from db.repositories import anidb

        repo = MagicMock()
        monkeypatch.setattr(anidb, "AnidbRepository", lambda: repo)
        return repo

    def _resolve(self, query):
        from wanted_search.metadata_enrichers import _resolve_anidb_absolute_episode

        _resolve_anidb_absolute_episode(
            query, {"id": 1, "item_type": "episode", "sonarr_series_id": 1084}
        )

    def test_absolute_order_without_mapping_falls_back_to_sonarr(self, anidb_repo):
        anidb_repo.get_absolute_order.return_value = True
        anidb_repo.get_anidb_absolute.return_value = None
        query = VideoQuery(tvdb_id=1, season=2, episode=12, sonarr_absolute_episode=24)
        self._resolve(query)
        assert query.absolute_episode == 24

    def test_anidb_mapping_beats_sonarr(self, anidb_repo):
        anidb_repo.get_absolute_order.return_value = True
        anidb_repo.get_anidb_absolute.return_value = 13
        query = VideoQuery(tvdb_id=1, season=2, episode=12, sonarr_absolute_episode=24)
        self._resolve(query)
        assert query.absolute_episode == 13

    def test_shoko_value_is_not_overridden(self, anidb_repo):
        anidb_repo.get_absolute_order.return_value = True
        query = VideoQuery(
            tvdb_id=1, season=2, episode=12, absolute_episode=12, sonarr_absolute_episode=24
        )
        self._resolve(query)
        assert query.absolute_episode == 12

    def test_without_absolute_order_sonarr_absolute_stays_matching_only(self, anidb_repo):
        anidb_repo.get_absolute_order.return_value = False
        query = VideoQuery(tvdb_id=1, season=2, episode=12, sonarr_absolute_episode=24)
        self._resolve(query)
        assert query.absolute_episode is None
