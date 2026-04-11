"""Verify that get_wanted_items uses file_path as secondary sort key."""

from datetime import UTC, datetime

import pytest

from db.models.core import WantedItem
from db.repositories.wanted import WantedRepository
from extensions import db


def make_item(file_path: str, target_language: str) -> WantedItem:
    """Create a test wanted item with the given file_path and language."""
    now = datetime(2026, 1, 1, tzinfo=UTC)
    item = WantedItem(
        item_type="episode",
        file_path=file_path,
        title="Test",
        season_episode="S01E01",
        existing_sub="",
        missing_languages="[]",
        embedded_languages="[]",
        target_language=target_language,
        subtitle_type="full",
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    db.session.add(item)
    db.session.commit()
    return item


def test_secondary_sort_by_file_path(app_ctx):
    """Items with same added_at must be returned ordered by file_path."""
    make_item("/media/Z_Last.mkv", "de")
    make_item("/media/A_First.mkv", "de")
    make_item("/media/M_Middle.mkv", "de")

    repo = WantedRepository()
    result = repo.get_wanted_items(sort_by="added_at", sort_dir="asc")
    paths = [item["file_path"] for item in result["data"]]

    assert paths == ["/media/A_First.mkv", "/media/M_Middle.mkv", "/media/Z_Last.mkv"]


def test_pairs_adjacent_after_secondary_sort(app_ctx):
    """DE+EN pairs for the same file_path are always adjacent in results."""
    make_item("/media/Ep1.mkv", "en")
    make_item("/media/Ep2.mkv", "de")
    make_item("/media/Ep1.mkv", "de")
    make_item("/media/Ep2.mkv", "en")

    repo = WantedRepository()
    result = repo.get_wanted_items(sort_by="added_at", sort_dir="asc")
    paths = [item["file_path"] for item in result["data"]]

    # Ep1 pair must be adjacent, Ep2 pair must be adjacent
    assert paths[0] == paths[1]  # first two are same file
    assert paths[2] == paths[3]  # second two are same file
    assert paths[0] != paths[2]  # different files
