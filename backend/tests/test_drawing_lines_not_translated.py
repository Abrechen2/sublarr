"""ASS drawing commands are vector data, not language — never translate them.

Prod, 2026-09-17: ``subtitle_automation`` spent 22:57–23:09 translating and
quality-retrying seven consecutive events whose text read
``m 78.43 15.3 b 77.04 15.3 75.83 16.15 …`` — the coordinates of a ``{\\p1}``
drawing. Each scored 1, was retranslated, scored 1 again. Over 72 hours
59 of 384 quality retries (15 %) were spent this way.

Two things have to line up for a drawing to reach the model:

- ``extract_tags`` splits out every ``{…}`` override tag, including the
  ``{\\p1}`` that is the only thing marking the rest as a drawing, and hands
  back the bare coordinates as "clean text";
- the style filter only separates dialog styles from signs/songs styles, so a
  drawing authored under a dialog style passes it.

So the guard has to look at the event text itself, before the tags are gone.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "text, expected",
    [
        # A closed drawing span contributes no text at all.
        (r"{\p1}m 78.43 15.3 b 77.04 15.3 75.83 16.15{\p0}", ""),
        # The real prod shape: the opener is never closed, the line just ends.
        (r"{\p4}m 0 0 l 100 0 100 100 0 100", ""),
        # A drawing that carries no override tag beyond the opener.
        (r"{\p1}m 1 2 l 3 4", ""),
        # Ordinary dialogue is untouched.
        ("Guten Morgen.", "Guten Morgen."),
        # Ordinary dialogue with positioning/styling tags stays translatable.
        (r"{\an8}{\i1}Guten Morgen.{\i0}", "Guten Morgen."),
        # \p0 is not a drawing opener — it turns drawing mode off.
        (r"{\p0}Guten Morgen.", "Guten Morgen."),
        # Mixed: real text after the span closes must survive.
        (r"{\p1}m 1 2{\p0}Guten Morgen.", "Guten Morgen."),
        # Drawing mode re-opened after real text still yields that text.
        (r"Hallo{\p1}m 1 2", "Hallo"),
        # Empty stays empty.
        ("", ""),
    ],
)
def test_text_outside_drawing(text, expected):
    from ass_utils import text_outside_drawing

    assert text_outside_drawing(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # A space before the number: libass skips whitespace, so this ends
        # drawing mode and the dialogue after it is visible.
        (r"{\p1}m 0 0 l 10 10{\p 0}Good morning.", "Good morning."),
        # A negative argument is <= 0, so drawing is off.
        (r"{\p1}m 0 0 l 10 10{\p-1}Good morning.", "Good morning."),
        # No argument at all parses as 0 — also off.
        (r"{\p1}m 0 0 l 10 10{\p}Good morning.", "Good morning."),
        # Leading zero still names mode 1: this IS a drawing.
        (r"{\p01}m 0 0 l 10 10", ""),
        # Uppercase is not the drawing tag at all; libass ignores it and the
        # line renders as ordinary dialogue.
        (r"{\P1}Good morning.", "Good morning."),
        # \pbo is the baseline-offset tag and must not be read as \p.
        (r"{\pbo3}Good morning.", "Good morning."),
        (r"{\p1}m 0 0{\pbo3}l 10 10", ""),
        # Mode numbers above 9 exist; two digits must not be truncated.
        (r"{\p12}m 0 0 l 10 10", ""),
    ],
)
def test_text_outside_drawing_follows_libass(text, expected):
    """The predicate has to agree with the renderer, not with a guess.

    Sandbox VM, 1.14.4-rc.9: seven pixel comparisons against the ffmpeg/libass
    shipped in the release image showed ``\\P1`` rendering identically to plain
    dialogue, ``\\p01`` identically to ``\\p1``, and ``{\\p 0}`` / ``{\\p-1}`` /
    ``{\\p}`` identically to ``{\\p0}``. The first regex pair
    (``\\p[1-9]`` / ``\\p0``, both IGNORECASE) disagreed with all of those —
    wrongly skipping whole events with visible dialogue in three of them, and
    wrongly translating coordinates in the fourth.
    """
    from ass_utils import text_outside_drawing

    assert text_outside_drawing(text) == expected


@pytest.mark.parametrize(
    "text, expected_body",
    [
        # Drawing first, dialogue after — the VM's reproduction.
        (r"{\p1}m 0 0 l 10 10{\p0}Good morning.", "Good morning."),
        # Dialogue first, drawing after.
        (r"Good morning.{\p1}m 0 0 l 10 10", "Good morning."),
        # Inline styling around the dialogue rides along in prefix/suffix; the
        # body is the sentence itself, which is all the model needs.
        (r"{\p1}m 0 0{\p0}{\i1}Good morning.{\i0}", "Good morning."),
        # Styling *inside* the sentence splits it into three runs. The body has
        # to span all of them, tags included, or an ordinary sign caption with
        # one italic word would be excluded from translation entirely.
        (
            r"{\p1}m 0 0{\p0}Good {\i1}morning{\i0} to you.",
            r"Good {\i1}morning{\i0} to you.",
        ),
    ],
)
def test_mixed_events_offer_only_their_dialogue(text, expected_body):
    """Only the dialogue half may reach the model — never the coordinates.

    Sandbox VM, 1.14.4-rc.9 (F3): the helper was used as a yes/no filter and
    ``extract_tags`` then got the *whole* original, so the coordinates went to
    the model anyway. With them in front, restoring the tags proportionally
    shifted them into the German sentence and the sanitizer then removed part
    of it: ``{\\p1}m 0 0 l 10 10{\\p0}Good morning.`` was saved as
    ``" Morgen."``. Present in rc.8 too, and the drawing filter did not close
    it.
    """
    from ass_utils import split_around_drawings

    split = split_around_drawings(text)
    assert split is not None, "a mixed event must be splittable"
    prefix, body, suffix = split
    assert body == expected_body
    assert prefix + body + suffix == text, "the split must lose nothing"


def test_drawing_between_two_pieces_of_dialogue_is_not_split():
    """Two text halves around a drawing cannot be put back together.

    One translated string cannot be mapped onto two separate runs, so the
    event is left alone rather than reassembled by guesswork.
    """
    from ass_utils import split_around_drawings

    assert split_around_drawings(r"Good{\p1}m 0 0{\p0}morning.") is None


def test_mixed_event_saves_the_whole_translated_sentence(tmp_path, app_ctx, monkeypatch):
    """End to end: the sentence arrives whole, not cut short.

    The saved file no longer carries the drawing — ``subtitle_sanitizer``
    removes complete ``{\\pN}…{\\p0}`` spans on purpose, because a drawing-mode
    overlay can cover the screen. That is not what was broken. What was broken
    is that the coordinates travelled *through* the model as part of the text,
    so ``restore_tags`` placed ``{\\p0}`` proportionally inside the German
    sentence and the sanitizer then removed everything up to it, saving
    ``" Morgen."`` (sandbox VM, rc.9). The sentence must survive whole.
    """
    pytest.importorskip("pysubs2")
    import pysubs2

    import translator.core as _core
    from translator.ass_flow import _translate_external_ass

    src = tmp_path / "source.ass"
    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    subs.events.append(
        pysubs2.SSAEvent(
            start=0, end=1000, style="Default", text=r"{\p1}m 0 0 l 10 10{\p0}Good morning."
        )
    )
    subs.save(str(src))

    seen = {}

    class _Result:
        backend_name = "stub"
        success = True

    def _fake_translate(lines, **kwargs):
        seen["lines"] = list(lines)
        return ["Guten Morgen."], _Result()

    monkeypatch.setattr(_core._pkg(), "_translate_with_manager", _fake_translate)
    monkeypatch.setattr(_core._pkg(), "_get_quality_config", lambda: (False, 35, 1))

    result = _translate_external_ass(
        str(tmp_path / "video.mkv"), str(src), target_language="de", source_language="en"
    )

    assert seen["lines"] == ["Good morning."], "coordinates reached the model"
    out = pysubs2.load(result["output_path"])
    assert out.events[0].text == "Guten Morgen.", (
        "the sanitizer took part of the sentence with the drawing"
    )


def test_drawing_events_are_not_offered_for_translation(tmp_path, app_ctx):
    """End to end through the flow's own selection, not just the helper.

    A file whose dialog style holds one real line and one unclosed drawing must
    offer exactly the real line to the translator.
    """
    pytest.importorskip("pysubs2")
    import pysubs2

    from translator.ass_flow import _collect_translatable_events

    subs = pysubs2.SSAFile()
    subs.styles["Default"] = pysubs2.SSAStyle()
    subs.events.append(pysubs2.SSAEvent(start=0, end=1000, style="Default", text="Guten Morgen."))
    subs.events.append(
        pysubs2.SSAEvent(
            start=1000,
            end=2000,
            style="Default",
            text=r"{\p4}m 78.43 15.3 b 77.04 15.3 75.83 16.15 75.33 17.41 l 14.03 4",
        )
    )

    indices, texts, *_rest = _collect_translatable_events(subs, {"Default"})

    assert texts == ["Guten Morgen."]
    assert indices == [0]
