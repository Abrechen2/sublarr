"""A failed commit must not leave the shared session unusable (#81 sweep).

Many callers treat a repository write as best effort and swallow its error.
Before the fix the failed flush left the request-scoped session in a state
where every later statement raised "This Session's transaction has been
rolled back due to a previous exception during flush".
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.models.core import SubtitleAutomationQueueEntry


def _broken_row():
    # created_at is NOT NULL, so the flush inside commit fails.
    return SubtitleAutomationQueueEntry(
        wanted_item_id=1,
        task_type=SubtitleAutomationQueueEntry.TASK_AUTO_SYNC,
        file_path="/media/x.de.ass",
        target_language="de",
        state="pending",
        attempt_count=0,
    )


def test_session_is_usable_after_a_failed_commit(app_ctx):
    from db.repositories.base import BaseRepository

    repo = BaseRepository()
    repo.session.add(_broken_row())
    with pytest.raises(IntegrityError):
        repo._commit()

    assert repo.session.execute(text("SELECT 1")).scalar() == 1
