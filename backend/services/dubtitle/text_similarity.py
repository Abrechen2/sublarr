"""Text-normalisation + similarity primitives for dubtitle detection.

Pure stdlib, no external dependencies — so the scoring core is trivially
unit-testable without ffmpeg/Whisper. Gemini's review (2026-06-14) flagged
that ``difflib.SequenceMatcher`` is too order-sensitive for ASR output,
which drops/swaps small words and mangles names. We therefore score with a
**token-set containment** metric: of the content words a subtitle cue
claims are spoken, what fraction actually appear in the dub transcript.

A dubtitle (transcribes the English dub) scores high against the dub
transcript (~0.7-0.9); a fansub (translates the Japanese) scores low
(~0.2-0.4) because the wording diverges. The gap is wide and stable even
with noisy ASR, which is exactly what makes the threshold robust.
"""

from __future__ import annotations

import re

# ASS/SSA inline override blocks: {\an8}, {\pos(..)} etc. — never spoken.
_ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")
# Bracketed SDH/CC annotations and music notes: "[door creaks]", "(sighs)",
# "♪ theme ♪". These describe sound, they are not dialogue, so they must not
# count toward an audio match.
_BRACKETED_RE = re.compile(r"[\[\(][^\]\)]*[\]\)]")
_MUSIC_RE = re.compile(r"[♪♫𝄞]")
# Speaker labels at the start of a cue: "NARRATOR:", "- John:".
_SPEAKER_RE = re.compile(r"^\s*[-–]?\s*[A-Z][A-Z0-9 .'_-]{0,24}:\s*", re.MULTILINE)
# Anything that is not a letter/number/apostrophe becomes a separator.
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9']+")

# Conversational fillers + ASR hallucination fragments that carry no signal.
_FILLERS: frozenset[str] = frozenset(
    {
        "uh",
        "uhh",
        "um",
        "umm",
        "ah",
        "ahh",
        "eh",
        "oh",
        "hm",
        "hmm",
        "mm",
        "mmm",
        "huh",
        "er",
        "err",
    }
)


def normalize_to_tokens(text: str, *, strip_bracketed: bool = True) -> list[str]:
    """Lower-case ``text`` and return a list of content tokens.

    Strips ASS override blocks, optional bracketed SDH annotations, speaker
    labels and music notes, then splits on non-alphanumeric characters and
    drops conversational fillers. ``strip_bracketed`` is True when scoring a
    *subtitle* (the bracketed sound descriptions are not spoken) and may be
    False for a raw transcript where there is nothing bracketed to remove.
    """
    if not text:
        return []
    text = _ASS_OVERRIDE_RE.sub(" ", text)
    text = _SPEAKER_RE.sub(" ", text)
    if strip_bracketed:
        text = _BRACKETED_RE.sub(" ", text)
    text = _MUSIC_RE.sub(" ", text)
    text = text.replace("\\N", " ").replace("\\n", " ")
    text = text.lower()
    tokens = [t for t in _TOKEN_SPLIT_RE.split(text) if t and t not in _FILLERS]
    return tokens


def containment_score(sub_tokens: set[str], transcript_tokens: set[str]) -> float:
    """Fraction of ``sub_tokens`` that also occur in ``transcript_tokens``.

    Asymmetric on purpose: we ask "how much of what this subtitle says is
    actually spoken in the dub", not the reverse. Returns 0.0 when the
    subtitle has no content tokens, which correctly disqualifies a
    signs/empty track from being mistaken for the dubtitle.
    """
    if not sub_tokens:
        return 0.0
    overlap = len(sub_tokens & transcript_tokens)
    return overlap / len(sub_tokens)


def jaccard_score(a_tokens: set[str], b_tokens: set[str]) -> float:
    """Symmetric Jaccard overlap of two token sets (0.0 when both empty)."""
    if not a_tokens and not b_tokens:
        return 0.0
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    return len(a_tokens & b_tokens) / len(union)
