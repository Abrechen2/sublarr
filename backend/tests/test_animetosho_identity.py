"""GH #210: TYBW episode 21 must not become original Bleach absolute 21."""

from unittest.mock import MagicMock

import pytest

from providers.animetosho import AnimeToshoProvider
from providers.animetosho_matching import match_entry, match_release
from providers.base import VideoQuery


@pytest.fixture
def query():
    return VideoQuery(
        series_title="Bleach", season=2, episode=1, absolute_episode=21, languages=["en"]
    )


def _file(name, attach_id=1):
    return {
        "filename": name,
        "attachments": [
            {"id": attach_id, "type": "subtitle", "info": {"lang": "eng", "codec": "ASS"}}
        ],
    }


@pytest.mark.parametrize(
    "title",
    [
        "[LostYears] Bleach Thousand-Year Blood War - S17E21 (WEB 1080p x264 AAC) [Dual Audio]",
        "Bleach S17E21 1080p WEB H.264 AAC -Tsundere-Raws (DSNP).mkv",
        "[ZigZag] BLEACH: Thousand-Year Blood War S02E08 [1080p] (Bleach S17E21)",
        "[Pro Bono] Bleach Sennen Kessen-hen - 21.5",
        "[Group] Bleach Thousand-Year Blood War - 21 [1080p]",
        "[Group] Bleach - 21.5 [1080p]",
        "[Group] Bleach - 387 [1080p]",
        "[Group] Bleach S02E21 [1080p]",
        "[DKB] Bleach - Sennen Kessen-hen - 21 [1080p][HEVC x265 10bit][Multi-Subs][weekly]",
        "[Nokiya-Fansubs] Bleach - Sennen Kessen-hen - 21 | Thousand-Year Blood War [1080p AMZN WEB-DL]",
    ],
)
def test_rejects_live_sequel_titles_and_wrong_numbering(query, title):
    assert match_entry({"title": title}, query) is None


@pytest.mark.parametrize(
    "title",
    [
        "[Group] Bleach - 21 [1080p].mkv",
        "[Group] Bleach - 21v2 [1080p].mkv",
        "Bleach.S02E01.1080p.mkv",
        "BLEACH - 0021.mkv",
    ],
)
def test_accepts_original_episode_in_absolute_or_season_order(query, title):
    assert {"series", "episode"} <= match_entry({"title": title}, query)


def test_even_a_matching_feed_id_cannot_override_a_wrong_season(query):
    # The live .xyz feed really marks some S17E21 releases as AniDB 2369.
    query.anidb_id = 2369
    assert match_entry({"title": "Bleach S17E21 1080p.mkv", "anidb_aid": 2369}, query) is None


@pytest.mark.parametrize("field,value", [("anidb_aid", 15449), ("anidb_eid", 260810)])
def test_conflicting_feed_ids_are_rejected(query, field, value):
    query.anidb_id = 2369
    query.anidb_episode_id = 30266
    assert match_entry({"title": "Bleach - 21 [1080p]", field: value}, query) is None


def test_missing_ids_do_not_reject_a_proven_title_match(query):
    query.anidb_id = 2369
    assert {"series", "episode"} <= match_entry({"title": "Bleach - 21 [1080p]"}, query)


def test_title_substrings_do_not_establish_series_identity(query):
    assert match_release("[Group] Bleach Something Else - 21 [1080p]", query) is None


def test_pack_only_returns_the_attachment_for_the_requested_file(query):
    provider = AnimeToshoProvider()
    provider._fetch_torrent_detail = MagicMock(
        return_value={
            "files": [
                _file("Bleach - 20 [1080p].mkv", 20),
                _file("Bleach - 21 [1080p].mkv", 21),
                _file("Bleach - 22 [1080p].mkv", 22),
                _file("Bleach Thousand-Year Blood War - 21 [1080p].mkv", 387),
                _file("extras.mkv", 99),
            ]
        }
    )
    results = provider._process_entry(
        {"id": 1, "title": "Bleach - 01-366 [1080p]", "num_files": 5}, query
    )
    assert [r.subtitle_id for r in results] == ["1:21"]
    assert {"series", "episode"} <= results[0].matches


def test_single_file_can_inherit_an_unambiguous_episode(query):
    provider = AnimeToshoProvider()
    provider._fetch_torrent_detail = MagicMock(return_value={"files": [_file("")]})
    results = provider._process_entry(
        {"id": 1, "title": "Bleach - 21 [1080p]", "num_files": 1}, query
    )
    assert len(results) == 1


def test_unnumbered_pack_files_cannot_inherit_the_feed_episode(query):
    provider = AnimeToshoProvider()
    provider._fetch_torrent_detail = MagicMock(return_value={"files": [_file(""), _file("", 2)]})
    assert (
        provider._process_entry({"id": 1, "title": "Bleach - 21 [1080p]", "num_files": 2}, query)
        == []
    )


def test_wrong_entries_do_not_exhaust_the_eight_detail_requests(query):
    provider = AnimeToshoProvider()
    provider.session = MagicMock()
    response = provider.session.get.return_value
    response.status_code = 200
    response.json.return_value = [
        {"id": n, "title": "Bleach S17E21 1080p.mkv", "num_files": 1} for n in range(10)
    ] + [{"id": 20, "title": "Bleach S02E01 1080p.mkv", "num_files": 1}]
    provider._fetch_torrent_detail = MagicMock(return_value={"files": [_file("Bleach S02E01.mkv")]})
    results = provider.search(query)
    assert len(results) == 1
    provider._fetch_torrent_detail.assert_called_once_with(20)


@pytest.mark.parametrize("episode_id", [None, 30266])
def test_api_eid_is_an_identity_never_the_absolute_number(query, episode_id):
    query.anidb_id = 2369
    query.anidb_episode_id = episode_id
    provider = AnimeToshoProvider()
    provider.session = MagicMock()
    provider.session.get.return_value.status_code = 200
    provider.session.get.return_value.json.return_value = []
    provider.search(query)
    params = provider.session.get.call_args.kwargs["params"]
    assert params["q"] == "Bleach 21"
    assert params.get("eid") == episode_id
    if episode_id is None:
        assert "aid" not in params


def test_movie_matching_still_uses_title_and_year():
    query = VideoQuery(title="Akira", year=1988)
    assert "title" in match_entry({"title": "Akira (1988) [1080p]"}, query)
    assert match_entry({"title": "Akira (2016) [1080p]"}, query) is None


def test_a_full_series_name_with_a_subtitle_still_matches_live_release_names():
    query = VideoQuery(series_title="Frieren: Beyond Journey's End", season=1, episode=1)
    entry = {"title": "[BlackRabbit] Frieren - Beyond Journey's End (2023) - S01 v2 [Bluray-1080p]"}
    assert {"series", "season"} <= match_entry(entry, query)
    filename = (
        "Frieren - Beyond Journey's End (2023) - S01E01 - The Journeys End [Bluray-1080p].mkv"
    )
    assert {"series", "season", "episode"} <= match_release(filename, query)


def test_four_digit_absolute_episodes_are_not_compact_season_numbers():
    query = VideoQuery(series_title="One Piece", season=21, episode=189, absolute_episode=1080)
    assert {"series", "episode"} <= match_release("[Group] One Piece - 1080 [1080p].mkv", query)
