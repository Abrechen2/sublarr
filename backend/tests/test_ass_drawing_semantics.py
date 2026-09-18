"""One reading of ``\\p`` tags, and it has to be the renderer's.

Sandbox VM, 1.14.4-rc.10: a differential harness put 47 override forms through
the ffmpeg/libass shipped in our own release image and through the product
helper, in both initial drawing states, and found 16 disagreements. Separately
it showed the security sanitizer using a *different*, older reading — and that
one deletes visible dialogue outright.
"""

from __future__ import annotations

import pytest

#: Spelled with chr() rather than written into the string literals: as literal
#: characters these are invisible, and two of the cases below would look like
#: exact duplicates of each other in any diff.
NBSP = chr(0x00A0)
EM_SPACE = chr(0x2003)
ARABIC_INDIC_ONE = chr(0x0661)
FULLWIDTH_ONE = chr(0xFF11)


@pytest.mark.parametrize(
    "tag_block, before, expected",
    [
        # libass accepts a leading plus; rc.10 allowed only a minus, so the
        # coordinates of a {\p+1} drawing were handed to the model.
        (r"{\p+1}", False, True),
        (r"{\p +1}", False, True),
        # The last \p in one block wins, plus sign included.
        (r"{\p1\p0\p+1}", False, True),
        (r"{\p1\p0}", False, False),
        # A no-break space is not ASCII whitespace, so the argument is not
        # read as a number at all and drawing ends up off — rc.10 accepted it
        # via Python's \s and skipped the visible dialogue that followed.
        (r"{\p" + NBSP + "1}", False, False),
        (r"{\p" + EM_SPACE + "1}", False, False),
        # Python's \d and int() take these for ones; libass does not.
        (r"{\p" + ARABIC_INDIC_ONE + "}", False, False),
        (r"{\p" + FULLWIDTH_ONE + "}", False, False),
        # An unparseable rest reads as 0, which turns drawing off rather than
        # leaving the tag unread.
        (r"{\pfoo}", True, False),
        (r"{\pBO3}", True, False),
        # ... but the real lowercase \pbo and \pos tags are left alone.
        (r"{\pbo3}", True, True),
        (r"{\pbo3}", False, False),
        (r"{\pos(10,20)}", True, True),
        (r"{\pos(10,20)}", False, False),
        # The canonical forms keep working.
        (r"{\p1}", False, True),
        (r"{\p0}", True, False),
        (r"{\p01}", False, True),
        (r"{\p12}", False, True),
        (r"{\p-1}", True, False),
        (r"{\p}", True, False),
        (r"{\an8\i1}", True, True),
        (r"{\an8\i1}", False, False),
        # Whitespace may sit between the backslash and the tag name.
        (r"{\ p1}", False, True),
        (r"{\  p1}", False, True),
        ("{" + chr(92) + chr(9) + "p1}", False, True),
        (r"{\ p0}", True, False),
        (r"{\ P1}", False, False),
        (r"{\ pbo3}", True, True),
        # One opening parenthesis is skipped, a second one is not.
        (r"{\p(1)}", False, True),
        (r"{\p(0)}", True, False),
        (r"{\p(-1)}", True, False),
        (r"{\p(+1)}", False, True),
        (r"{\p( 1 )}", False, True),
        (r"{\p((1))}", False, False),
        (r"{\p(1}", False, True),
        (r"{\p(foo)}", True, False),
        # Digits are read greedily and whatever follows them is ignored.
        (r"{\p1)}", False, True),
        (r"{\p1x}", False, True),
        (r"{\p0x}", True, False),
        (r"{\p1 2}", False, True),
        (r"{\ p(1)}", False, True),
    ],
)
def test_drawing_state_after(tag_block, before, expected):
    from ass_drawing import drawing_state_after

    assert drawing_state_after(tag_block, before) is expected


def test_a_huge_argument_does_not_raise():
    """A 5000-digit argument failed the whole file, ordinary lines included.

    ``int()`` refuses more than 4300 digits in Python 3.12, and the helper let
    that ValueError escape, so one malformed event cost every dialogue in the
    file its translation. Whether a number is positive needs no conversion.
    """
    from ass_drawing import drawing_state_after

    assert drawing_state_after("{\\p" + "9" * 5000 + "}", False) is True
    assert drawing_state_after("{\\p" + "0" * 5000 + "}", True) is False


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Good morning.", True),
        ("", False),
        ("   ", False),
        # Layout escapes are not sentences. A lone \N counted as a stretch of
        # dialogue, so a caption with a leading line break looked like two
        # sentences with a drawing between them and was skipped entirely.
        (r"\N", False),
        (r"\h", False),
        (r"\n", False),
        (r"\N\h", False),
        (r"Good\Nmorning.", True),
    ],
)
def test_holds_language(text, expected):
    from ass_drawing import holds_language

    assert holds_language(text) is expected


class TestSanitizerUsesTheSameReading:
    """The sanitizer deleted visible dialogue because it read \\p differently.

    Both cases below report ``success=true`` from the flow while the saved
    event is empty — confirmed by the VM against the renderer: the expected
    frame shows "Guten Morgen.", the actual frame is black.
    """

    def test_uppercase_p_is_not_an_opener(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\P1}Guten Morgen.{\p0}") == r"{\P1}Guten Morgen.{\p0}"

    def test_a_block_that_turns_drawing_off_again_is_not_an_opener(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p1\p0}Guten Morgen.{\p0}") == r"{\p1\p0}Guten Morgen.{\p0}"

    def test_a_real_drawing_span_is_still_removed(self):
        """The security control itself must not weaken."""
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p1}m 0 0 l 10 10{\p0}Guten Morgen.") == "Guten Morgen."

    def test_an_unclosed_opener_is_removed_to_the_end_of_its_line(self):
        """It was left alone, and it covers the screen.

        Measured in the container against the image's own libass: a
        ``{\\p1}`` that never closes renders 224 000 of 230 400 pixels — 97 %
        of the frame — which is precisely the full-screen overlay this filter
        exists to remove. It was kept only because the spanning regex that
        preceded this walk also kept it.

        Nothing visible is lost by removing it: everything after an unclosed
        opener is geometry to the renderer, so it never drew as text anyway.
        The strip ends at the line, so this cannot become the 2026-09-09
        scan-to-EOF again.
        """
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p1}m 0 0 l 10 10") == ""

    def test_an_unclosed_opener_keeps_the_text_before_it(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"Guten Morgen.{\p1}m 0 0 l 10 10") == "Guten Morgen."

    def test_an_unclosed_opener_keeps_its_blocks_other_overrides(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\an8\p1}m 0 0 l 10 10") == r"{\an8}"

    def test_other_lines_are_untouched_by_an_unclosed_opener(self):
        """Drawing mode resets at every event, so the strip must not run on."""
        from subtitle_sanitizer import strip_drawing_blocks

        text = "\n".join([r"{\p1}m 0 0 l 10 10", "Guten Morgen."])
        assert strip_drawing_blocks(text) == "\n".join(["", "Guten Morgen."])

    def test_a_plus_signed_opener_is_removed_too(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p+1}m 0 0{\p0}Guten Morgen.") == "Guten Morgen."


class TestRemovingADrawingKeepsTheRestOfItsBlock:
    """Only the drawing goes; the overrides sharing its block have to stay.

    A sign is usually authored as one event — ``{\\an8\\pos(...)\\p1}`` geometry
    ``{\\p0}`` caption — so deleting the opening block whole took the caption's
    position with the drawing and dropped it to the default bottom-centre.
    Sandbox VM, 1.14.4-rc.10. Older than this release series.
    """

    def test_positioning_in_the_opening_block_survives(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert (
            strip_drawing_blocks(r"{\an8\p1}m 0 0 l 10 10{\p0}Guten Morgen.")
            == r"{\an8}Guten Morgen."
        )

    def test_overrides_in_the_closing_block_survive(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p1}m 0 0{\p0\i1}Guten Morgen.") == r"{\i1}Guten Morgen."

    def test_a_block_holding_only_the_drawing_tag_leaves_nothing_behind(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert strip_drawing_blocks(r"{\p1}m 0 0 l 10 10{\p0}Guten Morgen.") == "Guten Morgen."

    def test_several_overrides_keep_their_order(self):
        from subtitle_sanitizer import strip_drawing_blocks

        assert (
            strip_drawing_blocks(r"{\an8\p1\pos(10,20)}m 0 0{\p0}Guten Morgen.")
            == r"{\an8\pos(10,20)}Guten Morgen."
        )
