"""Schema tests for 0.71.0 subtitle automation: new column + new table.

Covers:
- `SeriesSettings.cleanup_foreign_tracks` nullable Boolean (NULL = inherit global).
- `SubtitleAutomationQueueEntry` model + table with index on (state, next_retry_at)
  and unique constraint on wanted_item_id.
"""

from datetime import UTC, datetime

import pytest

from db.models.core import SeriesSettings, SubtitleAutomationQueueEntry


class TestSeriesSettingsCleanupFlag:
    """`cleanup_foreign_tracks`: nullable bool on SeriesSettings.

    NULL = inherit global default. True/False = explicit override.
    """

    def test_column_exists_and_defaults_to_none(self):
        ss = SeriesSettings(
            sonarr_series_id=1,
            absolute_order=0,
            updated_at=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assert hasattr(ss, "cleanup_foreign_tracks")
        assert ss.cleanup_foreign_tracks is None

    def test_column_accepts_true(self):
        ss = SeriesSettings(
            sonarr_series_id=2,
            absolute_order=0,
            cleanup_foreign_tracks=True,
            updated_at=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assert ss.cleanup_foreign_tracks is True

    def test_column_accepts_false(self):
        ss = SeriesSettings(
            sonarr_series_id=3,
            absolute_order=0,
            cleanup_foreign_tracks=False,
            updated_at=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assert ss.cleanup_foreign_tracks is False


class TestSubtitleAutomationQueue:
    """`subtitle_automation_queue` — persistent drain queue for auto-extract.

    Each pending embedded-extract gets a row. Rows survive restarts so the
    drain worker can pick up where it left off. One row per wanted_item.
    """

    def test_queue_entry_model_exists(self):
        entry = SubtitleAutomationQueueEntry(
            wanted_item_id=42,
            file_path="/media/Anime/Foo.mkv",
            target_language="ger",
            state="pending",
            attempt_count=0,
            created_at=datetime(2026, 4, 21, tzinfo=UTC),
            updated_at=datetime(2026, 4, 21, tzinfo=UTC),
        )
        assert entry.wanted_item_id == 42
        assert entry.state == "pending"
        assert entry.attempt_count == 0

    def test_queue_entry_defaults(self):
        # SQLAlchemy sets defaults at flush, not assignment. Verify default is
        # declared at column level instead of exercising flush here.
        state_col = SubtitleAutomationQueueEntry.__table__.c.state
        assert state_col.default is not None
        assert state_col.default.arg == "pending"

    def test_queue_entry_accepts_all_state_transitions(self):
        """State machine: pending → running → done | failed."""
        for state in ("pending", "running", "done", "failed"):
            entry = SubtitleAutomationQueueEntry(
                wanted_item_id=100 + hash(state) % 1000,
                file_path=f"/media/{state}.mkv",
                target_language="ger",
                state=state,
                created_at=datetime(2026, 4, 21, tzinfo=UTC),
                updated_at=datetime(2026, 4, 21, tzinfo=UTC),
            )
            assert entry.state == state

    def test_table_has_wanted_item_unique_constraint(self):
        """One row per wanted_item — prevents duplicate enqueue."""
        table = SubtitleAutomationQueueEntry.__table__
        unique_cols = set()
        for constraint in table.constraints:
            if constraint.__class__.__name__ == "UniqueConstraint":
                unique_cols |= {c.name for c in constraint.columns}
        # Check either UniqueConstraint OR unique=True on column itself.
        wanted_col = table.c.wanted_item_id
        assert wanted_col.unique is True or "wanted_item_id" in unique_cols

    def test_table_has_drain_lookup_index(self):
        """Drain worker queries `WHERE state IN (pending, running) AND
        next_retry_at <= now ORDER BY next_retry_at` — needs composite index."""
        table = SubtitleAutomationQueueEntry.__table__
        index_cols_sets = [tuple(c.name for c in idx.columns) for idx in table.indexes]
        assert any("state" in cols and "next_retry_at" in cols for cols in index_cols_sets), (
            f"No (state, next_retry_at) composite index found; got {index_cols_sets}"
        )

    def test_all_queue_columns_present(self):
        """Spec columns per 0.71.0 design."""
        cols = {c.name for c in SubtitleAutomationQueueEntry.__table__.c}
        expected = {
            "id",
            "wanted_item_id",
            "file_path",
            "target_language",
            "state",
            "attempt_count",
            "next_retry_at",
            "last_error",
            "last_started_at",
            "last_finished_at",
            "created_at",
            "updated_at",
        }
        missing = expected - cols
        assert not missing, f"Missing columns: {missing}"


class TestModelExports:
    """Ensure new model is exported from the models package."""

    def test_queue_entry_exported(self):
        from db.models import core

        assert "SubtitleAutomationQueueEntry" in core.__all__
