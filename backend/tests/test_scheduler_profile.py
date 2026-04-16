"""Tests for services.scheduler_profile — preset resolution + hardware recommendation."""

import pytest

from services.scheduler_profile import PROFILES, apply_profile, recommend_profile


class TestApplyProfile:
    def test_light_returns_expected_values(self):
        result = apply_profile("light")
        assert result["wanted_search_max_items_per_run"] == 100
        assert result["provider_budget_safety_margin_pct"] == 40

    def test_balanced_returns_expected_values(self):
        result = apply_profile("balanced")
        assert result["wanted_search_max_items_per_run"] == 500
        assert result["provider_budget_safety_margin_pct"] == 20

    def test_aggressive_returns_expected_values(self):
        result = apply_profile("aggressive")
        assert result["wanted_search_max_items_per_run"] == 2000
        assert result["provider_budget_safety_margin_pct"] == 10

    def test_custom_returns_empty_dict(self):
        assert apply_profile("custom") == {}

    def test_unknown_profile_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown scheduler profile"):
            apply_profile("turbo")

    def test_returned_dict_is_a_copy(self):
        """Mutating the returned dict must not pollute the preset table."""
        result = apply_profile("light")
        result["wanted_search_max_items_per_run"] = 9999
        assert PROFILES["light"]["wanted_search_max_items_per_run"] == 100


class TestRecommendProfile:
    def test_low_cpu_recommends_light(self):
        assert recommend_profile(cpu_count=2, ram_gb=8) == "light"

    def test_low_ram_recommends_light(self):
        assert recommend_profile(cpu_count=8, ram_gb=2) == "light"

    def test_high_spec_recommends_aggressive(self):
        assert recommend_profile(cpu_count=12, ram_gb=16) == "aggressive"

    def test_mid_spec_recommends_balanced(self):
        assert recommend_profile(cpu_count=4, ram_gb=4) == "balanced"

    def test_boundary_low_inclusive(self):
        """cpu_count==2 OR ram_gb==2 is light (inclusive boundary)."""
        assert recommend_profile(cpu_count=2, ram_gb=16) == "light"
        assert recommend_profile(cpu_count=16, ram_gb=2) == "light"

    def test_boundary_high_inclusive(self):
        """cpu_count>=8 AND ram_gb>=8 is aggressive."""
        assert recommend_profile(cpu_count=8, ram_gb=8) == "aggressive"
