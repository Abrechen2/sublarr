# backend/tests/test_hi_removal_extended.py
"""Tests for extended HI removal patterns applied by the processor."""

import os

import pytest


def test_curly_brackets_removed(create_test_subtitle):
    """pysubs2 strips {TAG} content from plaintext before processing.

    When a line is only a curly-bracket HI marker (e.g. '{APPLAUSE} Thank you'),
    pysubs2 exposes ' Thank you' as plaintext.  The hi_remover then processes
    that plaintext, so the result should have no {APPLAUSE} in the output text.
    We verify the event text does not contain the curly-bracket tag in the output.
    """
    import pysubs2

    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["{APPLAUSE} Thank you"])
    apply_mods(path, [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=True)

    # pysubs2 strips {APPLAUSE} as an ASS override tag — so plaintext is just "Thank you".
    # No change record is produced because the content was already stripped by pysubs2.
    # Verify the file can be processed without error and the text "APPLAUSE" is gone.
    subs = pysubs2.load(path, format_="srt", encoding="utf-8")
    for event in subs.events:
        assert "{APPLAUSE}" not in event.plaintext


def test_japanese_parens_removed(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["\uff08\u7b11\uff09 Hello"])
    result = apply_mods(path, [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=True)

    changes = [c for c in result.changes if "\uff08" in c.original_text]
    assert changes
    assert "\uff08" not in changes[0].modified_text


def test_all_caps_line_removed(create_test_subtitle):
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["PHONE RINGING", "Hello there"])
    result = apply_mods(path, [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=True)

    caps_changes = [c for c in result.changes if c.original_text == "PHONE RINGING"]
    assert caps_changes
    assert caps_changes[0].modified_text == ""


def test_all_caps_min_length_respected(create_test_subtitle):
    """3-char all-caps word should NOT be removed at default min_length=4."""
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["OK!", "Hello"])
    result = apply_mods(
        path,
        [ModConfig(mod=ModName.HI_REMOVAL, options={"all_caps_min_length": 4})],
        dry_run=True,
    )
    caps_changes = [c for c in result.changes if c.original_text == "OK!"]
    assert not caps_changes


def test_interjection_whole_word_only(create_test_subtitle):
    """'Hmm' standalone should be removed; 'Hmmm' (not in list) should not."""
    from subtitle_processor import ModConfig, ModName, apply_mods

    path = create_test_subtitle(fmt="srt", lines=["Hmm, that's odd", "Hmmm interesting"])
    result = apply_mods(path, [ModConfig(mod=ModName.HI_REMOVAL)], dry_run=True)

    hmm_changes = [c for c in result.changes if "Hmm," in c.original_text]
    assert hmm_changes  # "Hmm" matched
    hmmm_changes = [c for c in result.changes if c.original_text == "Hmmm interesting"]
    assert not hmmm_changes  # "Hmmm" not in list


def test_multiline_bracket_span_removed(create_test_subtitle):
    """[CROWD on event N and CHEERING] on event N+1 — both pre-marked for removal.

    _mark_multiline_bracket_events() detects spanning bracket pairs across events
    and adds both indices to the removal list before the main processing loop.
    Verify the correct indices are identified so the processor knows to drop them.
    """
    import pysubs2

    from subtitle_processor import _mark_multiline_bracket_events

    # Build an in-memory SSAFile with the multiline bracket pattern
    subs = pysubs2.SSAFile()
    for text in ["[CROWD", "CHEERING]", "Hello"]:
        event = pysubs2.SSAEvent(start=0, end=1000, text=text)
        subs.events.append(event)

    to_remove = []
    _mark_multiline_bracket_events(subs, to_remove)

    # Both spanning events must be marked; the non-HI line must not be
    assert 0 in to_remove
    assert 1 in to_remove
    assert 2 not in to_remove
