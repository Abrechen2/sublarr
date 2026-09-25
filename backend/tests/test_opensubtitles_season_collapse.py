"""OpenSubtitles season-1 collapse must not hand back another season's episode.

Prod, September 2026: 78 "season-1 collapse found" lines in four days, and the
ones that got saved were all the wrong episode. Farming Life S02E07 received
``S01E07-A_Hospitable_Heart``, Kim Possible S03E06 ``S01E06_-_Bueno_Nacho``,
South Park S29E01 ``South.Park.S01E01``. The retry asked OpenSubtitles for
S01E<same number>, and a result from season 1 merely missed the ``season``
bonus — series + episode still scored high enough to win.

The collapse is only legitimate for anime that OpenSubtitles numbers as one
long season: Sonarr S02E03 is OS S01E15 when the absolute number is 15.
"""

from unittest.mock import MagicMock

from providers.base import VideoQuery
from providers.opensubtitles import OpenSubtitlesProvider


def _item(season, episode, file_name, title="Farming Life in Another World", **attrs):
    return {
        "attributes": {
            "language": "de",
            "release": attrs.pop("release", ""),
            "files": [
                {"file_id": hash((season, episode, file_name)) % 10**6, "file_name": file_name}
            ],
            "feature_details": {
                "season_number": season,
                "episode_number": episode,
                "title": title,
            },
            **attrs,
        }
    }


def _response(items):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": items}
    return resp


def _provider(responder):
    """Provider whose session answers each /subtitles call via ``responder(params)``."""
    provider = OpenSubtitlesProvider(api_key="test-key")
    provider.session = MagicMock()
    provider.session.get.side_effect = lambda url, params=None, **kw: _response(
        responder(params or {})
    )
    return provider


def _query(season, episode, absolute=None, title="Farming Life in Another World"):
    return VideoQuery(
        series_title=title,
        season=season,
        episode=episode,
        absolute_episode=absolute,
        languages=["de"],
    )


def _requested(provider):
    return [call.kwargs["params"] for call in provider.session.get.call_args_list]


class TestSeasonOneCollapse:
    def test_no_absolute_number_never_returns_season_one_episode(self):
        """Farming Life S02E07: the S01E07 upload must not come back."""

        def responder(params):
            if params.get("season_number") == 1:
                return [_item(1, 7, "S01E07-A_Hospitable_Heart.srt")]
            return []

        provider = _provider(responder)
        results = provider.search(_query(2, 7))

        assert results == []
        # Nothing acceptable can come back, so the request is not spent either.
        assert all(p.get("season_number") != 1 for p in _requested(provider))

    def test_absolute_numbered_anime_is_still_found(self):
        """Sonarr S02E03 == OS S01E15 when the absolute number is 15."""

        def responder(params):
            if params.get("season_number") == 1 and params.get("episode_number") == 15:
                return [_item(1, 15, "[Group] Show - 15.srt", title="Show")]
            return []

        provider = _provider(responder)
        results = provider.search(_query(2, 3, absolute=15, title="Show"))

        assert [r.filename for r in results] == ["Group_Show_-_15.srt"]
        assert "episode" in results[0].matches
        collapse = [p for p in _requested(provider) if p.get("season_number") == 1]
        assert collapse and all(p["episode_number"] == 15 for p in collapse)

    def test_collapse_drops_results_that_are_not_the_absolute_episode(self):
        def responder(params):
            if params.get("season_number") == 1:
                return [
                    _item(1, 15, "Show - 15.srt", title="Show"),
                    _item(1, 3, "Show.S01E03.srt", title="Show"),
                ]
            return []

        provider = _provider(responder)
        results = provider.search(_query(2, 3, absolute=15, title="Show"))

        assert [r.filename for r in results] == ["Show_-_15.srt"]

    def test_collapse_drops_filename_naming_a_different_season_episode(self):
        """Feature says S01E15 (== absolute) but the file itself is S01E03."""

        def responder(params):
            if params.get("season_number") == 1:
                return [_item(1, 15, "Show.S01E03.srt", title="Show")]
            return []

        provider = _provider(responder)
        assert provider.search(_query(2, 3, absolute=15, title="Show")) == []

    def test_imdb_title_fallback_follows_the_same_rule(self):
        """Fallback 2 (title query without IMDB) must not reintroduce S01E<same>."""

        def responder(params):
            if params.get("season_number") == 1:
                return [_item(1, 21, "A.Certain.Magical.Index.S01E21.srt", title="Index")]
            return []

        provider = _provider(responder)
        query = _query(3, 21, title="Index")
        query.imdb_id = "tt1234567"
        assert provider.search(query) == []


class TestSeasonContradictionInPrimarySearch:
    def test_filename_season_contradicting_query_is_rejected(self):
        """Kim Possible S03E06 must not accept ``Kim.Possible.S01E06``."""

        def responder(params):
            return [
                _item(3, 6, "Kim.Possible.S01E06_-_Bueno_Nacho.srt", title="Kim Possible"),
                _item(3, 6, "Kim.Possible.S03E06.srt", title="Kim Possible"),
            ]

        provider = _provider(responder)
        results = provider.search(_query(3, 6, title="Kim Possible"))

        assert [r.filename for r in results] == ["Kim.Possible.S03E06.srt"]

    def test_release_season_contradicting_query_is_rejected(self):
        def responder(params):
            return [_item(29, 1, "sub.srt", title="South Park", release="South.Park.S01E01.720p")]

        provider = _provider(responder)
        assert provider.search(_query(29, 1, title="South Park")) == []

    def test_feature_season_contradicting_query_is_rejected(self):
        def responder(params):
            return [_item(1, 12, "Clevatess - 12.srt", title="Clevatess")]

        provider = _provider(responder)
        assert provider.search(_query(2, 12, title="Clevatess")) == []

    def test_matching_result_without_season_in_name_is_kept(self):
        def responder(params):
            return [_item(2, 7, "Farming Life - 07.srt")]

        provider = _provider(responder)
        results = provider.search(_query(2, 7))

        assert len(results) == 1
        assert {"season", "episode"} <= results[0].matches

    def test_hash_match_is_trusted_over_season_numbering(self, tmp_path):
        """A moviehash match identifies the file itself; numbering differences don't matter."""
        video = tmp_path / "Show.S02E03.mkv"
        video.write_bytes(b"x" * 1024)

        def responder(params):
            return [_item(1, 15, "Show.S01E15.srt", title="Show", moviehash_match=True)]

        provider = _provider(responder)
        query = _query(2, 3, title="Show")
        query.file_path = str(video)
        query.file_hash = "abcdef0123456789"
        results = provider.search(query)

        assert len(results) == 1
        assert "hash" in results[0].matches

    def test_season_zero_is_not_a_contradiction(self):
        def responder(params):
            return [_item(0, 12, "Clevatess - 12.srt", title="Clevatess")]

        provider = _provider(responder)
        assert len(provider.search(_query(2, 12, title="Clevatess"))) == 1
