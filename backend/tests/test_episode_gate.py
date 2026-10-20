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
