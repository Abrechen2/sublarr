"""Tests for the global release-group tier ranking (scoring + service + API)."""

import pytest

from wanted_search.scoring import _apply_fansub_rules, _apply_release_group_tiers


def _results(*release_infos):
    return [{"release_info": info, "score": 100} for info in release_infos]


class TestApplyReleaseGroupTiers:
    def test_top_tier_earns_more_than_lower_tier(self):
        results = _results("[Erai-raws] Show - 01", "[SubsPlease] Show - 01")
        _apply_release_group_tiers(results, ["Erai-raws", "SubsPlease"], step=10)
        assert results[0]["score"] == 120  # step * (2 - 0)
        assert results[1]["score"] == 110  # step * (2 - 1)

    def test_last_tier_still_earns_step(self):
        results = _results("[Judas] Show - 01")
        _apply_release_group_tiers(results, ["Erai-raws", "SubsPlease", "Judas"], step=10)
        assert results[0]["score"] == 110

    def test_no_match_leaves_score_unchanged(self):
        results = _results("[SomeOtherGroup] Show - 01")
        _apply_release_group_tiers(results, ["Erai-raws"], step=10)
        assert results[0]["score"] == 100

    def test_match_is_case_insensitive(self):
        results = _results("[erai-RAWS] Show - 01")
        _apply_release_group_tiers(results, ["Erai-Raws"], step=10)
        assert results[0]["score"] == 110

    def test_only_best_matching_tier_counts(self):
        # release_info mentions both groups — only the higher tier applies
        results = _results("[Erai-raws] Show (SubsPlease remux)")
        _apply_release_group_tiers(results, ["Erai-raws", "SubsPlease"], step=10)
        assert results[0]["score"] == 120

    def test_empty_and_whitespace_entries_are_dropped(self):
        results = _results("[NoMatchGroup] Show - 01")
        _apply_release_group_tiers(results, ["", "  ", "Erai-raws"], step=10)
        # "Erai-raws" is the only real tier (n=1) and it doesn't match
        assert results[0]["score"] == 100

    def test_empty_tier_list_is_noop(self):
        results = _results("[Erai-raws] Show - 01")
        _apply_release_group_tiers(results, [], step=10)
        assert results[0]["score"] == 100

    def test_zero_step_is_noop(self):
        results = _results("[Erai-raws] Show - 01")
        _apply_release_group_tiers(results, ["Erai-raws"], step=0)
        assert results[0]["score"] == 100

    def test_missing_release_info_key(self):
        results = [{"score": 100}]
        _apply_release_group_tiers(results, ["Erai-raws"], step=10)
        assert results[0]["score"] == 100

    def test_fansub_exclusion_dominates_tier_bonus(self):
        results = _results("[Erai-raws] Show - 01")
        _apply_release_group_tiers(results, ["Erai-raws"], step=10)
        _apply_fansub_rules(results, preferred=[], excluded=["Erai-raws"], bonus=20)
        assert results[0]["score"] < 0


class TestTierConfigService:
    def test_get_defaults_when_unset(self, app_ctx):
        from services.release_group_tiers import DEFAULT_STEP, get_tier_config

        config = get_tier_config()
        assert config == {"tiers": [], "step": DEFAULT_STEP}

    def test_set_and_get_roundtrip(self, app_ctx):
        from services.release_group_tiers import get_tier_config, set_tier_config

        set_tier_config(["Erai-raws", "SubsPlease"], step=15)
        config = get_tier_config()
        assert config["tiers"] == ["Erai-raws", "SubsPlease"]
        assert config["step"] == 15

    def test_set_sanitizes_and_dedupes(self, app_ctx):
        from services.release_group_tiers import set_tier_config

        config = set_tier_config([" Erai-raws ", "", "erai-RAWS", "Judas"], step=10)
        assert config["tiers"] == ["Erai-raws", "Judas"]

    def test_set_rejects_non_string_entries(self, app_ctx):
        from services.release_group_tiers import set_tier_config

        with pytest.raises(ValueError):
            set_tier_config(["ok", 42], step=10)

    def test_set_rejects_step_out_of_range(self, app_ctx):
        from services.release_group_tiers import set_tier_config

        with pytest.raises(ValueError):
            set_tier_config(["Erai-raws"], step=0)
        with pytest.raises(ValueError):
            set_tier_config(["Erai-raws"], step=501)

    def test_set_rejects_overlong_group_name(self, app_ctx):
        from services.release_group_tiers import set_tier_config

        with pytest.raises(ValueError):
            set_tier_config(["x" * 101], step=10)

    def test_get_survives_corrupt_config(self, app_ctx):
        from db.config import save_config_entry
        from services.release_group_tiers import CONFIG_KEY, DEFAULT_STEP, get_tier_config

        save_config_entry(CONFIG_KEY, "not json {")
        assert get_tier_config() == {"tiers": [], "step": DEFAULT_STEP}


class TestTierRoutes:
    def test_get_returns_defaults(self, client):
        r = client.get("/api/v1/scoring/release-group-tiers")
        assert r.status_code == 200
        data = r.get_json()
        assert data["tiers"] == []
        assert isinstance(data["step"], int)

    def test_put_then_get_roundtrip(self, client):
        r = client.put(
            "/api/v1/scoring/release-group-tiers",
            json={"tiers": ["Erai-raws", "SubsPlease", "Judas"], "step": 12},
        )
        assert r.status_code == 200
        assert r.get_json()["tiers"] == ["Erai-raws", "SubsPlease", "Judas"]

        r = client.get("/api/v1/scoring/release-group-tiers")
        assert r.get_json() == {"tiers": ["Erai-raws", "SubsPlease", "Judas"], "step": 12}

    def test_put_empty_list_disables_tiers(self, client):
        client.put(
            "/api/v1/scoring/release-group-tiers",
            json={"tiers": ["Erai-raws"], "step": 10},
        )
        r = client.put("/api/v1/scoring/release-group-tiers", json={"tiers": [], "step": 10})
        assert r.status_code == 200
        assert r.get_json()["tiers"] == []

    def test_put_rejects_bad_payload(self, client):
        r = client.put("/api/v1/scoring/release-group-tiers", json={"tiers": "Erai-raws"})
        assert r.status_code == 400
        r = client.put(
            "/api/v1/scoring/release-group-tiers",
            json={"tiers": ["Erai-raws"], "step": "abc"},
        )
        assert r.status_code == 400

    def test_put_defaults_step_when_omitted(self, client):
        from services.release_group_tiers import DEFAULT_STEP

        r = client.put("/api/v1/scoring/release-group-tiers", json={"tiers": ["Erai-raws"]})
        assert r.status_code == 200
        assert r.get_json()["step"] == DEFAULT_STEP
