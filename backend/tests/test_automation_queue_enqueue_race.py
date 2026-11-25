"""A lost enqueue race must not poison the session (#81).

The webhook pipeline and the wanted search can finish the same item at the
same moment and both queue its auto-sync. Both see "no row", the slower INSERT
hits the unique key, and before the fix the failed flush left the scoped
session unusable: deleting the wanted item, restoring its status and sending
the notification all failed afterwards in the same request.
"""

from __future__ import annotations

from datetime import UTC, datetime

from db.models.core import SubtitleAutomationQueueEntry


def _repo():
    from db.repositories.subtitle_automation_queue import (
        SubtitleAutomationQueueRepository,
    )

    return SubtitleAutomationQueueRepository()


_KEY = {
    "wanted_item_id": 194989,
    "file_path": "/media/show/S01E09.de.ass",
    "target_language": "de",
    "task_type": SubtitleAutomationQueueEntry.TASK_AUTO_SYNC,
}


def _lose_the_race(repo, monkeypatch):
    """The existence check misses a row another caller has just committed."""
    winner = _repo().enqueue(video_path="/media/show/S01E09.mkv", **_KEY)
    real_find = repo._find_existing
    calls = {"n": 0}

    def find_misses_once(*args, **kwargs):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(*args, **kwargs)

    monkeypatch.setattr(repo, "_find_existing", find_misses_once)
    return winner


class TestEnqueueRace:
    def test_lost_race_returns_the_winner(self, app_ctx, monkeypatch):
        repo = _repo()
        winner = _lose_the_race(repo, monkeypatch)

        assert repo.enqueue(video_path="/media/show/S01E09.mkv", **_KEY) == winner

    def test_session_stays_usable_after_a_lost_race(self, app_ctx, monkeypatch):
        repo = _repo()
        _lose_the_race(repo, monkeypatch)
        repo.enqueue(video_path="/media/show/S01E09.mkv", **_KEY)

        # The next statement in the same session must not raise
        # "This Session's transaction has been rolled back".
        assert len(repo.list_for_item(_KEY["wanted_item_id"])) == 1

    def test_lost_race_keeps_earlier_work_of_a_batch(self, app_ctx, monkeypatch):
        repo = _repo()
        _lose_the_race(repo, monkeypatch)

        with repo.batch():
            repo.session.add(
                SubtitleAutomationQueueEntry(
                    wanted_item_id=7,
                    task_type=SubtitleAutomationQueueEntry.TASK_EMBEDDED_EXTRACT,
                    file_path="/media/other.mkv",
                    target_language="de",
                    state="pending",
                    attempt_count=0,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            repo.enqueue(video_path="/media/show/S01E09.mkv", **_KEY)

        assert len(repo.list_for_item(7)) == 1
