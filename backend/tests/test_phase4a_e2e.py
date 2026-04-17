"""Phase 4a end-to-end tests: multi-key aggregate, min-per-day, priority override."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from db.models.core import SeriesSettings, WantedItem
from db.repositories.provider_account_pool import ProviderAccountPoolRepository
from db.repositories.wanted import WantedRepository
from extensions import db


def _seed_item(**overrides):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    defaults = dict(
        item_type="episode",
        file_path=f"/m/{overrides.get('title', 'x')}.mkv",
        title=overrides.get("title", "x"),
        season_episode="S01E01",
        status="wanted",
        target_language="de",
        subtitle_type="full",
        added_at=now,
        updated_at=now,
        priority="standard",
    )
    defaults.update(overrides)
    item = WantedItem(**defaults)
    db.session.add(item)
    db.session.commit()
    return item


def _seed_settings(series_id: int, override=None, min_per_day=0):
    s = SeriesSettings(
        sonarr_series_id=series_id,
        absolute_order=0,
        priority_override=override,
        min_attempts_per_day=min_per_day,
        updated_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    db.session.add(s)
    db.session.commit()
    return s


def test_aggregate_budget_doubles_with_two_vip_keys(client):
    """Phase 4a exit criterion: 2nd OpenSubtitles VIP key doubles aggregate day-budget."""
    with client.application.app_context():
        repo = ProviderAccountPoolRepository()
        repo.add(provider="opensubtitles", label="primary", api_key="a", tier="vip")
        repo.add(provider="opensubtitles", label="backup", api_key="b", tier="vip")

    p = MagicMock()
    p.name = "opensubtitles"
    p.tier = "vip"
    type(p).rate_limits = {
        "free": {"second": 5, "hour": 200, "day": 1000},
        "vip": {"second": 10, "hour": 1000, "day": 10000},
    }
    mgr = MagicMock()
    mgr._providers = {"opensubtitles": p}

    with patch("routes.system.budget.get_provider_manager", return_value=mgr):
        resp = client.get("/api/v1/system/budget")
    assert resp.status_code == 200
    body = resp.get_json()
    os_row = next(r for r in body["providers"] if r["name"] == "opensubtitles")
    assert os_row["tier"] == "vip"
    assert os_row["limits"]["day"] == 20000  # 10000 * 2
    assert len(os_row["keys"]) == 2
    labels = {k["label"] for k in os_row["keys"]}
    assert labels == {"primary", "backup"}


def test_min_attempts_per_day_guarantees_inclusion(client):
    """Phase 4a exit criterion: series with min_attempts_per_day=3 included every tick."""
    with client.application.app_context():
        _seed_settings(series_id=100, min_per_day=3)
        boss = [_seed_item(title=f"boss-{i}", sonarr_series_id=100) for i in range(5)]
        _ = [_seed_item(title=f"other-{i}") for i in range(10)]

        from services.wanted_search_runner import _collect_min_attempts_items

        prefix = _collect_min_attempts_items()
        prefix_ids = [p["id"] for p in prefix]
        assert len(prefix_ids) == 3
        assert set(prefix_ids).issubset({b.id for b in boss})


def test_priority_override_wins_over_item_priority(client):
    """Phase 4a exit criterion: priority_override=premium promotes a backlog item."""
    with client.application.app_context():
        _seed_settings(series_id=200, override="premium")
        override_item = _seed_item(title="override", sonarr_series_id=200, priority="backlog")
        _seed_item(title="standard-other", sonarr_series_id=None, priority="standard")

        rows = WantedRepository().get_items_for_scheduled_search(limit=10, order="fair")
        ids = [r["id"] for r in rows]
        # override_item's series has priority_override=premium → rank 0
        # wins over the standard item (rank 1).
        assert ids[0] == override_item.id
