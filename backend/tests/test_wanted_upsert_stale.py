"""Regression: upsert_wanted_item recovers from a concurrent-delete StaleDataError.

When a parallel scan / standalone cleanup / _prune_replaced_siblings deletes the
row we matched between our SELECT and flush, the ORM UPDATE matches 0 rows and
SQLAlchemy raises StaleDataError. Previously that propagated and poisoned the
shared session, cascading to every later item in the same scan. upsert now rolls
back and retries once (re-inserting a fresh row), so a single race no longer
breaks the whole scan.
"""

from __future__ import annotations

from unittest.mock import patch

from sqlalchemy.orm.exc import StaleDataError

from db.wanted import _get_repo, get_wanted_item, upsert_wanted_item


def test_upsert_recovers_from_stale_data_error_on_update(app_ctx, tmp_path):
    mkv = tmp_path / "ep.mkv"
    mkv.touch()

    # Seed an existing row so the next upsert takes the UPDATE path.
    first_id, was_updated = upsert_wanted_item(
        item_type="episode", file_path=str(mkv), target_language="de"
    )
    assert was_updated is False

    repo = _get_repo()
    real_commit = repo._commit
    state = {"n": 0}

    def flaky_commit():
        state["n"] += 1
        if state["n"] == 1:
            # Simulate the concurrent-delete race on the UPDATE flush.
            raise StaleDataError(
                "UPDATE statement on table 'wanted_items' expected to update "
                "1 row(s); 0 were matched."
            )
        return real_commit()

    with patch.object(repo, "_commit", side_effect=flaky_commit):
        row_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=str(mkv),
            target_language="de",
            title="recovered",
        )

    # No exception propagated, and the retry persisted the update.
    item = get_wanted_item(row_id)
    assert item is not None
    assert item["title"] == "recovered"
