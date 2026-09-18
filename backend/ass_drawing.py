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

#: ``\p`` and its argument, spelled the way the renderer reads it. Every part
#: of this pattern was read off rendered frames rather than off a document —
#: 19 probes through the image's own ffmpeg/libass, each matched against a
#: "plain dialogue" and a "geometry" reference:
#:
#:     \ p1   \  p1   \<tab>p1     on   — whitespace may follow the backslash
#:     \ P1                        off  — still not this tag
#:     \ pbo3                      off  — still the baseline-offset tag
#:     \p(1)  \p(+1)  \p( 1 )      on   — ONE opening parenthesis is skipped
#:     \p((1))                     off  — a second one is not
#:     \p(1                        on   — the parenthesis need not close
#:     \p1x   \p1)   \p1 2         on   — digits are greedy, the rest ignored
#:     \p0x                        off
_DRAW_TAG_RE = re.compile(r"\\[ \t]*p(?!bo|os)[ \t]*\(?[ \t]*([+-]?)([0-9]*)")

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


def contains_drawing_tag(text: str) -> bool:
    """Whether ``text`` holds a ``\\p`` tag at all, by the same reading.

    Exists so a caller can skip the per-line walk cheaply without inventing a
    second, looser test for the same thing — which is how ``{\\ p1}`` slipped
    past the sanitizer's shortcut while its walk would have caught it.
    """
    return _DRAW_TAG_RE.search(text) is not None


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
