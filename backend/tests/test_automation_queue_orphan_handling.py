"""Queue rows must not outlive their usefulness.

Two production findings from Cardinal, 2026-08-27:

1. 25 embedded_extract rows whose wanted item had been deleted retried
   daily, forever — ``extract_embedded_sub`` raised ``ValueError`` for the
   vanished item, which the runner's generic branch put back on the backoff
   ladder. A vanished item never comes back; the established contract for
   that (see ``_translate_sidecar``) is ``FileNotFoundError`` → terminal.
   Note: an orphaned *auto_sync* row is NOT a defect — those work off
   snapshotted paths precisely because the item is deleted the moment its
   subtitle lands.

2. Nothing ever deleted finished rows: 5429 ``done`` and hundreds of
   terminally-failed rows had accumulated. ``purge_finished`` gives the
   queue the same retention treatment scheduler_job_runs already has.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)
from services.subtitle_automation_runner import SubtitleAutomationRunner


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


@pytest.fixture
def runner(app_ctx):
    return SubtitleAutomationRunner()


# ── vanished wanted item is terminal for embedded_extract ────────────────────


class TestVanishedItemIsTerminal:
    def test_extract_for_vanished_item_does_not_retry(self, repo, runner):
        """The real extractor raises FileNotFoundError for a missing item,
        and the runner must treat that as terminal — not backoff."""
        repo.enqueue(wanted_item_id=99999, file_path="/m/gone.mkv", target_language="ger")
        with patch(
            "services.subtitle_automation_runner._extract_embedded_sub",
            side_effect=FileNotFoundError("Wanted item 99999 no longer exists"),
        ):
            assert runner.process_one() is True
        e = repo.get_by_wanted_item(99999)
        assert e["state"] == "failed"
        assert e["next_retry_at"] is None

    def test_extractor_raises_file_not_found_for_missing_item(self, app_ctx):
        """Pin the exception type: ValueError here meant daily retries for a
        row that could never succeed."""
        from services.embedded_extractor import extract_embedded_sub

        with pytest.raises(FileNotFoundError, match="no longer exists"):
            extract_embedded_sub(987654321, "/m/whatever.mkv")


# ── retention for finished rows ──────────────────────────────────────────────


class TestPurgeFinished:
    def _age(self, repo, wanted_item_id: int, *, days: int) -> None:
        """Backdate a row's updated_at."""
        from db.models.core import SubtitleAutomationQueueEntry

        stamp = datetime.now(UTC) - timedelta(days=days)
        repo.session.query(SubtitleAutomationQueueEntry).filter(
            SubtitleAutomationQueueEntry.wanted_item_id == wanted_item_id
        ).update({"updated_at": stamp}, synchronize_session=False)
        repo.session.commit()

    def test_old_done_rows_are_purged(self, repo):
        repo.enqueue(wanted_item_id=1, file_path="/m/a.mkv", target_language="ger")
        entry = repo.get_by_wanted_item(1)
        repo.mark_done(entry["id"])
        self._age(repo, 1, days=10)

        assert repo.purge_finished() == 1
        assert repo.get_by_wanted_item(1) is None

    def test_recent_done_rows_survive(self, repo):
        repo.enqueue(wanted_item_id=2, file_path="/m/b.mkv", target_language="ger")
        repo.mark_done(repo.get_by_wanted_item(2)["id"])

        assert repo.purge_finished() == 0
        assert repo.get_by_wanted_item(2) is not None

    def test_old_terminal_failures_are_purged(self, repo):
        repo.enqueue(wanted_item_id=3, file_path="/m/c.mkv", target_language="ger")
        repo.mark_failed(
            repo.get_by_wanted_item(3)["id"], error="gone for good", next_retry_at=None
        )
        self._age(repo, 3, days=40)

        assert repo.purge_finished() == 1
        assert repo.get_by_wanted_item(3) is None

    def test_terminal_failures_are_kept_within_window(self, repo):
        """30 days of terminal failures stay visible for diagnosis."""
        repo.enqueue(wanted_item_id=4, file_path="/m/d.mkv", target_language="ger")
        repo.mark_failed(
            repo.get_by_wanted_item(4)["id"], error="gone for good", next_retry_at=None
        )
        self._age(repo, 4, days=10)

        assert repo.purge_finished() == 0
        assert repo.get_by_wanted_item(4) is not None

    def test_retrying_failures_are_never_purged(self, repo):
        """A row still on the backoff ladder is pending work, however old."""
        repo.enqueue(wanted_item_id=5, file_path="/m/e.mkv", target_language="ger")
        repo.mark_failed(
            repo.get_by_wanted_item(5)["id"],
            error="transient",
            next_retry_at=datetime.now(UTC) + timedelta(days=1),
        )
        self._age(repo, 5, days=400)

        assert repo.purge_finished() == 0
        assert repo.get_by_wanted_item(5) is not None

    def test_pending_rows_are_never_purged(self, repo):
        repo.enqueue(wanted_item_id=6, file_path="/m/f.mkv", target_language="ger")
        self._age(repo, 6, days=400)

        assert repo.purge_finished() == 0
        assert repo.get_by_wanted_item(6) is not None


# ── wired into the scheduler history cleanup tick ────────────────────────────


def test_history_cleanup_tick_also_purges_queue(app_ctx):
    from utils import scheduler_retention

    with (
        patch.object(scheduler_retention, "delete_old_job_runs", return_value=3) as jr,
        patch.object(SubtitleAutomationQueueRepository, "purge_finished", return_value=2) as pf,
    ):
        scheduler_retention.internal_history_cleanup()
    jr.assert_called_once()
    pf.assert_called_once()
