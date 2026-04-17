"""Per-series priority_override tests (Phase 4a)."""

from __future__ import annotations

from datetime import UTC, datetime

from db.models.core import SeriesSettings, WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def _make_item(
    file_path: str,
    sonarr_series_id: int | None = None,
    priority: str = "standard",
):
    now = datetime(2026, 4, 17, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=file_path,
        title=file_path,
        season_episode="S01E01",
        status="wanted",
        target_language="de",
        subtitle_type="full",
        priority=priority,
        sonarr_series_id=sonarr_series_id,
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def _make_settings(
    sonarr_series_id: int,
    override: str | None,
    min_per_day: int = 0,
):
    s = SeriesSettings(
        sonarr_series_id=sonarr_series_id,
        absolute_order=0,
        priority_override=override,
        min_attempts_per_day=min_per_day,
        updated_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    db.session.add(s)
    db.session.commit()
    return s


def test_priority_override_wins_over_item_priority(app_ctx):
    """Item says backlog, series override says premium — override wins."""
    _make_settings(sonarr_series_id=100, override="premium")
    boss = _make_item("/m/boss.mkv", sonarr_series_id=100, priority="backlog")
    other = _make_item("/m/other.mkv", sonarr_series_id=None, priority="standard")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    ids = [r["id"] for r in rows]
    assert ids.index(boss.id) < ids.index(other.id)


def test_null_override_does_not_affect_ranking(app_ctx):
    """When override is NULL, item.priority wins normally."""
    _make_settings(sonarr_series_id=100, override=None)
    a = _make_item("/m/a.mkv", sonarr_series_id=100, priority="backlog")
    b = _make_item("/m/b.mkv", sonarr_series_id=None, priority="premium")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    # b (premium) wins over a (backlog) — normal Phase-1 order.
    assert [r["id"] for r in rows] == [b.id, a.id]


def test_override_on_standalone_item_has_no_effect(app_ctx):
    """Items with sonarr_series_id=None never LEFT-JOIN a settings row."""
    a = _make_item("/m/a.mkv", sonarr_series_id=None, priority="backlog")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    assert rows[0]["id"] == a.id  # present, no error


def test_override_backlog_demotes_item(app_ctx):
    """Item has premium, override demotes to backlog — override wins."""
    _make_settings(sonarr_series_id=100, override="backlog")
    demoted = _make_item("/m/demoted.mkv", sonarr_series_id=100, priority="premium")
    standard = _make_item("/m/std.mkv", sonarr_series_id=None, priority="standard")
    repo = WantedRepository()
    rows = repo.get_items_for_scheduled_search(limit=10, order="fair")
    # demoted should now rank AFTER standard.
    ids = [r["id"] for r in rows]
    assert ids.index(standard.id) < ids.index(demoted.id)
