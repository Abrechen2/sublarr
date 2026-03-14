"""Tests for the new term_type, confidence, approved columns on glossary_entries."""

import pytest

from db.translation import add_glossary_entry, get_glossary_entry, update_glossary_entry


def test_add_glossary_entry_with_metadata(app_ctx):
    """add_glossary_entry stores explicit term_type, confidence, and approved values."""
    entry_id = add_glossary_entry(
        series_id=1,
        source_term="Naruto",
        target_term="Naruto",
        notes="main character",
        term_type="character",
        confidence=0.95,
        approved=0,
    )
    assert isinstance(entry_id, int)

    entry = get_glossary_entry(entry_id)
    assert entry is not None
    assert entry["source_term"] == "Naruto"
    assert entry["target_term"] == "Naruto"
    assert entry["term_type"] == "character"
    assert pytest.approx(entry["confidence"], abs=1e-6) == 0.95
    assert entry["approved"] == 0


def test_add_glossary_entry_defaults(app_ctx):
    """add_glossary_entry uses correct defaults: term_type='other', confidence=None, approved=1."""
    entry_id = add_glossary_entry(
        series_id=None,
        source_term="Konoha",
        target_term="Konoha",
    )
    assert isinstance(entry_id, int)

    entry = get_glossary_entry(entry_id)
    assert entry is not None
    assert entry["term_type"] == "other"
    assert entry["confidence"] is None
    assert entry["approved"] == 1


def test_update_glossary_entry_metadata(app_ctx):
    """update_glossary_entry can update term_type, confidence, and approved independently."""
    entry_id = add_glossary_entry(
        series_id=2,
        source_term="Hokage",
        target_term="Hokage",
        term_type="other",
        confidence=None,
        approved=1,
    )

    # Update term_type and approved only — confidence should remain None
    result = update_glossary_entry(entry_id, term_type="place", approved=0)
    assert result is True

    entry = get_glossary_entry(entry_id)
    assert entry["term_type"] == "place"
    assert entry["approved"] == 0
    assert entry["confidence"] is None  # unchanged

    # Now set confidence explicitly
    result = update_glossary_entry(entry_id, confidence=0.7)
    assert result is True

    entry = get_glossary_entry(entry_id)
    assert pytest.approx(entry["confidence"], abs=1e-6) == 0.7

    # Clear confidence back to None via explicit None
    result = update_glossary_entry(entry_id, confidence=None)
    assert result is True

    entry = get_glossary_entry(entry_id)
    assert entry["confidence"] is None


def test_update_glossary_entry_no_fields(app_ctx):
    """update_glossary_entry returns False when no fields are provided."""
    entry_id = add_glossary_entry(
        series_id=3,
        source_term="Sensei",
        target_term="Lehrer",
        term_type="other",
    )

    result = update_glossary_entry(entry_id)
    assert result is False


def test_add_glossary_entry_place_type(app_ctx):
    """add_glossary_entry stores 'place' as term_type correctly."""
    entry_id = add_glossary_entry(
        series_id=4,
        source_term="Hidden Leaf Village",
        target_term="Verborgenes Blatt-Dorf",
        term_type="place",
        confidence=0.88,
        approved=1,
    )

    entry = get_glossary_entry(entry_id)
    assert entry["term_type"] == "place"
    assert pytest.approx(entry["confidence"], abs=1e-6) == 0.88
    assert entry["approved"] == 1
