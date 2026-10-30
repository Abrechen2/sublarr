"""HI markers in German (and other non-English) subtitles are removed too.

Prod 2026-10-30, Slime S02E20: a German translation of an English CC track
kept 141 markers such as "[HERMES stöhnt]" and "[schnappt nach Luft]". The
patterns only knew all-caps or all-lowercase ASCII inside the brackets, and
German capitalises nouns and writes umlauts.
"""

import pytest

from hi_remover import remove_hi_markers


@pytest.mark.parametrize(
    "text",
    [
        "[HERMES stöhnt]",
        "[schnappt nach Luft]",
        "[SUPHIA atmet schwer]",
        "[Gelächter]",
        "[Tür knallt zu]",
        "(stöhnt)",
        "(Seufzt)",
        "(SEUFZT)",
        "(rit doucement)",
    ],
)
def test_a_cue_that_is_only_a_marker_goes(text):
    assert remove_hi_markers(text) == ""


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("[lacht] Okay.", "Okay."),
        ("Nein! [keucht] Sir Gabiru...", "Nein! Sir Gabiru..."),
        ("GABIRU: Los!", "Los!"),
        ("SÖREN: Hallo.", "Hallo."),
        ("(flüstert) Komm her.", "Komm her."),
    ],
)
def test_a_marker_inside_dialogue_goes_and_the_dialogue_stays(text, kept):
    assert remove_hi_markers(text) == kept


@pytest.mark.parametrize(
    "text",
    [
        "Nein, Sir Gabiru...",
        "Er sagte (Gott sei Dank) nichts.",
        "Um 10:30 Uhr.",
        "Rimuru: der Name gefällt mir.",
    ],
)
def test_dialogue_without_markers_is_left_alone(text):
    assert remove_hi_markers(text) == text
