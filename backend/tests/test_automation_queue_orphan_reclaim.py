"""Orphaned `running` rows must be reclaimed at scheduler startup.

Prod 2026-08-15: two `sidecar_translate` rows sat in `running` for 10h19m
and 4h32m. Both were claimed before the 04:37 container restart, so the
worker threads holding them were long dead. Nothing ever moved them back:

- `claim_next()` transitions `pending` -> `running`
- only `mark_done()` / `mark_failed()` leave that state
- `enqueue()` deliberately keeps an existing `running` row as-is, so a
  fresh search does not rescue one either

Result: every process restart silently strands whatever item was in
flight. No retry, no error, it just falls out of the queue.

The scheduler already reconciles its own abandoned rows at startup via
`reconcile_stale_runs()`. These tests pin the missing counterpart for
the automation queue.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


def _claimed_row(repo, wanted_item_id: int, *, started_at: datetime) -> int:
    """Enqueue one item, claim it, and backdate its `last_started_at`."""
    entry_id = repo.enqueue(
        wanted_item_id=wanted_item_id,
        file_path=f"/media/Anime/{wanted_item_id}.mkv",
        target_language="ger",
    )
    claimed = repo.claim_next()
    assert claimed is not None, "claim_next should hand out the pending row"
    assert claimed["id"] == entry_id
    _backdate(repo, entry_id, started_at)
    return entry_id


def _backdate(repo, entry_id: int, started_at: datetime) -> None:
    from db.models.core import SubtitleAutomationQueueEntry

    repo.session.query(SubtitleAutomationQueueEntry).filter(
        SubtitleAutomationQueueEntry.id == entry_id
    ).update({"last_started_at": started_at}, synchronize_session=False)
    repo.session.commit()


class TestReclaimOrphaned:
    def test_running_row_is_returned_to_pending(self, repo):
        """The confirmed prod case: a row claimed by a dead process."""
        stale = datetime.now(UTC) - timedelta(hours=10)
        entry_id = _claimed_row(repo, 9001, started_at=stale)
        assert repo.get_by_id(entry_id)["state"] == "running"

        reclaimed = repo.reclaim_orphaned()

        assert reclaimed == 1
        row = repo.get_by_id(entry_id)
        assert row["state"] == "pending"
        assert row["next_retry_at"] is None, "must be eligible immediately"

    def test_reclaimed_row_is_claimable_again(self, repo):
        """Reclaiming is pointless unless the drain can pick the row up."""
        entry_id = _claimed_row(repo, 9002, started_at=datetime.now(UTC) - timedelta(hours=5))
        repo.reclaim_orphaned()

        claimed = repo.claim_next()
        assert claimed is not None
        assert claimed["id"] == entry_id

    def test_attempt_count_is_incremented(self, repo):
        """A row that kills the worker every boot must not loop forever.

        `attempt_count` is the only signal the backoff ladder has, so an
        interruption has to leave a mark.
        """
        entry_id = _claimed_row(repo, 9003, started_at=datetime.now(UTC) - timedelta(hours=5))
        before = repo.get_by_id(entry_id)["attempt_count"]

        repo.reclaim_orphaned()

        assert repo.get_by_id(entry_id)["attempt_count"] == before + 1

    def test_reason_is_recorded(self, repo):
        entry_id = _claimed_row(repo, 9004, started_at=datetime.now(UTC) - timedelta(hours=5))
        repo.reclaim_orphaned()

        assert "interrupted" in (repo.get_by_id(entry_id)["last_error"] or "").lower()

    def test_terminal_and_waiting_rows_are_untouched(self, repo):
        """Only `running` is ambiguous — the other states own themselves."""
        done_id = repo.enqueue(wanted_item_id=9101, file_path="/a.mkv", target_language="ger")
        repo.claim_next()
        repo.mark_done(done_id)

        failed_id = repo.enqueue(wanted_item_id=9102, file_path="/b.mkv", target_language="ger")
        repo.claim_next()
        retry_at = datetime.now(UTC) + timedelta(hours=1)
        repo.mark_failed(failed_id, error="boom", next_retry_at=retry_at)

        pending_id = repo.enqueue(wanted_item_id=9103, file_path="/c.mkv", target_language="ger")

        assert repo.reclaim_orphaned() == 0
        assert repo.get_by_id(done_id)["state"] == "done"
        assert repo.get_by_id(failed_id)["state"] == "failed"
        assert repo.get_by_id(pending_id)["state"] == "pending"

    def test_grace_period_spares_a_fresh_claim(self, repo):
        """With a grace window, an in-flight item must survive."""
        fresh_id = _claimed_row(repo, 9201, started_at=datetime.now(UTC))
        old_id = _claimed_row(repo, 9202, started_at=datetime.now(UTC) - timedelta(hours=3))

        reclaimed = repo.reclaim_orphaned(grace_minutes=60)

        assert reclaimed == 1
        assert repo.get_by_id(fresh_id)["state"] == "running"
        assert repo.get_by_id(old_id)["state"] == "pending"

    def test_empty_queue_is_a_noop(self, repo):
        assert repo.reclaim_orphaned() == 0


def test_bootstrap_reclaims_the_orphan(monkeypatch, tmp_path):
    """The whole point: a real startup has to release the stranded claim.

    Goes through `bootstrap_scheduler` rather than calling the repository
    directly, so removing the wiring fails this test instead of passing
    quietly.
    """
    monkeypatch.setenv("SUBLARR_SCHEDULER_ROLE", "primary")
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
        repo = SubtitleAutomationQueueRepository()
        entry_id = repo.enqueue(
            wanted_item_id=9301,
            file_path="/media/Anime/stranded.mkv",
            target_language="ger",
        )
        repo.claim_next()
        _backdate(repo, entry_id, datetime.now(UTC) - timedelta(hours=10))
        assert repo.get_by_id(entry_id)["state"] == "running"

    from services.scheduler import bootstrap_scheduler

    s = bootstrap_scheduler(app)
    try:
        with app.app_context():
            row = SubtitleAutomationQueueRepository().get_by_id(entry_id)
        assert row["state"] == "pending"
    finally:
        if s is not None:
            s.shutdown(timeout_s=2)
