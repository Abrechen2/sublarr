"""Tests for user-defined regex scoring rules (repo + pipeline + API)."""

import pytest


@pytest.fixture(autouse=True)
def _fresh_custom_rules_cache():
    """Custom-rule pipeline cache must not leak between tests."""
    from wanted_search.penalty_rules import invalidate_custom_rules_cache

    invalidate_custom_rules_cache()
    yield
    invalidate_custom_rules_cache()


def _make_candidate(**kw):
    from providers.base import SubtitleFormat, SubtitleResult

    defaults = dict(
        provider_name="test",
        subtitle_id="1",
        language="de",
        format=SubtitleFormat.ASS,
        release_info="[Erai-raws] Show - 01 [1080p][Multiple Subtitle]",
    )
    defaults.update(kw)
    return SubtitleResult(**defaults)


def _make_query(**kw):
    from providers.base import VideoQuery

    defaults = dict(file_path="/m/S01E01.mkv", series_title="X", season=1, episode=1)
    defaults.update(kw)
    return VideoQuery(**defaults)


class TestCustomScoringRuleRepository:
    def test_create_and_list_roundtrip(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        repo = CustomScoringRuleRepository()
        rule = repo.create_rule("Prefer dual audio", r"dual[ .-]?audio", 15)
        assert rule["id"] > 0
        assert rule["enabled"] is True

        rules = repo.list_rules()
        assert any(r["id"] == rule["id"] for r in rules)

    def test_create_rejects_invalid_regex(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        with pytest.raises(ValueError, match="invalid regex"):
            CustomScoringRuleRepository().create_rule("bad", "[unclosed", 10)

    def test_create_rejects_empty_name_and_pattern(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        repo = CustomScoringRuleRepository()
        with pytest.raises(ValueError):
            repo.create_rule("  ", "x", 10)
        with pytest.raises(ValueError):
            repo.create_rule("ok", "", 10)

    def test_create_rejects_weight_out_of_range(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        with pytest.raises(ValueError):
            CustomScoringRuleRepository().create_rule("x", "y", 1000)

    def test_update_and_delete(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        repo = CustomScoringRuleRepository()
        rule = repo.create_rule("orig", "orig", 5)
        updated = repo.update_rule(rule["id"], "renamed", "new", -20, False)
        assert updated["name"] == "renamed"
        assert updated["weight"] == -20
        assert updated["enabled"] is False

        assert repo.delete_rule(rule["id"]) is True
        assert repo.delete_rule(rule["id"]) is False

    def test_update_unknown_id_returns_none(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        assert CustomScoringRuleRepository().update_rule(99999, "x", "y", 1, True) is None

    def test_list_enabled_only_filters(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository

        repo = CustomScoringRuleRepository()
        on = repo.create_rule("on", "aaa", 5, enabled=True)
        off = repo.create_rule("off", "bbb", 5, enabled=False)
        enabled_ids = {r["id"] for r in repo.list_rules(enabled_only=True)}
        assert on["id"] in enabled_ids
        assert off["id"] not in enabled_ids


class TestApplyCustomRegexRules:
    def test_matching_rule_contributes_weight(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        rule = CustomScoringRuleRepository().create_rule("erai", r"erai[- ]?raws", 25)
        breakdown = apply_custom_regex_rules(_make_candidate(), _make_query())
        assert breakdown.get(f"custom_{rule['id']}") == 25

    def test_non_matching_rule_is_absent(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        CustomScoringRuleRepository().create_rule("nope", r"commie", 25)
        assert apply_custom_regex_rules(_make_candidate(), _make_query()) == {}

    def test_disabled_rule_is_skipped(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        CustomScoringRuleRepository().create_rule("off", r"erai", -50, enabled=False)
        assert apply_custom_regex_rules(_make_candidate(), _make_query()) == {}

    def test_match_is_case_insensitive(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        rule = CustomScoringRuleRepository().create_rule("caps", r"MULTIPLE SUBTITLE", 5)
        breakdown = apply_custom_regex_rules(_make_candidate(), _make_query())
        assert f"custom_{rule['id']}" in breakdown

    def test_negative_weight_penalty(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        rule = CustomScoringRuleRepository().create_rule("no-1080", r"1080p", -30)
        breakdown = apply_custom_regex_rules(_make_candidate(), _make_query())
        assert breakdown[f"custom_{rule['id']}"] == -30

    def test_empty_release_info_matches_nothing(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_custom_regex_rules

        CustomScoringRuleRepository().create_rule("any", r".*", 5)
        assert apply_custom_regex_rules(_make_candidate(release_info=""), _make_query()) == {}

    def test_pipeline_includes_custom_entries(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import apply_penalty_pipeline

        rule = CustomScoringRuleRepository().create_rule("erai", r"erai", 25)
        breakdown = apply_penalty_pipeline(_make_candidate(), _make_query())
        assert breakdown.get(f"custom_{rule['id']}") == 25

    def test_cache_invalidation_picks_up_new_rules(self, app_ctx):
        from db.repositories.custom_rules import CustomScoringRuleRepository
        from wanted_search.penalty_rules import (
            apply_custom_regex_rules,
            invalidate_custom_rules_cache,
        )

        # Prime the cache with no rules
        assert apply_custom_regex_rules(_make_candidate(), _make_query()) == {}

        rule = CustomScoringRuleRepository().create_rule("erai", r"erai", 25)
        # Still cached-empty until invalidated
        assert apply_custom_regex_rules(_make_candidate(), _make_query()) == {}

        invalidate_custom_rules_cache()
        breakdown = apply_custom_regex_rules(_make_candidate(), _make_query())
        assert breakdown.get(f"custom_{rule['id']}") == 25


class TestCustomRuleRoutes:
    def test_list_initially_empty(self, client):
        r = client.get("/api/v1/scoring/custom-rules")
        assert r.status_code == 200
        assert r.get_json() == {"rules": []}

    def test_create_list_update_delete_lifecycle(self, client):
        r = client.post(
            "/api/v1/scoring/custom-rules",
            json={"name": "Dual audio", "pattern": r"dual[ .-]?audio", "weight": 15},
        )
        assert r.status_code == 200
        rule = r.get_json()
        assert rule["enabled"] is True

        r = client.get("/api/v1/scoring/custom-rules")
        assert len(r.get_json()["rules"]) == 1

        r = client.put(
            f"/api/v1/scoring/custom-rules/{rule['id']}",
            json={"name": "Dual audio", "pattern": r"dual", "weight": -5, "enabled": False},
        )
        assert r.status_code == 200
        assert r.get_json()["weight"] == -5
        assert r.get_json()["enabled"] is False

        r = client.delete(f"/api/v1/scoring/custom-rules/{rule['id']}")
        assert r.status_code == 200
        r = client.get("/api/v1/scoring/custom-rules")
        assert r.get_json() == {"rules": []}

    def test_create_rejects_invalid_regex(self, client):
        r = client.post(
            "/api/v1/scoring/custom-rules",
            json={"name": "bad", "pattern": "[unclosed", "weight": 10},
        )
        assert r.status_code == 400
        assert "invalid regex" in r.get_json()["error"]

    def test_update_unknown_id_404(self, client):
        r = client.put(
            "/api/v1/scoring/custom-rules/424242",
            json={"name": "x", "pattern": "y", "weight": 1},
        )
        assert r.status_code == 404

    def test_delete_unknown_id_404(self, client):
        r = client.delete("/api/v1/scoring/custom-rules/424242")
        assert r.status_code == 404
