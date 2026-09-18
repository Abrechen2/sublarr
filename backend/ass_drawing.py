"""One reading of ASS drawing-mode tags, shared by everything that needs it.

``\\p<n>`` switches drawing mode: the span after it is vector geometry rather
than language. Three places care — the translator's event selection, the
security sanitizer that removes drawing overlays, and their tests — and until
2026-09-18 two of them disagreed. The sanitizer read ``{\\P1}`` as an opener and
``{\\p1\\p0}`` as an opener too, so it deleted the visible dialogue that followed
and both flows still reported success.

The semantics below are what the ffmpeg/libass shipped in our own image does,
established by pixel comparison rather than by reading the spec:

* the tag is lowercase ``p``, and ``\\pbo`` / ``\\pos`` are different tags that
  must not be read as a ``\\p`` with a missing argument;
* the argument is an optionally signed run of ASCII digits after optional ASCII
  whitespace. A no-break space or a fullwidth digit does not count, and neither
  does anything else Python's ``\\s`` and ``\\d`` would happily accept;
* anything that is not a valid argument reads as 0, so ``\\pfoo`` and ``\\pBO3``
  turn drawing *off* rather than being ignored;
* drawing is on when the value is greater than zero.

The value is never converted to an int: a 5000-digit argument raised
``ValueError: Exceeds the limit (4300 digits)`` and failed the whole file,
including its ordinary lines. Whether a number is positive is a question about
its sign and digits, not about its magnitude.
"""

import re

#: ``\p`` that is not the start of ``\pbo`` or ``\pos``, its optional ASCII
#: whitespace, sign and digits. Case-sensitive on purpose: there is no evidence
#: that libass accepts ``\P`` as this tag.
_DRAW_TAG_RE = re.compile(r"\\p(?!bo|os)[ \t]*([+-]?)([0-9]*)")

#: ``\N`` (hard break), ``\n`` (soft break) and ``\h`` (hard space) are layout,
#: not language. Python sees the raw two-character sequences as ordinary text,
#: so a lone ``\N`` counted as a stretch of dialogue and made a caption look
#: like two sentences with a drawing between them.
_LAYOUT_ESCAPE_RE = re.compile(r"\\[Nnh]")


def drawing_state_after(tag_block: str, current: bool) -> bool:
    """Drawing mode after ``tag_block``, given it was ``current`` before.

    A single ``{…}`` block can hold several overrides and the last ``\\p`` in it
    wins, which is why the whole block has to be walked rather than searched.
    Blocks with no ``\\p`` tag leave the state alone.
    """
    state = current
    for match in _DRAW_TAG_RE.finditer(tag_block):
        sign, digits = match.group(1), match.group(2)
        state = sign != "-" and any(digit != "0" for digit in digits)
    return state


def without_drawing_tags(tag_block: str) -> str:
    """``tag_block`` with its ``\\p`` tags removed, or "" if nothing remains.

    A sign is usually one event — ``{\\an8\\pos(...)\\p1}`` geometry ``{\\p0}``
    caption — so removing the drawing by deleting the whole opening block took
    the caption's positioning with it and dropped it to the default
    bottom-centre.
    """
    stripped = _DRAW_TAG_RE.sub("", tag_block)
    return "" if stripped in ("{}", "") else stripped


def holds_language(text: str) -> bool:
    """Whether ``text`` carries something worth translating.

    Layout escapes are removed first: ``\\N`` alone is a line break, not a
    sentence, and treating it as one made the selection skip whole captions.
    """
    return bool(_LAYOUT_ESCAPE_RE.sub(" ", text).strip())
