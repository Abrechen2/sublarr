"""Provider profiles: per-profile provider restriction + scoring preset.

Covers the feature added for the "Regel-Engine und Profile" request:
- VideoQuery.allowed_providers gates which providers a search queries.
- VideoQuery.scoring_preset swaps the weight map used by compute_score,
  including the port-group penalty rules that supersede legacy weight keys.
- load_profile_filters exposes enabled_providers / scoring_preset.
- profile_service validates both new fields.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery, compute_score


def _make_result(provider_name: str = "prov_a", fmt=SubtitleFormat.SRT) -> SubtitleResult:
    return SubtitleResult(
        provider_name=provider_name,
        subtitle_id=f"sub-{provider_name}",
        language="de",
        format=fmt,
        filename="test.srt",
        release_info="",
        hearing_impaired=False,
        forced=False,
        provider_data={},
    )


def _make_provider(name: str):
    _result = _make_result(name)

    class _FakeProvider:
        rate_limits = {"free": {"second": 5, "hour": 200, "day": 1000}}

        def __init__(self):
            self.name = name
            self.tier = "free"
            self.session = object()
            self.search = MagicMock(return_value=[_result])
            self.download = MagicMock(return_value=b"")

    return _FakeProvider()


def _patch_db_noop(monkeypatch):
    monkeypatch.setattr("db.providers.is_provider_auto_disabled", lambda name: False)
    monkeypatch.setattr("db.providers.update_provider_stats", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.cache_provider_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_cached_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_all_provider_stats", lambda: [], raising=False)
    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)


def _build_manager(monkeypatch, *providers):
    from providers import ProviderManager

    _patch_db_noop(monkeypatch)
    monkeypatch.setattr("providers.ProviderManager._get_cache_backend", staticmethod(lambda: None))

    manager = ProviderManager()
    manager._providers.clear()
    for provider in providers:
        manager._providers[provider.name] = provider
        cb = MagicMock()
        cb.allow_request.return_value = True
        manager._circuit_breakers[provider.name] = cb

    # Keep the budget gate out of these tests — it has its own suite.
    manager.settings = manager.settings.model_copy(update={"provider_budget_enabled": False})
    return manager


class TestProviderProfileGate:
    """query.allowed_providers restricts which providers are searched."""

    def test_allowed_providers_restricts_search(self, app_ctx, monkeypatch):
        prov_a = _make_provider("prov_a")
        prov_b = _make_provider("prov_b")
        manager = _build_manager(monkeypatch, prov_a, prov_b)

        query = VideoQuery(
            file_path="/test/movie.mkv",
            languages=["de"],
            allowed_providers=["prov_a"],
        )
        manager.search(query)

        prov_a.search.assert_called_once()
        prov_b.search.assert_not_called()

    def test_empty_allowed_providers_queries_all(self, app_ctx, monkeypatch):
        prov_a = _make_provider("prov_a")
        prov_b = _make_provider("prov_b")
        manager = _build_manager(monkeypatch, prov_a, prov_b)

        manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["de"]))

        prov_a.search.assert_called_once()
        prov_b.search.assert_called_once()

    def test_allowed_providers_partitions_cache_key(self, app_ctx, monkeypatch):
        prov_a = _make_provider("prov_a")
        manager = _build_manager(monkeypatch, prov_a)

        base = VideoQuery(file_path="/test/movie.mkv", languages=["de"])
        restricted = VideoQuery(
            file_path="/test/movie.mkv", languages=["de"], allowed_providers=["prov_a"]
        )
        preset = VideoQuery(file_path="/test/movie.mkv", languages=["de"], scoring_preset="Anime")

        keys = {
            manager._make_cache_key(base),
            manager._make_cache_key(restricted),
            manager._make_cache_key(preset),
        }
        assert len(keys) == 3


class TestPresetScoring:
    """query.scoring_preset swaps the weight map used by compute_score."""

    def test_anime_preset_format_bonus_survives_pipeline(self, app_ctx):
        # Anime preset: format_bonus=80. The format_bonus_ass port rule
        # supersedes the legacy key, so the preset weight must be carried
        # into the rule's contribution.
        result = _make_result("prov_a", fmt=SubtitleFormat.ASS)
        result.matches = {"series", "season", "episode"}
        query = VideoQuery(
            series_title="Test",
            season=1,
            episode=1,
            languages=["de"],
            scoring_preset="Anime",
        )
        compute_score(result, query)

        ass_bonus = result.score_breakdown.get(
            "rule:format_bonus_ass"
        ) or result.score_breakdown.get("format_bonus")
        assert ass_bonus == 80
        # Anime preset raises series weight to 180 (same as default) — sanity
        assert result.score_breakdown["series"] == 180

    def test_unknown_preset_falls_back_to_global_weights(self, app_ctx):
        result = _make_result("prov_a", fmt=SubtitleFormat.ASS)
        result.matches = {"series"}
        query = VideoQuery(
            series_title="Test",
            season=1,
            episode=1,
            languages=["de"],
            scoring_preset="does-not-exist",
        )
        compute_score(result, query)

        ass_bonus = result.score_breakdown.get(
            "rule:format_bonus_ass"
        ) or result.score_breakdown.get("format_bonus")
        assert ass_bonus == 50  # global default

    def test_no_preset_keeps_default_scoring(self, app_ctx):
        result = _make_result("prov_a", fmt=SubtitleFormat.ASS)
        result.matches = {"series"}
        query = VideoQuery(series_title="Test", season=1, episode=1, languages=["de"])
        compute_score(result, query)

        ass_bonus = result.score_breakdown.get(
            "rule:format_bonus_ass"
        ) or result.score_breakdown.get("format_bonus")
        assert ass_bonus == 50


class TestProfileFilters:
    """load_profile_filters exposes the provider-profile fields."""

    def test_none_profile_defaults(self):
        from wanted_search.profile_filters import load_profile_filters

        pf = load_profile_filters(None)
        assert pf["enabled_providers"] == []
        assert pf["scoring_preset"] == ""

    def test_profile_fields_decoded(self):
        from wanted_search.profile_filters import load_profile_filters

        class _Profile:
            must_contain_json = "[]"
            must_not_contain_json = "[]"
            cutoff_language = ""
            audio_exclude_languages_json = "[]"
            hi_preference = "include"
            forced_scoring = "include"
            enabled_providers_json = '["jimaku", "animetosho"]'
            scoring_preset = "Anime"

        pf = load_profile_filters(_Profile())
        assert pf["enabled_providers"] == ["jimaku", "animetosho"]
        assert pf["scoring_preset"] == "Anime"

    def test_profile_null_json_defaults(self):
        from wanted_search.profile_filters import load_profile_filters

        class _Profile:
            must_contain_json = "[]"
            must_not_contain_json = "[]"
            cutoff_language = ""
            audio_exclude_languages_json = "[]"
            hi_preference = "include"
            forced_scoring = "include"
            enabled_providers_json = None
            scoring_preset = None

        pf = load_profile_filters(_Profile())
        assert pf["enabled_providers"] == []
        assert pf["scoring_preset"] == ""


class TestProfileServiceValidation:
    """profile_service validates enabled_providers and scoring_preset."""

    def test_clean_enabled_providers_normalises(self):
        from services.profile_service import _clean_enabled_providers

        assert _clean_enabled_providers(None) == []
        assert _clean_enabled_providers([]) == []
        assert _clean_enabled_providers(["Jimaku", "jimaku", " animetosho "]) == [
            "jimaku",
            "animetosho",
        ]

    def test_clean_enabled_providers_rejects_bad_names(self):
        from services.profile_service import ProfileValidationError, _clean_enabled_providers

        with pytest.raises(ProfileValidationError):
            _clean_enabled_providers(["../etc/passwd"])
        with pytest.raises(ProfileValidationError):
            _clean_enabled_providers("jimaku")  # not a list

    def test_clean_scoring_preset_validates_against_bundled(self):
        from services.profile_service import ProfileValidationError, _clean_scoring_preset

        assert _clean_scoring_preset(None) == ""
        assert _clean_scoring_preset("") == ""
        assert _clean_scoring_preset("Anime") == "Anime"
        with pytest.raises(ProfileValidationError):
            _clean_scoring_preset("NoSuchPreset")
