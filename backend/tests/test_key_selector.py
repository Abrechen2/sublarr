"""Tests for KeySelector (Phase 4a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from services.key_selector import KeySelector


def _row(
    id_=1,
    label="primary",
    tier="free",
    api_key="k",
    enabled=True,
    last_429_at=None,
):
    return {
        "id": id_,
        "account_label": label,
        "api_key": api_key,
        "username": None,
        "password": None,
        "tier": tier,
        "enabled": enabled,
        "last_used_at": None,
        "last_429_at": last_429_at,
    }


def test_pick_returns_none_when_pool_empty():
    sel = KeySelector()
    with patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo:
        MockRepo.return_value.get_enabled_for.return_value = []
        assert sel.pick("opensubtitles", provider_rate_limits={}) is None


def test_pick_prefers_highest_remaining_day_budget():
    sel = KeySelector()
    rows = [
        _row(id_=1, label="free_key", tier="free"),
        _row(id_=2, label="vip_key", tier="vip"),
    ]
    rate_limits = {
        "free": {"day": 200, "hour": 20, "second": 1},
        "vip": {"day": 10000, "hour": 1000, "second": 10},
    }
    usage = {1: {"day": 100}, 2: {"day": 500}}
    with (
        patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo,
        patch("services.key_selector.get_budget_manager") as bm_mock,
    ):
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = usage
        picked = sel.pick("opensubtitles", provider_rate_limits=rate_limits)
    # free_key: 200 - 100 = 100; vip_key: 10000 - 500 = 9500. vip wins.
    assert picked["id"] == 2


def test_pick_excludes_row_in_429_cooldown():
    sel = KeySelector()
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    hot = _row(id_=1, label="hot", tier="vip", last_429_at=now - timedelta(seconds=30))
    cool = _row(id_=2, label="cool", tier="free")
    rate_limits = {
        "free": {"day": 200},
        "vip": {"day": 10000},
    }
    with (
        patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo,
        patch("services.key_selector.get_budget_manager") as bm_mock,
    ):
        MockRepo.return_value.get_enabled_for.return_value = [hot, cool]
        bm_mock.return_value.get_usage_per_key.return_value = {}
        picked = sel.pick(
            "opensubtitles",
            provider_rate_limits=rate_limits,
            retry_after_seconds=60,
            now=now,
        )
    assert picked["id"] == 2


def test_pick_returns_none_when_all_cooling_down():
    sel = KeySelector()
    now = datetime(2026, 4, 17, 12, 0, tzinfo=UTC)
    hot1 = _row(id_=1, label="h1", last_429_at=now - timedelta(seconds=30))
    hot2 = _row(id_=2, label="h2", last_429_at=now - timedelta(seconds=30))
    with (
        patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo,
        patch("services.key_selector.get_budget_manager") as bm_mock,
    ):
        MockRepo.return_value.get_enabled_for.return_value = [hot1, hot2]
        bm_mock.return_value.get_usage_per_key.return_value = {}
        picked = sel.pick(
            "opensubtitles",
            provider_rate_limits={"free": {"day": 200}},
            retry_after_seconds=60,
            now=now,
        )
    assert picked is None


def test_cache_avoids_repeated_db_reads_within_ttl():
    sel = KeySelector()
    rows = [_row()]
    with (
        patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo,
        patch("services.key_selector.get_budget_manager") as bm_mock,
    ):
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = {}
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
    assert MockRepo.return_value.get_enabled_for.call_count == 1


def test_invalidate_forces_refresh():
    sel = KeySelector()
    rows = [_row()]
    with (
        patch("services.key_selector.ProviderAccountPoolRepository") as MockRepo,
        patch("services.key_selector.get_budget_manager") as bm_mock,
    ):
        MockRepo.return_value.get_enabled_for.return_value = rows
        bm_mock.return_value.get_usage_per_key.return_value = {}
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
        sel.invalidate("os")
        sel.pick("os", provider_rate_limits={"free": {"day": 200}})
    assert MockRepo.return_value.get_enabled_for.call_count == 2
