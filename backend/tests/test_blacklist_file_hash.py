"""Tests for Plan B3 granular blacklist (file_hash dimension)."""

import pytest

from db.models.core import BlacklistEntry


def test_blacklist_entry_has_file_hash_column():
    """The BlacklistEntry ORM model exposes a file_hash attribute."""
    assert hasattr(BlacklistEntry, "file_hash"), (
        "Expected BlacklistEntry.file_hash after B3 migration"
    )


def test_blacklist_entry_file_hash_default_is_none():
    """Creating a BlacklistEntry without file_hash leaves it as None."""
    from datetime import datetime, timezone

    entry = BlacklistEntry(
        provider_name="opensubtitles",
        subtitle_id="12345",
        language="en",
        added_at=datetime.now(timezone.utc),
    )
    assert entry.file_hash is None
