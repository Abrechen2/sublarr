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


def test_add_entry_with_file_hash(app_ctx):
    """add_blacklist_entry() accepts a file_hash kwarg and persists it."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="opensubtitles",
        subtitle_id="sub_123",
        file_hash="a" * 64,
        reason="test",
    )
    assert entry_id > 0

    # Existence check by hash works
    assert repo.is_blacklisted_by_hash("opensubtitles", "a" * 64) is True

    # Wrong provider returns False
    assert repo.is_blacklisted_by_hash("gestdown", "a" * 64) is False

    # Wrong hash returns False
    assert repo.is_blacklisted_by_hash("opensubtitles", "b" * 64) is False

    # Cleanup to keep the test DB clean
    repo.remove_blacklist_entry(entry_id)


def test_add_entry_without_file_hash_still_works(app_ctx):
    """Legacy add_blacklist_entry() call (no file_hash) continues to work."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="podnapisi",
        subtitle_id="sub_456",
        reason="legacy path",
    )
    assert entry_id > 0
    # Traditional check still works
    assert repo.is_blacklisted("podnapisi", "sub_456") is True
    repo.remove_blacklist_entry(entry_id)


def test_is_blacklisted_accepts_hash_alternative(app_ctx):
    """is_blacklisted() can be called with file_hash= instead of subtitle_id."""
    from db.repositories.blacklist import BlacklistRepository

    repo = BlacklistRepository()
    entry_id = repo.add_blacklist_entry(
        provider_name="opensubtitles",
        subtitle_id="sub_999",
        file_hash="c" * 64,
    )
    # Check by subtitle_id (traditional)
    assert repo.is_blacklisted("opensubtitles", subtitle_id="sub_999") is True
    # Check by file_hash (new)
    assert repo.is_blacklisted("opensubtitles", file_hash="c" * 64) is True
    repo.remove_blacklist_entry(entry_id)


def test_db_blacklist_wrapper_forwards_file_hash():
    """The db.blacklist wrapper module exposes hash-aware functions."""
    import db.blacklist as bl

    # The wrapper must expose the new function
    assert hasattr(bl, "is_blacklisted_by_hash"), (
        "Expected db.blacklist.is_blacklisted_by_hash to be exposed"
    )
    # And the existing add function should accept file_hash kwarg
    import inspect

    sig = inspect.signature(bl.add_blacklist_entry)
    assert "file_hash" in sig.parameters
