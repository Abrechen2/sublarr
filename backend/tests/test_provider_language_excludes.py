"""Tests for per-provider language exclusion (#192).

Covers the ``parse_language_excludes`` reader and the search-coordinator
gate: excluded languages are removed from the query a provider sees, a
provider whose requested languages are all excluded is skipped, and results
in an excluded language are dropped even if a provider returns them anyway.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.language_excludes import parse_language_excludes


class TestParseLanguageExcludes:
    def test_empty_and_whitespace(self):
        assert parse_language_excludes("") == {}
        assert parse_language_excludes("   ") == {}

    def test_valid_object(self):
        result = parse_language_excludes('{"opensubtitles": ["sr", "hr"], "subdl": ["en"]}')
        assert result == {
            "opensubtitles": frozenset({"sr", "hr"}),
            "subdl": frozenset({"en"}),
        }

    def test_codes_are_normalized(self):
        result = parse_language_excludes('{"opensubtitles": [" SR ", "Hr"]}')
        assert result == {"opensubtitles": frozenset({"sr", "hr"})}

    def test_invalid_json_is_empty(self):
        assert parse_language_excludes("{not json") == {}

    def test_non_object_is_empty(self):
        assert parse_language_excludes('["sr"]') == {}
        assert parse_language_excludes('"sr"') == {}

    def test_non_list_entries_are_dropped(self):
        result = parse_language_excludes('{"a": "sr", "b": ["sr"], "c": 5}')
        assert result == {"b": frozenset({"sr"})}

    def test_non_string_codes_are_dropped(self):
        result = parse_language_excludes('{"a": ["sr", 5, null, ""]}')
        assert result == {"a": frozenset({"sr"})}

    def test_empty_lists_are_dropped(self):
        assert parse_language_excludes('{"a": []}') == {}


# ---------------------------------------------------------------------------
# Coordinator gate
# ---------------------------------------------------------------------------
def _make_result(provider_name: str, language: str) -> SubtitleResult:
    return SubtitleResult(
        provider_name=provider_name,
        subtitle_id=f"sub-{language}",
        language=language,
        format=SubtitleFormat.SRT,
        filename=f"test.{language}.srt",
        score=80,
    )


def _make_provider(name: str = "test_provider", results=None):
    _results = results if results is not None else []

    class _FakeProvider:
        rate_limits = {}
        config_fields = []

        def __init__(self):
            self.name = name
            self.tier = "free"
            self.session = object()
            self.search = MagicMock(return_value=list(_results))
            self.download = MagicMock(return_value=b"")

    return _FakeProvider()


def _patch_db_noop(monkeypatch):
    monkeypatch.setattr("db.providers.is_provider_auto_disabled", lambda name: False)
    monkeypatch.setattr("db.providers.update_provider_stats", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.cache_provider_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_cached_results", lambda *a, **kw: None)
    monkeypatch.setattr("db.providers.get_all_provider_stats", lambda: [], raising=False)
    monkeypatch.setattr("db.blacklist.is_blacklisted", lambda *a, **kw: False)


def _build_manager(monkeypatch, provider, excludes_json: str = ""):
    from providers import ProviderManager

    _patch_db_noop(monkeypatch)
    monkeypatch.setattr("providers.ProviderManager._get_cache_backend", staticmethod(lambda: None))

    manager = ProviderManager()
    manager._providers.clear()
    manager._providers[provider.name] = provider
    # Budget gate is exercised by its own suite; keep this one focused.
    manager.settings = manager.settings.model_copy(
        update={
            "provider_budget_enabled": False,
            "provider_language_excludes_json": excludes_json,
        }
    )

    cb = MagicMock()
    cb.allow_request.return_value = True
    manager._circuit_breakers[provider.name] = cb

    return manager


class TestLanguageExcludeGate:
    def test_no_excludes_searches_with_original_languages(self, app_ctx, monkeypatch):
        provider = _make_provider()
        manager = _build_manager(monkeypatch, provider, excludes_json="")

        manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["sr", "en"]))

        provider.search.assert_called_once()
        query_seen = provider.search.call_args.args[0]
        assert query_seen.languages == ["sr", "en"]

    def test_excluded_language_is_removed_from_provider_query(self, app_ctx, monkeypatch):
        provider = _make_provider()
        manager = _build_manager(monkeypatch, provider, excludes_json='{"test_provider": ["sr"]}')
        original_query = VideoQuery(file_path="/test/movie.mkv", languages=["sr", "en"])

        manager.search(original_query)

        provider.search.assert_called_once()
        query_seen = provider.search.call_args.args[0]
        assert query_seen.languages == ["en"]
        # The original query must not be mutated — other providers still see it.
        assert original_query.languages == ["sr", "en"]

    def test_all_languages_excluded_skips_provider(self, app_ctx, monkeypatch):
        provider = _make_provider()
        manager = _build_manager(monkeypatch, provider, excludes_json='{"test_provider": ["sr"]}')

        manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["sr"]))

        provider.search.assert_not_called()

    def test_exclusion_only_hits_named_provider(self, app_ctx, monkeypatch):
        provider = _make_provider()
        manager = _build_manager(
            monkeypatch, provider, excludes_json='{"another_provider": ["sr"]}'
        )

        manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["sr"]))

        provider.search.assert_called_once()
        assert provider.search.call_args.args[0].languages == ["sr"]

    def test_results_in_excluded_language_are_dropped(self, app_ctx, monkeypatch):
        # A provider that ignores the narrowed query and returns an excluded
        # language anyway — the coordinator must not let that result through.
        provider = _make_provider(
            results=[
                _make_result("test_provider", "sr"),
                _make_result("test_provider", "en"),
            ]
        )
        manager = _build_manager(monkeypatch, provider, excludes_json='{"test_provider": ["sr"]}')

        results = manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["sr", "en"]))

        languages = {r.language for r in results}
        assert "sr" not in languages
        assert "en" in languages

    def test_skip_is_recorded_in_decision_log(self, app_ctx, monkeypatch):
        provider = _make_provider()
        manager = _build_manager(monkeypatch, provider, excludes_json='{"test_provider": ["sr"]}')
        skipped = []
        monkeypatch.setattr(
            "providers.search_coordinator.decision_log.provider_skipped",
            lambda name, reason, detail="": skipped.append((name, reason)),
        )

        manager.search(VideoQuery(file_path="/test/movie.mkv", languages=["sr"]))

        assert ("test_provider", "languages_excluded") in skipped
