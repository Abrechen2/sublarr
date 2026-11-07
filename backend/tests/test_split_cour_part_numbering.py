"""Split-cour releases number each part from 1 ("Part 2 - 05").

Prod 2026-10-31: Mushoku Tensei S02 (24 episodes in Sonarr, two cours of 12)
got ``[Erai-raws] Mushoku Tensei II - Isekai Ittara Honki Dasu Part 2 - 05``
saved as S02E05 (it is S02E17), and "Part 2 - 07" flip-flopped onto S02E07.
Both the episode gate and AnimeTosho's own matching read the bare number as
the season's episode.
"""

from __future__ import annotations

from providers.animetosho_matching import match_release
from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.episode_gate import episode_gate_reason

ERAI_05 = (
    "[Erai-raws] Mushoku Tensei II - Isekai Ittara Honki Dasu Part 2 - 05 [1080p][HEVC]"
    "[Multiple Subtitle] [ENG][POR-BR][SPA-LA][SPA][ARA][FRE][GER][ITA][RUS]"
)


def _query(episode, season_size=24, absolute=None) -> VideoQuery:
    return VideoQuery(
        series_title="Mushoku Tensei: Jobless Reincarnation",
        series_aliases=[("Mushoku Tensei II Isekai Ittara Honki Dasu", None, None)],
        season=2,
        episode=episode,
        sonarr_absolute_episode=absolute,
        season_size=season_size,
        languages=["de"],
    )


def _result(release) -> SubtitleResult:
    return SubtitleResult(
        provider_name="animetosho",
        subtitle_id="1",
        language="de",
        format=SubtitleFormat.ASS,
        filename="German.ger.ass",
        release_info=release,
        matches={"series", "episode"},
    )


class TestEpisodeGate:
    def test_part_2_episode_5_is_not_the_seasons_fifth(self):
        assert "Part 2" in episode_gate_reason(_result(ERAI_05), _query(5, absolute=30))

    def test_part_2_episode_5_is_the_seventeenth_of_a_24_episode_season(self):
        assert episode_gate_reason(_result(ERAI_05), _query(17, absolute=42)) == ""

    def test_another_part_2_episode_is_still_rejected(self):
        assert episode_gate_reason(_result(ERAI_05), _query(18, absolute=43))

    def test_a_number_past_the_cour_is_continuous_numbering(self):
        release = ERAI_05.replace("Part 2 - 05", "Part 2 - 17")
        assert episode_gate_reason(_result(release), _query(17)) == ""

    def test_an_odd_season_size_cannot_place_the_part(self):
        # 25 episodes split 12+13 or 13+12: "Part 2 - 05" is E17 or E18.
        assert episode_gate_reason(_result(ERAI_05), _query(17, season_size=25))

    def test_a_three_cour_season_cannot_place_the_part(self):
        # Dr. Stone: Science Future is 3 x 12: "Part 2 - 01" is E13, not E19.
        reason = episode_gate_reason(_result(ERAI_05), _query(17, season_size=36))
        assert reason.startswith("no episode evidence")

    def test_a_dr_stone_season_1_episode_is_not_science_future_part_2(self):
        release = "[Erai-raws] Dr. Stone: Science Future Part 2 - 08 [1080p CR WEBRip HEVC AAC]"
        query = VideoQuery(series_title="Dr. STONE", season=1, episode=8, season_size=24)
        assert "Part 2 episode 8" in episode_gate_reason(_result(release), query)

    def test_unknown_season_size_cannot_place_the_part(self):
        assert episode_gate_reason(_result(ERAI_05), _query(5, season_size=None))


class TestAnimeToshoMatching:
    def test_part_2_episode_5_is_no_match_for_e05(self):
        assert match_release(ERAI_05, _query(5, absolute=30)) is None

    def test_part_2_episode_5_matches_e17(self):
        matches = match_release(ERAI_05, _query(17, absolute=42))
        assert matches is not None and "episode" in matches

    def test_an_unplaceable_part_proves_no_episode(self):
        matches = match_release(ERAI_05, _query(5, season_size=None))
        assert matches is None or "episode" not in matches

    def test_an_sxxeyy_beside_the_part_is_the_episode(self):
        release = (
            "Dr STONE S04E16 Medusa Mechanism 1080p CR WEB-DL MULTi AAC2.0 H 264-VARYG "
            "(Dr. STONE: SCIENCE FUTURE Part 2, Multi-Audio, Multi-Subs)"
        )
        query = VideoQuery(series_title="Dr. STONE", season=4, episode=16, season_size=36)
        matches = match_release(release, query)
        assert matches is not None and "episode" in matches
        assert episode_gate_reason(_result(release), query) == ""

    def test_a_season_and_part_still_count_the_part(self):
        release = "[Group] Mushoku Tensei Season 2 Part 2 - 05 [1080p]"
        assert match_release(release, _query(5)) is None
