"""Foreign-track sweep: cleanup_history rows, stats and the one-off backfill.

The owner asked (2026-09-26) whether the statistics page records how much the
sweep freed — it did not: every slice's result was only logged. These tests
pin down the history row per slice, the stats aggregate built from it, and
the backfill for strips that happened before the row existed.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from services.foreign_tracks import sweep as sw

ACTION = "scheduled_foreign_track_sweep"
INT4_MAX = 2_147_483_647


def _result(**overrides):
    base = {
        "phase": "strip",
        "probed": 3,
        "stripped_files": 2,
        "tracks_removed": 5,
        "bytes_freed": 1234,
        "pending": 0,
        "affected": 4,
        "paused_reason": None,
    }
    base.update(overrides)
    return base


def _history(action=ACTION):
    from sqlalchemy import select

    from db.models.cleanup import CleanupHistory
    from extensions import db

    return list(
        db.session.execute(
            select(CleanupHistory)
            .where(CleanupHistory.action_type == action)
            .order_by(CleanupHistory.id)
        ).scalars()
    )


@pytest.fixture
def tick_env(app_ctx, monkeypatch, tmp_path):
    """Drive foreign_track_sweep_tick with a canned slice result."""
    monkeypatch.setattr(
        "config.get_settings",
        lambda: SimpleNamespace(
            foreign_track_sweep_enabled=True,
            foreign_track_sweep_budget_s=60,
            media_path=str(tmp_path),
        ),
    )
    monkeypatch.setattr(sw, "_find_rule", lambda repo: {"id": 7, "config_json": {}})
    holder = {"result": _result()}
    monkeypatch.setattr(sw, "run_slice", lambda *a, **k: dict(holder["result"]))
    return holder


# ── 1. one history row per slice that stripped something ─────────────────────


def test_tick_writes_one_history_row_when_files_were_stripped(tick_env):
    sw.foreign_track_sweep_tick()

    rows = _history()
    assert len(rows) == 1
    row = rows[0]
    assert row.rule_id == 7
    assert row.files_processed == 2
    assert row.files_deleted == 0
    assert row.bytes_freed == 1234
    assert json.loads(row.details_json) == {
        "tracks_removed": 5,
        "probed": 3,
        "phase": "strip",
        "backups_deleted": 0,
        "verify_failed": 0,
    }


def test_tick_writes_nothing_when_no_file_was_stripped(tick_env):
    tick_env["result"] = _result(stripped_files=0, tracks_removed=0, bytes_freed=0)

    sw.foreign_track_sweep_tick()

    assert _history() == []


def test_failing_history_write_never_fails_the_tick(tick_env, monkeypatch, caplog):
    from db.repositories.cleanup import CleanupRepository

    def boom(self, *a, **k):
        raise RuntimeError("db gone")

    monkeypatch.setattr(CleanupRepository, "log_cleanup", boom)
    caplog.set_level(logging.WARNING, logger="services.foreign_tracks.stats")

    sw.foreign_track_sweep_tick()  # must not raise

    assert any("db gone" in r.getMessage() for r in caplog.records)


def test_slice_larger_than_int4_is_split_across_rows(tick_env):
    """cleanup_history.bytes_freed is INTEGER — int4 on Postgres."""
    big = INT4_MAX * 2 + 10
    tick_env["result"] = _result(bytes_freed=big)

    sw.foreign_track_sweep_tick()

    rows = _history()
    assert len(rows) == 3
    assert all(r.bytes_freed <= INT4_MAX for r in rows)
    assert sum(r.bytes_freed for r in rows) == big
    # Files and tracks are counted once, on the first row only.
    assert [r.files_processed for r in rows] == [2, 0, 0]
    assert sum(json.loads(r.details_json).get("tracks_removed", 0) for r in rows) == 5


# ── 2. stats aggregate + endpoint ─────────────────────────────────────────────


def _seed_scan(path, state, size=100, tracks=0, processed_at=None):
    from db.models.foreign_tracks import ForeignTrackScan
    from extensions import db

    db.session.add(
        ForeignTrackScan(
            path=path,
            size_bytes=size,
            mtime=0.0,
            state=state,
            track_count=tracks,
            processed_at=processed_at,
        )
    )
    db.session.commit()


def _seed_history(bytes_freed, files, tracks, days_ago=0, details=None):
    from db.models.cleanup import CleanupHistory
    from extensions import db

    db.session.add(
        CleanupHistory(
            rule_id=1,
            action_type=ACTION,
            files_processed=files,
            files_deleted=0,
            bytes_freed=bytes_freed,
            details_json=json.dumps(details or {"tracks_removed": tracks}),
            performed_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
    )
    db.session.commit()


def test_sweep_stats_aggregates_history_scan_counts_and_state(app_ctx):
    from services.foreign_tracks.state import SweepState, save_state
    from services.foreign_tracks.stats import get_sweep_stats

    _seed_history(1000, files=2, tracks=4, days_ago=1)
    _seed_history(500, files=1, tracks=3, days_ago=40)
    _seed_scan("/m/a.mkv", "stripped")
    _seed_scan("/m/b.mkv", "clean")
    _seed_scan("/m/c.mkv", "clean")
    _seed_scan("/m/d.mkv", "affected")
    save_state(SweepState(phase="strip", paused_reason="disk floor reached"))

    stats = get_sweep_stats()

    assert stats["files_stripped"] == 3
    assert stats["tracks_removed"] == 7
    assert stats["bytes_freed_total"] == 1500
    assert stats["bytes_freed_30d"] == 1000
    assert stats["scan_counts"] == {
        "pending": 0,
        "clean": 2,
        "affected": 1,
        "stripped": 1,
        "failed": 0,
    }
    assert stats["phase"] == "strip"
    assert stats["paused_reason"] == "disk floor reached"


def test_sweep_stats_empty_database(app_ctx):
    from services.foreign_tracks.stats import get_sweep_stats

    stats = get_sweep_stats()

    assert stats["files_stripped"] == 0
    assert stats["tracks_removed"] == 0
    assert stats["bytes_freed_total"] == 0
    assert stats["bytes_freed_30d"] == 0
    assert stats["phase"] == "idle"
    assert stats["paused_reason"] is None


def test_sweep_stats_endpoint(client):
    with client.application.app_context():
        _seed_history(2048, files=1, tracks=2)

    resp = client.get("/api/v1/statistics/foreign-tracks")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["bytes_freed_total"] == 2048
    assert data["files_stripped"] == 1
    assert data["tracks_removed"] == 2
    assert set(data["scan_counts"]) == {"pending", "clean", "affected", "stripped", "failed"}
    assert "phase" in data and "paused_reason" in data


# ── 3. backfill for strips made before the history row existed ────────────────


def _file(tmp_path, name, size):
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return str(path)


def test_backfill_sums_size_delta_of_stripped_rows(app_ctx, tmp_path):
    from services.foreign_tracks.stats import backfill_sweep_history

    old = datetime.now(UTC) - timedelta(days=3)
    _seed_scan(_file(tmp_path, "a.mkv", 600), "stripped", size=1000, tracks=2, processed_at=old)
    _seed_scan(_file(tmp_path, "b.mkv", 300), "stripped", size=500, tracks=3, processed_at=old)
    # Grew after the strip (replaced file): clamped to 0, still counted.
    _seed_scan(_file(tmp_path, "c.mkv", 900), "stripped", size=100, tracks=1, processed_at=old)
    # Missing file: skipped entirely.
    _seed_scan(str(tmp_path / "gone.mkv"), "stripped", size=999, tracks=9, processed_at=old)
    # Not stripped: ignored.
    _seed_scan(_file(tmp_path, "d.mkv", 10), "clean", size=5000, processed_at=old)

    summary = backfill_sweep_history(dry_run=False)

    assert summary["written"] is True
    assert summary["bytes_freed"] == 400 + 200
    rows = _history()
    assert len(rows) == 1
    assert rows[0].bytes_freed == 600
    assert rows[0].files_processed == 3
    details = json.loads(rows[0].details_json)
    assert details == {"backfill": True, "files": 3, "tracks_removed": 6}


def test_backfill_dry_run_writes_nothing(app_ctx, tmp_path):
    from services.foreign_tracks.stats import backfill_sweep_history

    old = datetime.now(UTC) - timedelta(days=3)
    _seed_scan(_file(tmp_path, "a.mkv", 600), "stripped", size=1000, tracks=2, processed_at=old)

    summary = backfill_sweep_history(dry_run=True)

    assert summary["written"] is False
    assert summary["bytes_freed"] == 400
    assert _history() == []


def test_backfill_is_idempotent(app_ctx, tmp_path):
    from services.foreign_tracks.stats import backfill_sweep_history

    old = datetime.now(UTC) - timedelta(days=3)
    _seed_scan(_file(tmp_path, "a.mkv", 600), "stripped", size=1000, tracks=2, processed_at=old)

    backfill_sweep_history(dry_run=False)
    second = backfill_sweep_history(dry_run=False)

    assert second["written"] is False
    assert second["reason"] == "already backfilled"
    assert len(_history()) == 1


def test_backfill_only_counts_strips_older_than_the_first_history_row(app_ctx, tmp_path):
    from services.foreign_tracks.stats import backfill_sweep_history

    _seed_history(50, files=1, tracks=1, days_ago=2)
    before = datetime.now(UTC) - timedelta(days=5)
    after = datetime.now(UTC) - timedelta(hours=1)
    _seed_scan(_file(tmp_path, "a.mkv", 600), "stripped", size=1000, tracks=2, processed_at=before)
    _seed_scan(_file(tmp_path, "b.mkv", 100), "stripped", size=900, tracks=7, processed_at=after)

    summary = backfill_sweep_history(dry_run=False)

    assert summary["files"] == 1
    assert summary["bytes_freed"] == 400
    assert summary["tracks_removed"] == 2


def test_backfill_larger_than_int4_splits_but_stays_one_backfill(app_ctx, tmp_path, monkeypatch):
    from services.foreign_tracks import stats as st

    old = datetime.now(UTC) - timedelta(days=3)
    path = _file(tmp_path, "a.mkv", 10)
    _seed_scan(path, "stripped", size=INT4_MAX + 10 + 10, tracks=4, processed_at=old)

    st.backfill_sweep_history(dry_run=False)
    again = st.backfill_sweep_history(dry_run=False)

    rows = _history()
    assert len(rows) == 2
    assert sum(r.bytes_freed for r in rows) == INT4_MAX + 10
    assert all(json.loads(r.details_json).get("backfill") is True for r in rows)
    assert again["written"] is False
    assert os.path.exists(path)
