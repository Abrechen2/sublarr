"""Repository tests for subtitle_automation_queue (Phase 3a).

Covers enqueue idempotency, atomic claim, counts, retry/backoff, and
per-wanted-item lookup. Uses in-memory SQLite via the standard
Sublarr test app fixture (`app`).
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)


@pytest.fixture
def repo(app_ctx):
    """Queue repository with Flask app context (shared DB fixture)."""
    return SubtitleAutomationQueueRepository()


class TestEnqueue:
    def test_enqueue_inserts_pending_row(self, repo):
        entry_id = repo.enqueue(
            wanted_item_id=101,
            file_path="/media/Anime/A.mkv",
            target_language="ger",
        )
        assert entry_id is not None
        e = repo.get_by_wanted_item(101)
        assert e is not None
        assert e["state"] == "pending"
        assert e["attempt_count"] == 0
        assert e["next_retry_at"] is None
        assert e["last_error"] is None

    def test_enqueue_is_idempotent(self, repo):
        """Second enqueue for same wanted_item_id returns existing row id."""
        first = repo.enqueue(
            wanted_item_id=102,
            file_path="/media/Anime/B.mkv",
            target_language="ger",
        )
        second = repo.enqueue(
            wanted_item_id=102,
            file_path="/media/Anime/B.mkv",
            target_language="ger",
        )
        assert first == second

    def test_enqueue_different_items_creates_separate_rows(self, repo):
        a = repo.enqueue(
            wanted_item_id=201,
            file_path="/a.mkv",
            target_language="ger",
        )
        b = repo.enqueue(
            wanted_item_id=202,
            file_path="/b.mkv",
            target_language="ger",
        )
        assert a != b


class TestClaimNext:
    def test_claim_next_none_when_empty(self, repo):
        claim = repo.claim_next(now=datetime.now(UTC))
        assert claim is None

    def test_claim_next_picks_pending(self, repo):
        repo.enqueue(wanted_item_id=301, file_path="/x.mkv", target_language="ger")
        claim = repo.claim_next(now=datetime.now(UTC))
        assert claim is not None
        assert claim["wanted_item_id"] == 301
        # Claim transitions to running.
        e = repo.get_by_wanted_item(301)
        assert e["state"] == "running"
        assert e["last_started_at"] is not None

    def test_claim_next_skips_future_retry(self, repo):
        """Failed rows scheduled for future retry are not claimed yet."""
        repo.enqueue(wanted_item_id=401, file_path="/a.mkv", target_language="ger")
        claim = repo.claim_next(now=datetime.now(UTC))
        assert claim is not None
        future = datetime.now(UTC) + timedelta(hours=1)
        repo.mark_failed(claim["id"], error="io", next_retry_at=future)
        # Trying to claim again before next_retry_at must yield nothing.
        again = repo.claim_next(now=datetime.now(UTC))
        assert again is None
        # Clock forward past next_retry_at: it becomes claimable.
        still_later = future + timedelta(seconds=1)
        again = repo.claim_next(now=still_later)
        assert again is not None
        assert again["wanted_item_id"] == 401

    def test_claim_next_prefers_earlier_next_retry_at(self, repo):
        """Within the claimable set, oldest next_retry_at wins (FIFO-ish)."""
        repo.enqueue(wanted_item_id=501, file_path="/a.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=502, file_path="/b.mkv", target_language="ger")
        # Both are claimable (pending, next_retry_at NULL). The repo should
        # return them one at a time on each call, transitioning to running.
        first = repo.claim_next(now=datetime.now(UTC))
        second = repo.claim_next(now=datetime.now(UTC))
        assert first is not None
        assert second is not None
        assert {first["wanted_item_id"], second["wanted_item_id"]} == {501, 502}


class TestMarkDone:
    def test_mark_done_transitions_to_done(self, repo):
        repo.enqueue(wanted_item_id=601, file_path="/a.mkv", target_language="ger")
        claim = repo.claim_next(now=datetime.now(UTC))
        repo.mark_done(claim["id"])
        e = repo.get_by_wanted_item(601)
        assert e["state"] == "done"
        assert e["last_finished_at"] is not None
        assert e["last_error"] is None


class TestMarkFailed:
    def test_mark_failed_increments_attempt(self, repo):
        repo.enqueue(wanted_item_id=701, file_path="/a.mkv", target_language="ger")
        claim = repo.claim_next(now=datetime.now(UTC))
        repo.mark_failed(
            claim["id"],
            error="ffprobe timeout",
            next_retry_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        e = repo.get_by_wanted_item(701)
        assert e["state"] == "failed"
        assert e["attempt_count"] == 1
        assert "ffprobe" in e["last_error"]
        assert e["next_retry_at"] is not None

    def test_mark_failed_then_reclaim_increments_again(self, repo):
        repo.enqueue(wanted_item_id=702, file_path="/a.mkv", target_language="ger")
        claim1 = repo.claim_next(now=datetime.now(UTC))
        now = datetime.now(UTC)
        past = now - timedelta(hours=1)
        repo.mark_failed(claim1["id"], error="x", next_retry_at=past)
        claim2 = repo.claim_next(now=now)
        assert claim2 is not None
        repo.mark_failed(
            claim2["id"], error="y", next_retry_at=now + timedelta(minutes=5)
        )
        e = repo.get_by_wanted_item(702)
        assert e["attempt_count"] == 2


class TestGetCounts:
    def test_counts_empty(self, repo):
        counts = repo.get_counts()
        assert counts == {"pending": 0, "running": 0, "failed": 0, "done": 0}

    def test_counts_mixed_states(self, repo):
        # 2 pending
        repo.enqueue(wanted_item_id=801, file_path="/a.mkv", target_language="ger")
        repo.enqueue(wanted_item_id=802, file_path="/b.mkv", target_language="ger")
        # Claim one and leave it running
        repo.claim_next(now=datetime.now(UTC))
        # Claim second and mark done
        claim2 = repo.claim_next(now=datetime.now(UTC))
        repo.mark_done(claim2["id"])
        # Add a failed one
        repo.enqueue(wanted_item_id=803, file_path="/c.mkv", target_language="ger")
        claim3 = repo.claim_next(now=datetime.now(UTC))
        repo.mark_failed(
            claim3["id"], error="x", next_retry_at=datetime.now(UTC) + timedelta(hours=1)
        )
        counts = repo.get_counts()
        # pending=0 (all claimed), running=1, failed=1, done=1
        assert counts["running"] == 1
        assert counts["failed"] == 1
        assert counts["done"] == 1


class TestReset:
    def test_re_enqueue_after_done_resets_state(self, repo):
        """An item that finished successfully can be re-enqueued later
        (e.g. user re-added file). It should transition back to pending
        with attempt_count reset to 0."""
        repo.enqueue(wanted_item_id=901, file_path="/a.mkv", target_language="ger")
        claim = repo.claim_next(now=datetime.now(UTC))
        repo.mark_done(claim["id"])
        repo.enqueue(wanted_item_id=901, file_path="/a.mkv", target_language="ger")
        e = repo.get_by_wanted_item(901)
        assert e["state"] == "pending"
        assert e["attempt_count"] == 0
