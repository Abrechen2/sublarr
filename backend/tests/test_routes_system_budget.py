"""Tests for /api/v1/system/budget endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _fake_provider(name, tier="free", rate_limits=None):
    p = MagicMock()
    p.name = name
    p.tier = tier
    type(p).rate_limits = rate_limits or {
        "free": {"second": 5, "hour": 200, "day": 1000},
    }
    return p


def test_budget_endpoint_returns_shape_for_registered_providers(client):
    p_os = _fake_provider("opensubtitles")
    p_subdl = _fake_provider("subdl")
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p_os, "subdl": p_subdl}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    assert resp.status_code == 200
    data = resp.get_json()
    assert set(data.keys()) == {"providers", "enabled"}
    assert isinstance(data["providers"], list)
    assert len(data["providers"]) == 2
    # sorted by name — opensubtitles, subdl
    names = [p["name"] for p in data["providers"]]
    assert names == sorted(names)
    for p in data["providers"]:
        assert set(p.keys()) == {
            "name",
            "tier",
            "limits",
            "usage",
            "reset_seconds",
            "learning",
            "keys",
        }
        assert set(p["reset_seconds"].keys()) == {"second", "hour", "day"}


def test_budget_endpoint_reflects_usage(client):
    p = _fake_provider("opensubtitles")
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        # Prime the singleton with real consume() so the endpoint reads actual usage
        from services.provider_budget import get_budget_manager

        bm = get_budget_manager()
        bm.consume("opensubtitles")
        bm.consume("opensubtitles")
        bm.consume("opensubtitles")

        resp = client.get("/api/v1/system/budget")

    assert resp.status_code == 200
    prov = resp.get_json()["providers"][0]
    assert prov["usage"]["day"] == 3


def test_budget_endpoint_uses_tier_limits(client):
    p = _fake_provider(
        "opensubtitles",
        tier="vip",
        rate_limits={"free": {"day": 1000}, "vip": {"day": 10000}},
    )
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    data = resp.get_json()
    assert data["providers"][0]["tier"] == "vip"
    assert data["providers"][0]["limits"]["day"] == 10000


def test_budget_endpoint_reports_disabled_flag(client):
    mgr = MagicMock()
    mgr._providers = {}

    from config import get_settings

    s = get_settings()
    original = getattr(s, "provider_budget_enabled", True)
    try:
        setattr(s, "provider_budget_enabled", False)
        with patch("routes.system.budget.get_provider_manager", return_value=mgr):
            resp = client.get("/api/v1/system/budget")
    finally:
        setattr(s, "provider_budget_enabled", original)

    assert resp.get_json()["enabled"] is False


def test_budget_endpoint_returns_learning_block_per_provider(client):
    """After a recorded 429, the endpoint surfaces the learned row for that provider."""
    from datetime import UTC, datetime

    from db.repositories.provider_learned_limits import ProviderLearnedLimitsRepository

    p_os = _fake_provider("opensubtitles")
    p_subdl = _fake_provider("subdl")
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p_os, "subdl": p_subdl}

    now = datetime.now(UTC)
    # Seed the learned row via the test client's app context so we share one
    # Flask app with the endpoint call — two nested app contexts collide on
    # teardown.
    with client.application.app_context():
        ProviderLearnedLimitsRepository().upsert_on_429(
            provider="opensubtitles",
            window="day",
            configured_limit=1000,
            observed_limit=None,
            now=now,
        )

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    assert resp.status_code == 200
    body = resp.get_json()
    os_row = next(p for p in body["providers"] if p["name"] == "opensubtitles")
    assert os_row["learning"] is not None
    assert os_row["learning"]["adjustment_factor"] == pytest.approx(0.9)
    assert os_row["learning"]["consecutive_good_days"] == 0
    assert os_row["learning"]["last_429_at"] is not None  # ISO string


def test_budget_endpoint_returns_null_learning_when_no_row(client):
    """Providers without a learned row surface learning=None."""
    p = _fake_provider("subdl")
    mgr = MagicMock()
    mgr._providers = {"subdl": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    body = resp.get_json()
    assert body["providers"][0]["learning"] is None


def test_budget_endpoint_returns_keys_breakdown(client):
    """After adding 2 pool rows, /system/budget reports aggregate + per-key."""
    from db.repositories.provider_account_pool import ProviderAccountPoolRepository

    # Seed rows inside the test-client's app context so we share one Flask app
    # with the endpoint call — two nested app contexts collide on teardown.
    with client.application.app_context():
        repo = ProviderAccountPoolRepository()
        repo.add(provider="opensubtitles", label="primary", api_key="a", tier="free")
        repo.add(provider="opensubtitles", label="backup", api_key="b", tier="vip")

    p = _fake_provider(
        "opensubtitles",
        rate_limits={
            "free": {"second": 5, "hour": 200, "day": 1000},
            "vip": {"second": 10, "hour": 1000, "day": 10000},
        },
    )
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    body = resp.get_json()
    os_row = next(r for r in body["providers"] if r["name"] == "opensubtitles")
    # Highest-tier wins as outer tier
    assert os_row["tier"] == "vip"
    # free=1000 + vip=10000 aggregated
    assert os_row["limits"]["day"] == 11000
    assert len(os_row["keys"]) == 2
    labels = {k["label"] for k in os_row["keys"]}
    assert labels == {"primary", "backup"}
    # Each key reports its own tier-specific limit
    primary = next(k for k in os_row["keys"] if k["label"] == "primary")
    backup = next(k for k in os_row["keys"] if k["label"] == "backup")
    assert primary["tier"] == "free"
    assert primary["limit"]["day"] == 1000
    assert backup["tier"] == "vip"
    assert backup["limit"]["day"] == 10000


def test_budget_endpoint_empty_pool_falls_back_to_provider_instance(client):
    """When no pool rows exist, report the legacy provider instance limits and keys=[]."""
    p = _fake_provider("subdl", tier="free")
    mgr = MagicMock()
    mgr._providers = {"subdl": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")

    body = resp.get_json()
    subdl_row = next(r for r in body["providers"] if r["name"] == "subdl")
    assert subdl_row["tier"] == "free"
    assert subdl_row["limits"]["day"] == 1000  # from _fake_provider default
    assert subdl_row["keys"] == []
