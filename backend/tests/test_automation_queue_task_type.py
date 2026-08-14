"""One wanted item can need both an extraction and a translation.

`wanted_item_id` was UNIQUE, which encoded the assumption that the queue only
ever holds one kind of work. Moving sidecar translation onto this queue breaks
that assumption: an item with an embedded track queued for extraction can also
have a source sidecar queued for translation. The uniqueness that still matters
is per (item, task_type) — enqueueing the same work twice must stay a no-op.
"""

from __future__ import annotations


def _repo():
    from db.repositories.subtitle_automation_queue import (
        SubtitleAutomationQueueRepository,
    )

    return SubtitleAutomationQueueRepository()


class TestTaskTypeUniqueness:
    def test_same_item_can_hold_both_task_types(self, app_ctx):
        repo = _repo()
        repo.enqueue(
            wanted_item_id=1,
            file_path="/media/a.mkv",
            target_language="de",
            task_type="embedded_extract",
        )
        repo.enqueue(
            wanted_item_id=1,
            file_path="/media/a.eng.ass",
            target_language="de",
            task_type="sidecar_translate",
            source_language="en",
        )

        rows = repo.list_for_item(1)
        assert {r["task_type"] for r in rows} == {"embedded_extract", "sidecar_translate"}

    def test_same_item_and_type_still_deduplicates(self, app_ctx):
        repo = _repo()
        first = repo.enqueue(
            wanted_item_id=2,
            file_path="/media/b.mkv",
            target_language="de",
            task_type="embedded_extract",
        )
        second = repo.enqueue(
            wanted_item_id=2,
            file_path="/media/b.mkv",
            target_language="de",
            task_type="embedded_extract",
        )

        assert first == second
        assert len(repo.list_for_item(2)) == 1

    def test_existing_rows_default_to_extraction(self, app_ctx):
        """The migration backfills; a row written without a type is extraction,
        which is the only thing the queue held before."""
        repo = _repo()
        repo.enqueue(wanted_item_id=3, file_path="/media/c.mkv", target_language="de")
        rows = repo.list_for_item(3)
        assert [r["task_type"] for r in rows] == ["embedded_extract"]
        assert rows[0]["source_language"] is None

    def test_source_language_round_trips(self, app_ctx):
        repo = _repo()
        repo.enqueue(
            wanted_item_id=4,
            file_path="/media/d.eng.ass",
            target_language="de",
            task_type="sidecar_translate",
            source_language="en",
        )
        assert repo.list_for_item(4)[0]["source_language"] == "en"


class TestReadsSurviveTwoRowsPerItem:
    def test_get_by_wanted_item_does_not_raise_on_two_rows(self, app_ctx):
        """It used ``one_or_none()``, which raises MultipleResultsFound the
        moment an item legitimately holds two kinds of work."""
        repo = _repo()
        repo.enqueue(
            wanted_item_id=5,
            file_path="/media/e.mkv",
            target_language="de",
            task_type="embedded_extract",
        )
        repo.enqueue(
            wanted_item_id=5,
            file_path="/media/e.eng.ass",
            target_language="de",
            task_type="sidecar_translate",
            source_language="en",
        )

        assert repo.get_by_wanted_item(5) is not None
        assert repo.get_by_wanted_item(5, task_type="sidecar_translate")["file_path"] == (
            "/media/e.eng.ass"
        )

    def test_claimed_row_carries_its_task_type(self, app_ctx):
        """The drain worker branches on it, so it has to survive the claim."""
        repo = _repo()
        repo.enqueue(
            wanted_item_id=6,
            file_path="/media/f.eng.ass",
            target_language="de",
            task_type="sidecar_translate",
            source_language="en",
        )
        claimed = repo.claim_next()
        assert claimed is not None
        assert claimed["task_type"] == "sidecar_translate"
        assert claimed["source_language"] == "en"
