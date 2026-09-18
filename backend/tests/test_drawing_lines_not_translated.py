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

    indices, texts, _tags, _lengths = _collect_translatable_events(subs, {"Default"})

    assert texts == ["Guten Morgen."]
    assert indices == [0]
