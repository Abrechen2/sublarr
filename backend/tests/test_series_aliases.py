"""Sequels named by their own title, resolved through Sonarr's season-scoped aliases.

Prod 1.17.0-rc.6 replay (6,384 kept downloads): the episode gate dropped 199
saved subtitles a fresh search would need, mostly sequels numbered per season
with the season only in the title: "Strike Witches - Road to Berlin - 05" for
S03E05, "Psycho-Pass 2 - 01" for S02E01. Sonarr lists those titles as
alternateTitles with a sceneSeasonNumber. A title scoped to the queried season
permits its own numbering; a title scoped to another season is another season.
The bare series title keeps the Clevatess rule (S02E12 is not "Clevatess - 12").
"""

from __future__ import annotations

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.episode_gate import episode_gate_reason

# As Sonarr returns them: (title, seasonNumber, sceneSeasonNumber).
STRIKE_WITCHES = [("Strike Witches 2", None, 2), ("Strike Witches - Road to Berlin", None, 3)]
BAHAMUT = [
    ("Shingeki no Bahamut - Virgin Soul", None, 2),
    ("Shingeki no Bahamut - Genesis", None, 1),
]
CLEVATESS = [
    ("Clevatess S2", None, 2),
    ("Clevatess II", None, 2),
    ("Clevatess-Majuu no Ou", None, -1),
]
PSYCHO_PASS = [("Psycho-Pass 2", None, 2), ("Psycho-Pass 3", None, 3)]
CRIMINAL_MINDS = [("Criminal Minds Evolution", 16, 1), ("Mentes criminales", -1, None)]
K_ON = [("K-ON!", None, 1), ("K-ON!!", None, 2), ("K-On!! S2", None, 2)]
DR_STONE = [("Dr. Stone: New World", None, 3), ("Dr. Stone: Science Future", None, 4)]


def _q(series, season, episode, absolute, aliases, scene_season=None):
    return VideoQuery(
        series_title=series,
        season=season,
        episode=episode,
        sonarr_absolute_episode=absolute,
        series_aliases=aliases,
        scene_season=scene_season,
        languages=["de"],
    )


def _r(release):
    return SubtitleResult(
        provider_name="animetosho",
        subtitle_id="1",
        language="de",
        format=SubtitleFormat.ASS,
        release_info=release,
        matches={"series", "episode"},
    )


class TestGate:
    @pytest.mark.parametrize(
        "release",
        [
            "[Pantsu]_Strike_Witches_-_Road_to_Berlin_-_05_[1080p][2BF39ADA]",
            "[Golumpa] Strike Witches - Road to Berlin - 05 [English Dub]",
        ],
    )
    def test_a_title_scoped_to_the_queried_season_numbers_its_own_episodes(self, release):
        query = _q("Strike Witches", 3, 5, 33, STRIKE_WITCHES)
        assert episode_gate_reason(_r(release), query) == ""

    def test_its_numbering_must_still_be_the_episode(self):
        query = _q("Strike Witches", 3, 5, 33, STRIKE_WITCHES)
        reason = episode_gate_reason(_r("Strike Witches - Road to Berlin - 06 [1080p]"), query)
        assert "episode 6" in reason

    def test_a_numbered_sequel_title_is_its_season(self):
        query = _q("Psycho-Pass", 2, 1, 23, PSYCHO_PASS)
        assert episode_gate_reason(_r("[Erai-raws] Psycho-Pass 2 - 01 [1080p]"), query) == ""

    def test_a_title_scoped_to_another_season_is_that_season(self):
        # Genesis is season 1; its first episode is not Virgin Soul's.
        query = _q("Rage of Bahamut", 2, 1, 13, BAHAMUT)
        reason = episode_gate_reason(
            _r("[Mawaru] Shingeki no Bahamut Genesis - 01v2 (BD 1080p)"), query
        )
        assert "season 1" in reason

    def test_clevatess_bare_title_keeps_the_season_one_rule(self):
        query = _q("Clevatess", 2, 12, 24, CLEVATESS)
        assert "episode 12" in episode_gate_reason(_r("[SubsPlease] Clevatess - 12 (1080p)"), query)

    def test_clevatess_season_two_alias_numbers_season_two(self):
        query = _q("Clevatess", 2, 12, 24, CLEVATESS)
        assert episode_gate_reason(_r("[SubsPlease] Clevatess II - 12 (1080p)"), query) == ""

    def test_an_unscoped_alias_is_the_bare_title(self):
        query = _q("Clevatess", 2, 12, 24, CLEVATESS)
        reason = episode_gate_reason(_r("[Group] Clevatess-Majuu no Ou - 12 [1080p]"), query)
        assert "episode 12" in reason

    def test_an_explicit_sxxeyy_wins_over_the_title(self):
        query = _q("Strike Witches", 3, 5, 33, STRIKE_WITCHES)
        reason = episode_gate_reason(_r("Strike Witches - Road to Berlin S01E05"), query)
        assert "S01E05" in reason

    def test_without_aliases_nothing_changes(self):
        query = _q("Strike Witches", 3, 5, 33, [])
        reason = episode_gate_reason(_r("Strike Witches - Road to Berlin - 05 [1080p]"), query)
        assert "episode 5" in reason


class TestCodexReviewOfRc7:
    """Counterexamples from the independent review of the rc.7 draft."""

    def test_a_library_season_wins_over_the_scene_season(self):
        # Scene season 1, library season 16: S16E05 is the Evolution's fifth.
        query = _q("Criminal Minds", 16, 5, None, CRIMINAL_MINDS)
        assert episode_gate_reason(_r("Criminal Minds Evolution - 05 [1080p]"), query) == ""

    def test_a_scene_season_is_compared_with_the_episodes_scene_season(self):
        aliases = [("Show Kanketsu-hen", None, 2)]
        query = _q("Show", 3, 4, 28, aliases, scene_season=2)
        assert episode_gate_reason(_r("[Group] Show Kanketsu-hen - 04 [1080p]"), query) == ""

    def test_one_name_for_two_seasons_proves_nothing(self):
        # K-ON! and K-ON!! are the same words: neither season is proven, so the
        # base-title rule decides (absolute 15 for S02E01).
        query = _q("K-ON!", 2, 1, 15, K_ON)
        assert "episode 1," in episode_gate_reason(_r("[Tsundere] K-On!! - 01 [BD]"), query)

    def test_a_wrong_local_number_under_its_own_title_is_not_rescued_by_the_absolute(self):
        query = _q("Show", 2, 1, 13, [("Show II", None, 2)])
        assert "episode 13" in episode_gate_reason(_r("[Group] Show II - 13 [1080p]"), query)

    def test_an_absolute_number_the_season_cannot_hold_is_kept(self):
        aliases = [("Shingeki no Kyojin (The Final Season)", None, 4)]
        query = _q("Attack on Titan", 4, 1, 60, aliases)
        query.season_size = 30
        release = "Shingeki no Kyojin (The Final Season) - 60 (1920x1080 10bit AAC)"
        assert episode_gate_reason(_r(release), query) == ""

    def test_an_absolute_number_the_season_could_hold_is_not(self):
        query = _q("Show", 2, 1, 13, [("Show II", None, 2)])
        query.season_size = 24
        assert "episode 13" in episode_gate_reason(_r("[Group] Show II - 13 [1080p]"), query)

    def test_a_season_word_inside_the_alias_is_kept(self):
        query = _q("Show", 2, 1, 13, [("Show Season 2", None, 2)])
        assert episode_gate_reason(_r("[Group] Show Season 2 - 01 [1080p]"), query) == ""

    def test_a_trailing_number_is_the_episode_not_the_alias(self):
        # "Psycho-Pass - 2" is season 1's second, not "Psycho-Pass 2".
        query = _q("Psycho-Pass", 1, 2, 2, PSYCHO_PASS)
        assert episode_gate_reason(_r("[Group] Psycho-Pass - 2 [1080p]"), query) == ""

    def test_a_split_cour_after_the_alias_proves_nothing(self):
        query = _q("Dr. STONE", 3, 21, 45, DR_STONE)
        reason = episode_gate_reason(
            _r("[Erai-raws] Dr Stone - New World Part 2 - 10 [1080p]"), query
        )
        assert "by its title" not in reason


class TestSpacedEpisode:
    def test_s01e_space_07_is_s01e07(self):
        query = _q("Nagatoro", 1, 7, 7, [])
        assert (
            episode_gate_reason(
                _r("[Crunchyroll] DON'T TOY WITH ME, MISS NAGATORO S01E 07 Senpai"), query
            )
            == ""
        )

    def test_s01e_space_07_is_not_s02e07(self):
        query = _q("Nagatoro", 2, 7, 19, [])
        reason = episode_gate_reason(
            _r("[Crunchyroll] DON'T TOY WITH ME, MISS NAGATORO S01E 07 Senpai"), query
        )
        assert "S01E07" in reason


class TestAnimeToshoMatching:
    def test_a_season_scoped_sequel_title_matches_its_season(self):
        from providers.animetosho_matching import match_release

        query = _q("Strike Witches", 3, 5, 33, STRIKE_WITCHES)
        assert match_release("[Golumpa] Strike Witches - Road to Berlin - 05 [English Dub]", query)

    def test_a_sequel_title_of_another_season_does_not(self):
        from providers.animetosho_matching import match_release

        query = _q("Rage of Bahamut", 2, 1, 13, BAHAMUT)
        assert (
            match_release("[Mawaru] Shingeki no Bahamut - Genesis - 01v2 (BD 1080p)", query) is None
        )

    def test_the_bare_title_keeps_its_rule(self):
        from providers.animetosho_matching import match_release

        query = _q("Clevatess", 2, 12, 24, CLEVATESS)
        assert match_release("[SubsPlease] Clevatess - 12 (1080p)", query) is None


def test_animetosho_keeps_an_absolute_number_the_season_cannot_hold():
    from providers.animetosho_matching import match_release

    aliases = [("Shingeki no Kyojin (The Final Season)", None, 4)]
    query = _q("Shingeki no Kyojin (The Final Season)", 4, 1, 60, aliases)
    query.series_title = "Attack on Titan"
    query.season_size = 30
    assert match_release("Shingeki no Kyojin (The Final Season) - 60 (1920x1080 10bit AAC)", query)


def test_animetosho_rejects_a_wrong_local_number_under_the_seasons_title():
    from providers.animetosho_matching import match_release

    query = _q("Strike Witches", 3, 5, 33, STRIKE_WITCHES)
    query.season_size = 12
    assert (
        match_release("[Golumpa] Strike Witches - Road to Berlin - 06 [English Dub]", query) is None
    )
