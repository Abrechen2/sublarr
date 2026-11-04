"""Jimaku: only the queried series, season and episode (names from the live API, 2026-11)."""

from unittest.mock import MagicMock

import pytest

from providers.base import VideoQuery
from providers.jimaku import JimakuProvider
from providers.jimaku_matching import (
    entry_season,
    file_matches_episode,
    is_later_part,
    search_names,
    select_entries,
)

MUSHOKU = [
    {
        "id": 1927,
        "name": "Mushoku Tensei II: Isekai Ittara Honki Dasu",
        "english_name": "Mushoku Tensei: Jobless Reincarnation Season 2",
    },
    {
        "id": 2699,
        "name": "Mushoku Tensei II: Isekai Ittara Honki Dasu Part 2",
        "english_name": "Mushoku Tensei: Jobless Reincarnation Season 2 Part 2",
    },
    {
        "id": 12216,
        "name": "Mushoku Tensei III: Isekai Ittara Honki Dasu",
        "english_name": "Mushoku Tensei: Jobless Reincarnation Season 3",
    },
    {
        "id": 1426,
        "name": "Mushoku Tensei: Isekai Ittara Honki Dasu",
        "english_name": "Mushoku Tensei: Jobless Reincarnation",
    },
    {
        "id": 3547,
        "name": "Mushoku Tensei: Isekai Ittara Honki Dasu Part 2",
        "english_name": "Mushoku Tensei: Jobless Reincarnation Cour 2",
    },
]
FRIEREN = [
    {"id": 729, "name": "Sousou no Frieren", "english_name": "Frieren: Beyond Journey’s End"},
    {
        "id": 11446,
        "name": "Sousou no Frieren 2nd Season",
        "english_name": "Frieren: Beyond Journey’s End Season 2",
        "japanese_name": "葬送のフリーレン 第2期",
    },
    {
        "id": 7350,
        "name": "Dragon Ball: Ossu! Kaette Kita Son Goku to Nakama-tachi!!",
        "english_name": "Dragon Ball: Yo! Son Goku and His Friends Return!!",
    },
]


def _q(title="Mushoku Tensei: Jobless Reincarnation", season=1, episode=5, **kw):
    return VideoQuery(series_title=title, season=season, episode=episode, languages=["ja"], **kw)


def _ids(entries):
    return [e["id"] for e in entries]


@pytest.mark.parametrize(
    ("entry", "season"),
    [(MUSHOKU[0], 2), (MUSHOKU[2], 3), (MUSHOKU[3], None), (MUSHOKU[4], None), (FRIEREN[1], 2)],
)
def test_entry_season(entry, season):
    assert entry_season(entry) == season


def test_later_part():
    assert is_later_part(MUSHOKU[4]) and is_later_part(MUSHOKU[1])
    assert not is_later_part(MUSHOKU[3])


def test_season_one_keeps_the_unmarked_entries_first_part_first():
    assert _ids(select_entries(MUSHOKU, _q(season=1))) == [1426, 3547]


def test_a_later_season_keeps_its_own_entries():
    assert _ids(select_entries(MUSHOKU, _q(season=2))) == [1927, 2699]
    assert _ids(select_entries(MUSHOKU, _q(season=3))) == [12216]


def test_other_series_are_dropped():
    assert _ids(select_entries(FRIEREN, _q("Frieren: Beyond Journey's End", 1, 3))) == [729]


def test_no_title_match_keeps_the_old_behaviour():
    assert _ids(select_entries(MUSHOKU, _q("Arbeitslos wiedergeboren"))) == _ids(MUSHOKU)


@pytest.mark.parametrize(
    ("name", "fits"),
    [
        ("[SubsPlease] Mushoku Tensei - 05v2 (1080p) [DBC034A9].ja.srt", True),
        ("無職転生.～異世界行ったら本気だす～.S01E05.お嬢様と暴力.WEBRip.Netflix.ja[cc].srt", True),
        (
            "[Nekomoe kissaten&VCB-Studio] Mushoku Tensei ~Isekai Ittara Honki Dasu~ [05][Ma10p_1080p].ass",
            True,
        ),
        ("[Netflix] Mushoku Tensei Jobless Reincarnation 05 (non SDH).srt", True),
        ("[SubsPlease] Mushoku Tensei - 06 (1080p) [DBC034A9].ja.srt", False),
        ("無職転生.～異世界行ったら本気だす～.S02E05.WEBRip.Netflix.ja[cc].srt", False),
        ("[NanakoRaws] Sousou no Frieren - 01-04 (1080p).ass", False),
        ("Mushoku Tensei OP.ass", False),
    ],
)
def test_file_matches_episode(name, fits):
    assert file_matches_episode(name, _q(), 5) is fits


def test_a_multi_episode_video_takes_its_range():
    assert file_matches_episode(
        "[NanakoRaws] Sousou no Frieren - 01-04 (1080p).ass",
        _q(episode=3, episodes=[1, 2, 3, 4]),
        3,
    )


def test_search_names():
    q = _q("Frieren: Beyond Journey's End", series_aliases=[("Sousou no Frieren", -1, None)])
    assert search_names(q) == ["Frieren: Beyond Journey's End", "Sousou no Frieren", "Frieren"]


def test_search_offers_only_the_episode_with_its_matches():
    provider = JimakuProvider(api_key="k")
    provider.session = MagicMock()
    provider._search_by_name = MagicMock(return_value=MUSHOKU)
    files = {
        3: "[SubsPlease] Mushoku Tensei S3 - 05 (1080p).ja.srt",
        1426: "[SubsPlease] Mushoku Tensei - 05v2 (1080p) [DBC034A9].ja.srt",
        1427: "[SubsPlease] Mushoku Tensei - 06 (1080p) [DBC034A9].ja.srt",
    }
    provider._get_entry_files = MagicMock(
        side_effect=lambda entry_id, _q: (
            [
                (files[1426], "u1", False),
                (files[1427], "u2", False),
                ("Mushoku Tensei.zip", "u3", True),
            ]
            if entry_id == 1426
            else [(files[3], "u4", False)]
        )
    )
    results = provider.search(_q())
    names = {r.filename: r.matches for r in results}
    assert set(names) == {files[1426], "Mushoku Tensei.zip"}
    assert {"episode", "season"} <= names[files[1426]]
    assert "episode" not in names["Mushoku Tensei.zip"]
    assert [c.args[0] for c in provider._get_entry_files.call_args_list] == [1426, 3547]


def test_name_search_falls_back_to_other_names():
    provider = JimakuProvider(api_key="k")
    provider.session = MagicMock()
    provider._search_by_name = MagicMock(side_effect=[[], FRIEREN])
    provider._get_entry_files = MagicMock(return_value=[])
    provider.search(_q("Frieren: Beyond Journey's End", 1, 3))
    assert [c.args[0] for c in provider._search_by_name.call_args_list] == [
        "Frieren: Beyond Journey's End",
        "Frieren",
    ]


@pytest.mark.parametrize(
    ("name", "lang"),
    [
        ("[Nekomoe kissaten] Akiba Maid Sensou - 04 [WebRip][JPN].ass", "ja"),
        ("[SubsPlease] Mushoku Tensei - 05v2 (1080p) [DBC034A9].ja.srt", "ja"),
        ("Pokemon Horizon.S01E01.Amazon.ja[sdh].srt", "ja"),
        ("Show - 01 [ENG].ass", "en"),
        ("Show.S01E01.en.srt", "en"),
        # Two languages in one file: a clean subtitle in neither.
        ("[Nekomoe kissaten] Akiba Maid Sensou [04][BDRip][CHS, JPN].ass", None),
        ("[SubsPlease] Sousou no Frieren - 03 (1080p) [7EF3F175]_ja-en.ass", None),
        ("[NanakoRaws] Otonari no Tenshi-sama S01E03 (AT-X 1080p HEVC AAC).ass", None),
        ("Show [1080p][Web].ass", None),
    ],
)
def test_language_from_tags(name, lang):
    from providers.jimaku_matching import language_from_tags

    assert language_from_tags(name) == lang
