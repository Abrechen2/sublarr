"""Reject LLM output that is chat filler instead of a translation.

Prod 2026-08-18: 1124 translation-memory rows held the model's conversational
replies ("Okay, please provide the English anime subtitle lines...") instead
of translations, written during the batch_size=1 era. The line-count check in
translator.manager cannot catch these — a chat reply is exactly one line —
and once cached they replay into every later file whose source line matches.
"""

import re

# Phrases that only ever appear when the model talks ABOUT translating
# instead of translating. Kept deliberately narrow: a false positive here
# fails the whole batch, so generic words ("ready", "translate") are always
# anchored inside a longer assistant-speak phrase.
_CHAT_FILLER_PATTERNS = (
    r"please provide",
    r"ready when you are",
    r"okay,? i'?m ready",
    r"here (?:is|are) (?:the|your) translat",
    r"subtitle lines? you want me to",
    r"as an ai",
    r"language model",
    r"i can(?:not|'t) translate",
    r"hier (?:ist|sind) die übersetz",
)

_CHAT_FILLER_RE = re.compile("|".join(f"(?:{p})" for p in _CHAT_FILLER_PATTERNS), re.IGNORECASE)


def find_chat_filler(lines):
    """Return (index, line) pairs whose text is chat filler, not a translation.

    Args:
        lines: Translated lines as returned by a backend. None entries
            (cache placeholders) are skipped.

    Returns:
        list[tuple[int, str]]: Offending lines with their index in the batch,
        empty when every line looks like an actual translation.
    """
    return [(i, line) for i, line in enumerate(lines) if line and _CHAT_FILLER_RE.search(line)]
