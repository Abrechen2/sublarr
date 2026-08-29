r"""Song and karaoke styles must not be handed to a translator as dialogue.

`SIGNS_PATTERNS` anchored `^op$` and `^ed$`, which misses the naming fansubs
actually use — `OP Romaji`, `OP English`, `ED Romaji`, `ED English`. Measured on
a real library on 2026-08-24: 92 of 403 "dialogue" lines in one episode were
song lines, and the German output shipped with the *romaji* — transliterated
Japanese — machine-translated (`OP Romaji ... Wind, oh Wind`).

A style only escapes the sign/song bucket today if its karaoke lines happen to
carry `\pos`/`\move` tags, which is a property of the typesetter, not a rule.
"""

import pysubs2

from ass_utils import classify_styles


def _subs(*styles: str) -> pysubs2.SSAFile:
    subs = pysubs2.SSAFile()
    for name in styles:
        subs.styles[name] = pysubs2.SSAStyle()
    subs.events = [pysubs2.SSAEvent(text=f"line for {name}", style=name) for name in styles]
    return subs


def test_prefixed_opening_and_ending_styles_are_songs():
    dialog, signs = classify_styles(_subs("OP Romaji", "OP English", "ED Romaji", "ED English"))

    assert dialog == set()
    assert signs == {"OP Romaji", "OP English", "ED Romaji", "ED English"}


def test_bare_op_and_ed_stay_songs():
    _dialog, signs = classify_styles(_subs("OP", "ED"))

    assert signs == {"OP", "ED"}


def test_romaji_is_never_dialogue_whatever_it_is_called():
    """Romaji is transliterated Japanese — never something to translate."""
    _dialog, signs = classify_styles(_subs("Insert Song Romaji", "romaji", "Karaoke-Romaji"))

    assert signs == {"Insert Song Romaji", "romaji", "Karaoke-Romaji"}


def test_ordinary_dialogue_styles_are_untouched():
    dialog, signs = classify_styles(_subs("Default", "Main", "Italics", "Top Default", "Alt."))

    assert signs == set()
    assert "Default" in dialog and "Top Default" in dialog


def test_words_merely_containing_ed_are_not_songs():
    """A guard against a sloppy substring match — 'Edited', 'Red', 'Shed'."""
    dialog, signs = classify_styles(_subs("Edited", "Red Text", "Shed"))

    assert signs == set()
    assert dialog == {"Edited", "Red Text", "Shed"}


def test_a_character_named_ed_keeps_their_dialogue():
    """The reason this pattern must not be a bare word match.

    ``classify_styles`` also feeds ``cleanup_signs`` and
    ``purge_signs_after_extract``, which DELETE what they consider signs. A
    fansub style named after a character — 'Ed', 'Ed Smith', 'Op Officer' —
    landing in the sign bucket would strand that character's lines
    untranslated and expose them to a purge.
    """
    dialog, signs = classify_styles(_subs("Ed Smith", "Ed (thoughts)", "Op Officer"))

    assert signs == set()
    assert dialog == {"Ed Smith", "Ed (thoughts)", "Op Officer"}
