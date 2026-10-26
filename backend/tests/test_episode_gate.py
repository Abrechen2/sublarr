"""Central wrong-episode gate (providers/episode_gate.py).

Prod (Clevatess, Sonarr series 1084, S01 12 eps + S02) saved season-1
subtitles for season-2 episodes: OpenSubtitles scored
``Clevatess - S01E12 [CR WEB-DL 1080p]`` {"year": 90, "episode": 30} and
AnimeTosho ``[SubsPlease] Clevatess - 12`` {"series": 180, "episode": 30}
for S02E12, both above min_score. The hub provider subtitlecat did the same
(Mission Yozakura S02E14 <- S01E02, Overgeared S01E04 <- S01E03). Every
provider's results pass through one gate before scoring decides anything.
"""

from __future__ import annotations

import pytest

import decision_log
from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.episode_gate import apply_episode_gate, episode_gate_reason


def _query(season=2, episode=12, **kwargs) -> VideoQuery:
    kwargs.setdefault("series_title", "Clevatess")
    return VideoQuery(season=season, episode=episode, languages=["de"], **kwargs)


def _result(filename="", release_info="", matches=None, provider="opensubtitles", **kwargs):
    return SubtitleResult(
        provider_name=provider,
        subtitle_id=kwargs.pop("subtitle_id", "1"),
        language="de",
        format=SubtitleFormat.SRT,
        filename=filename,
        release_info=release_info,
        matches=set(matches if matches is not None else {"series", "episode"}),
        **kwargs,
    )


class TestWrongEpisodeIsDropped:
    def test_clevatess_s01e12_for_s02e12(self):
        result = _result(
            filename="Clevatess - S01E12 [CR WEB-DL 1080p].srt",
            release_info="Clevatess - S01E12 [CR WEB-DL 1080p]",
            matches={"year", "episode"},
        )
        assert "S01E12" in episode_gate_reason(result, _query())

    def test_clevatess_s01e06_blackluster_for_s02e06(self):
        result = _result(
            filename="Clevatess.S01E06.1080p.WEB.H264-BlackLuster.srt",
            matches={"year", "episode"},
        )
        assert episode_gate_reason(result, _query(episode=6))

    def test_bare_episode_of_season_one_when_the_absolute_is_known(self):
        # S02E12 is absolute 24; a bare "12" without any season is S01E12.
        result = _result(
            filename="[SubsPlease] Clevatess - 12 (1080p).ass",
            matches={"series", "episode"},
            provider="animetosho",
        )
        assert episode_gate_reason(result, _query(absolute_episode=24))

    def test_bare_episode_uses_sonarr_absolute_for_matching(self):
        result = _result(filename="[SubsPlease] Clevatess - 12 (1080p).ass", provider="animetosho")
        assert episode_gate_reason(result, _query(sonarr_absolute_episode=24))

    @pytest.mark.parametrize("name", ["Show.1x5.srt", "Show 1x05.srt", "Show.1x005.srt"])
    def test_single_digit_cross_numbering_of_another_season(self, name):
        # VM 191 (RC 1.17.0-rc.1): "1x5" was not read as numbering at all, so
        # the "episode" match let season 1's fifth through for S02E05.
        reason = episode_gate_reason(
            _result(filename=name), _query(episode=5, sonarr_absolute_episode=17)
        )
        assert "S01E05" in reason

    def test_single_digit_cross_numbering_of_the_queried_episode(self):
        assert episode_gate_reason(_result(filename="Show.2x5.srt"), _query(episode=5)) == ""

    @pytest.mark.parametrize("name", ["Show.1920x1080.srt", "Show.x264.srt", "Show.5x1080.srt"])
    def test_resolutions_and_codecs_are_not_cross_numbering(self, name):
        from providers.episode_gate import parse_claims

        assert parse_claims(name).season_episodes == []

    def test_overgeared_s01e03_for_s01e04(self):
        result = _result(
            filename="Overgeared_S01E03.srt",
            matches={"series"},
            provider="subtitlecat",
        )
        assert episode_gate_reason(result, _query(season=1, episode=4, series_title="Overgeared"))

    def test_mission_yozakura_s01e02_for_s02e14(self):
        result = _result(
            filename="Mission.Yozakura.Family.S01E02.1080p.WEB.srt",
            matches={"series"},
            provider="subtitlecat",
        )
        assert episode_gate_reason(
            result, _query(episode=14, series_title="Mission: Yozakura Family")
        )

    def test_season_pack_of_another_season(self):
        result = _result(filename="Clevatess.S01.1080p.WEB-DL.zip", matches={"series", "season"})
        assert episode_gate_reason(result, _query())

    def test_season_marker_with_wrong_bare_episode(self):
        result = _result(filename="[Group] Clevatess S2 - 05 [1080p].ass")
        assert episode_gate_reason(result, _query())

    def test_no_numbering_and_no_episode_match_is_not_eligible(self):
        result = _result(filename="Clevatess.German.srt", matches={"series", "year"})
        assert "no episode evidence" in episode_gate_reason(result, _query())


class TestRightEpisodeIsKept:
    def test_correct_s02e12_release(self):
        result = _result(filename="Clevatess.S02E12.1080p.WEB.H264-BlackLuster.srt")
        assert episode_gate_reason(result, _query()) == ""

    def test_bare_absolute_number(self):
        result = _result(filename="[SubsPlease] Clevatess - 24 (1080p).ass", matches={"series"})
        assert episode_gate_reason(result, _query(absolute_episode=24)) == ""

    def test_s01e_absolute_naming(self):
        result = _result(filename="Clevatess.S01E24.1080p.srt", matches={"series"})
        assert episode_gate_reason(result, _query(absolute_episode=24)) == ""

    def test_s01e_absolute_naming_with_sonarr_absolute(self):
        result = _result(filename="Clevatess.S01E24.1080p.srt", matches={"series"})
        assert episode_gate_reason(result, _query(sonarr_absolute_episode=24)) == ""

    def test_season_pack_whose_episode_the_provider_resolves(self):
        result = _result(
            filename="Clevatess.S02.1080p.WEB-DL.zip",
            matches={"series", "season"},
            provider="titlovi",
            provider_data={"is_pack": True, "season": 2, "episode": 12},
        )
        assert episode_gate_reason(result, _query()) == ""

    def test_named_season_pack_of_the_queried_season(self):
        result = _result(filename="Clevatess.S02.1080p.WEB-DL.zip", matches={"series", "season"})
        assert episode_gate_reason(result, _query()) == ""

    def test_hash_match_beats_a_contradicting_name(self):
        result = _result(filename="Clevatess.S01E12.srt", matches={"hash"})
        assert episode_gate_reason(result, _query()) == ""

    def test_no_numbering_with_episode_match_keeps_current_behaviour(self):
        result = _result(filename="Clevatess.German.srt", matches={"series", "episode"})
        assert episode_gate_reason(result, _query()) == ""

    def test_one_matching_release_in_a_list_is_enough(self):
        result = _result(
            filename="Clevatess.srt",
            release_info="Clevatess.S01E12.720p Clevatess.S02E12.1080p",
            matches={"series"},
        )
        assert episode_gate_reason(result, _query()) == ""

    def test_season_marker_with_matching_bare_episode(self):
        result = _result(filename="[Group] Clevatess S2 - 12 [1080p].ass", matches={"series"})
        assert episode_gate_reason(result, _query(absolute_episode=24)) == ""

    def test_bare_episode_without_absolute_is_not_contradicted(self):
        # Without an absolute number "12" may well be this season's 12th.
        result = _result(filename="[Group] Clevatess - 12 [1080p].ass")
        assert episode_gate_reason(result, _query()) == ""

    def test_multi_episode_file(self):
        result = _result(filename="Show.S01E01E02.1080p.srt", matches={"series"})
        query = _query(season=1, episode=1, episodes=[1, 2], series_title="Show")
        assert episode_gate_reason(result, query) == ""

    def test_resolution_and_codec_are_not_episode_numbers(self):
        result = _result(filename="Clevatess.S02E12.1920x1080.x264-10bit.srt")
        assert episode_gate_reason(result, _query()) == ""

    def test_movie_queries_are_not_gated(self):
        result = _result(filename="Movie.S01E01.srt", matches={"title"})
        assert episode_gate_reason(result, VideoQuery(title="Movie", year=2020)) == ""


def test_apply_episode_gate_returns_reasons():
    keep = _result(filename="Clevatess.S02E12.srt", subtitle_id="keep")
    drop = _result(filename="Clevatess.S01E12.srt", subtitle_id="drop")
    kept, rejected = apply_episode_gate([keep, drop], _query())
    assert kept == [keep]
    assert [(r.subtitle_id, bool(reason)) for r, reason in rejected] == [("drop", True)]


class TestFinalisePipeline:
    @pytest.fixture(autouse=True)
    def _reset_decision_log(self):
        decision_log.finish()
        yield
        decision_log.finish()

    def _finalise(self, monkeypatch, results, query):
        from providers import ProviderManager

        monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)
        manager = ProviderManager.__new__(ProviderManager)
        return manager._finalise_search_results(results, query, None, 0, None, None)

    def test_wrong_episode_is_dropped_and_logged(self, app_ctx, monkeypatch):
        decision_log.start({"id": 1})
        decision_log.search_started(["de"], None, 0)
        right = _result(filename="Clevatess.S02E12.srt", subtitle_id="right")
        wrong = _result(
            filename="Clevatess - S01E12 [CR WEB-DL 1080p].srt",
            subtitle_id="wrong",
            matches={"year", "episode"},
        )

        final = self._finalise(monkeypatch, [wrong, right], _query())

        assert [r.subtitle_id for r in final] == ["right"]
        stages = {f["stage"]: f for f in decision_log.active().to_dict()["searches"][0]["filters"]}
        stage = stages["wrong_episode"]
        assert stage["removed"] == 1
        assert stage["wanted"] == "S02E12"
        assert stage["rejected"][0]["filename"].startswith("Clevatess - S01E12")
        assert "S01E12" in stage["reasons"][0]

    def test_hub_result_with_series_only_is_dropped(self, app_ctx, monkeypatch):
        wrong = _result(
            filename="Overgeared_S01E03.srt", matches={"series"}, provider="subtitlecat"
        )
        final = self._finalise(
            monkeypatch, [wrong], _query(season=1, episode=4, series_title="Overgeared")
        )
        assert final == []


class TestEarlyExit:
    def test_wrong_episode_cannot_trigger_early_exit(self, monkeypatch):
        from concurrent.futures import Future

        from providers import ProviderManager

        manager = ProviderManager.__new__(ProviderManager)
        manager._circuit_breakers = {}
        monkeypatch.setattr(manager, "_get_language_excludes", lambda: {}, raising=False)
        monkeypatch.setattr(
            "providers.search_coordinator.compute_score",
            lambda r, q: setattr(r, "score", 500) or 500,
        )
        exits = []
        monkeypatch.setattr(
            "providers.search_coordinator.decision_log.early_exit",
            lambda *a: exits.append(a),
        )
        wrong = _result(filename="Clevatess.S01E12.srt", matches={"series", "year", "episode"})
        future: Future = Future()
        future.set_result(([wrong], 5))

        results = manager._collect_provider_results(
            {future: "opensubtitles"}, {}, 5, _query(), True, lambda *a, **kw: None
        )

        assert results == [wrong]
        assert exits == []


class TestProdAuditFalseAlarms:
    """Prod 1.17.0-rc.4: the wrong-episode audit flagged 377 saved subtitles,
    about a quarter of them the right episode under other numbering. The same
    gate runs on every search, where those names were dropped as well."""

    @pytest.mark.parametrize(
        "release,season,episode",
        [
            ("[LostYears] Peter Grill and the Philosopher's Time - 05-08 (WEB 1080p x264)", 1, 7),
            ("[Redc4t] Death Note - 13-24 [BD 720p] [Batch]", 1, 24),
            ("[Redc4t] Death Note - 21-22 [BD 1080p]", 1, 22),
            ("[Erai-raws] Re-Creators - 01 ~ 22 [1080p][Multiple Subtitle]", 1, 2),
            ("[MA0MA0] To Be Hero X (Tu Bian Yingxiong X) - S01 E01~E12 [Pb]", 1, 3),
            ("[Maximus] Fire Force S2 - Ep. 01 - 19 [1080p x265 Dual Audio AAC]", 2, 12),
            ("[USD] Kuma Kuma Kuma Bear - S01 - E01-03 [1080p HEVC 10bits]", 1, 3),
            ("[AnimeRG] Twin Star Exorcists Episode 1 - 14 [720p] [Multi-Sub]", 1, 11),
        ],
    )
    def test_a_batch_range_holding_the_episode_is_kept(self, release, season, episode):
        result = _result(release_info=release, matches={"series"}, provider="animetosho")
        assert episode_gate_reason(result, _query(season=season, episode=episode)) == ""

    @pytest.mark.parametrize(
        "release",
        [
            "[Erai-raws] Re-Creators - 01 ~ 22 [1080p]",
            "[Redc4t] Death Note - 13-24 [BD 720p] [Batch]",
        ],
    )
    def test_a_batch_range_without_the_episode_is_dropped(self, release):
        result = _result(release_info=release, matches={"series"}, provider="animetosho")
        assert "episode" in episode_gate_reason(result, _query(season=1, episode=25))

    def test_a_year_span_is_not_a_range(self):
        result = _result(release_info="Show - 2019-2021 Complete", matches={"series"})
        assert episode_gate_reason(result, _query(season=1, episode=5)) == (
            "no episode evidence (no episode match and no numbering in the name)"
        )

    @pytest.mark.parametrize(
        "release,season,episode,absolute",
        [
            ("[Crunchyroll] My Hero Academia S03E39 Game Start_[eng]", 3, 1, 39),
            (
                "[Cunchyroll] That Time I Got Reincarnated as a Slime S02E25 Rimuru's Busy Life",
                2,
                1,
                25,
            ),
        ],
    )
    def test_continuous_numbering_by_absolute_is_kept(self, release, season, episode, absolute):
        result = _result(release_info=release)
        query = _query(season=season, episode=episode, sonarr_absolute_episode=absolute)
        assert episode_gate_reason(result, query) == ""

    def test_a_later_seasons_same_number_is_not_continuous_numbering(self):
        # S01E05 is absolute 5; "S02E05" is season 2's fifth, the Clevatess case
        # the other way round, not a continuously numbered S01E05.
        result = _result(release_info="Clevatess - S02E05 [CR WEB-DL 1080p]")
        query = _query(season=1, episode=5, sonarr_absolute_episode=5)
        assert "S02E05" in episode_gate_reason(result, query)

    def test_continuous_numbering_of_a_later_season_is_dropped(self):
        # S05E25 cannot be absolute 25 counted from a season-2 episode's past.
        result = _result(release_info="Show S05E25 Something")
        query = _query(season=2, episode=1, sonarr_absolute_episode=25)
        assert "S05E25" in episode_gate_reason(result, query)

    def test_the_episode_title_in_the_name_is_the_episode(self):
        result = _result(release_info="[Crunchyroll] My Hero Academia S03E39 Game Start_[eng]")
        query = _query(season=3, episode=1, title="Game Start")
        assert episode_gate_reason(result, query) == ""

    @pytest.mark.parametrize("title", ["Episode 11", "Folge 3", "Pilot", ""])
    def test_a_generic_title_proves_nothing(self, title):
        result = _result(release_info="[AMZN] Dropkick on my Devil! S01E11 Episode 11")
        query = _query(season=2, episode=11, title=title)
        assert "S01E11" in episode_gate_reason(result, query)


class TestCodexReviewOfRc5:
    """Counterexamples from the independent review of the rc.5 draft."""

    def test_a_title_inside_a_longer_title_is_not_the_episode(self):
        result = _result(release_info="Show S01E12 The Beginning of the End")
        query = _query(season=1, episode=1, title="The Beginning")
        assert "S01E12" in episode_gate_reason(result, query)

    def test_the_series_name_as_title_proves_nothing(self):
        result = _result(release_info="Clevatess S01E05 Clevatess [1080p]")
        query = _query(season=2, episode=5, title="Clevatess")
        assert "S01E05" in episode_gate_reason(result, query)

    def test_the_whole_release_title_must_be_the_episode_title(self):
        result = _result(release_info="[Crunchyroll] My Hero Academia S03E39 Game Start_[eng]")
        assert episode_gate_reason(result, _query(season=3, episode=1, title="Game Start")) == ""

    def test_an_intermediate_seasons_absolute_number_is_not_continuous(self):
        # S03E01 is absolute 25 here; "S02E25" may be season 2's own 25th.
        result = _result(release_info="Show S02E25 Something")
        query = _query(season=3, episode=1, sonarr_absolute_episode=25)
        assert "S02E25" in episode_gate_reason(result, query)

    @pytest.mark.parametrize("release", ["Show - 01-12-2025 [1080p]", "Show - 11-12.5 [1080p]"])
    def test_dates_and_fractions_are_not_ranges(self, release):
        result = _result(release_info=release, matches={"series"})
        assert episode_gate_reason(result, _query(season=1, episode=5)) != ""

    def test_a_recap_episode_is_not_the_next_episode(self):
        result = _result(release_info="86 - Eighty Six - 11.5 [1080p]", matches={"series"})
        assert "11.5" in episode_gate_reason(result, _query(season=1, episode=12))

    def test_a_tilde_range_is_capped(self):
        result = _result(release_info="Show S01E01~E900", matches={"series"})
        assert "S01E01" in episode_gate_reason(result, _query(season=1, episode=700))

    def test_a_title_rescued_listing_keeps_its_archive_member(self):
        from providers.episode_gate import archive_member_reason

        result = _result(release_info="[Crunchyroll] My Hero Academia S03E39 Game Start")
        query = _query(season=3, episode=1, title="Game Start")
        assert archive_member_reason(result, "My Hero Academia S03E39.srt", query) == ""


@pytest.mark.parametrize(
    "ext", ["srt", "ass", "ssa", "vtt", "sub", "en.srt", "de.forced.ass", "pt-br.srt"]
)
def test_a_recap_file_name_with_its_extension_is_not_the_episode(ext):
    result = _result(filename=f"Harbor Tales - 11.5.{ext}", matches={"series", "episode"})
    assert "11.5" in episode_gate_reason(result, _query(season=1, episode=11))


@pytest.mark.parametrize("name", ["Show - 2.0.srt", "Show - 1.2.srt"])
def test_a_version_number_before_the_extension_is_no_recap(name):
    result = _result(filename=name, matches={"series", "episode"})
    assert episode_gate_reason(result, _query(season=1, episode=2)) == ""
