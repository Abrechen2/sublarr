"""Which writing system a subtitle uses, and whether it fits the language it claims.

Sublarr moves subtitle text between four places — the container, a provider,
the translator and the disk — and every one of them labels the text by a
language tag it took on trust. Prod 2026-09-07 held eighteen ``.de.srt``
files whose letters were Arabic, Chinese or Japanese: a provider's "German"
upload that was Chinese, and a spring-2026 extractor that wrote the first
foreign track under the target-language name. Nobody looked at the letters.

This module looks at the letters. It answers one narrow question — "is this
text written in the script that language uses?" — and deliberately nothing
more: English under a German name passes, because that is a language
problem, not a script problem, and this check must never produce a false
alarm on a file that merely needs translating.

Scripts are counted per letter (``str.isalpha``), so timings, numbers,
punctuation and markup do not vote. A verdict needs at least ``min_letters``
letters and is only "mismatch" when the expected script holds less than a
fifth of them — a German line quoting a sign in kanji is still German.
"""

from __future__ import annotations

import re
from collections import Counter

# Languages grouped by the script they are written in. Anything not listed
# here yields no opinion — the check is a guard against the gross case, not
# a language identifier.
_SCRIPT_BY_LANGUAGE: dict[str, str] = {
    **dict.fromkeys(
        (
            "af", "az", "bs", "ca", "cs", "da", "de", "en", "es", "et", "eu", "fi", "fr",
            "gl", "hr", "hu", "id", "is", "it", "lt", "lv", "ms", "nl", "no", "pl", "pt",
            "ro", "sk", "sl", "sq", "sv", "sw", "tl", "tr", "uz", "vi",
        ),
        "latin",
    ),
    **dict.fromkeys(("bg", "kk", "mk", "mn", "ru", "sr", "uk"), "cyrillic"),
    **dict.fromkeys(("ar", "fa", "ur"), "arabic"),
    "he": "hebrew",
    "el": "greek",
    "th": "thai",
    "hi": "devanagari",
    **dict.fromkeys(("ja", "zh", "ko", "zh-hans", "zh-hant"), "cjk"),
}  # fmt: skip

# Unicode ranges per script. Half-open on purpose: (lo, hi) means lo <= cp < hi.
_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0041, 0x005B, "latin"),
    (0x0061, 0x007B, "latin"),
    (0x00C0, 0x0250, "latin"),  # Latin-1 Supplement + Extended-A/B
    (0x1E00, 0x1F00, "latin"),  # Latin Extended Additional (Vietnamese)
    (0x0370, 0x0400, "greek"),
    (0x0400, 0x0530, "cyrillic"),
    (0x0590, 0x0600, "hebrew"),
    (0x0600, 0x0700, "arabic"),
    (0x0750, 0x0780, "arabic"),
    (0x08A0, 0x0900, "arabic"),
    (0x0900, 0x0980, "devanagari"),
    (0x0E00, 0x0E80, "thai"),
    (0x3040, 0x3100, "cjk"),  # hiragana + katakana
    (0x3400, 0x4DC0, "cjk"),  # CJK Extension A
    (0x4E00, 0xA000, "cjk"),  # CJK Unified Ideographs
    (0xAC00, 0xD7B0, "cjk"),  # Hangul syllables
    (0xF900, 0xFB00, "cjk"),  # CJK Compatibility Ideographs
    (0xFF66, 0xFFA0, "cjk"),  # halfwidth katakana
)

_MARKUP_RE = re.compile(r"<[^>]{1,40}>|\{[^}]{1,80}\}")
_SAMPLE_CHARS = 65536

# Scripts the check may pass a verdict on. CJK is deliberately absent: a
# Japanese or Korean release routinely carries romaji lyrics, karaoke and
# English lines under its own tag, so "not enough CJK letters" is not evidence
# of a mislabel there. The failures this guard exists for all ran the other
# way — Arabic, Chinese, Japanese under a German name.
_JUDGED_SCRIPTS = frozenset(
    {"latin", "cyrillic", "greek", "arabic", "hebrew", "thai", "devanagari"}
)


def decode_sample(data: bytes) -> str:
    """Decode subtitle bytes for the script check.

    Honours a UTF-16 BOM and guesses UTF-16-LE from interleaved NULs; falls
    back to UTF-8 with undecodable bytes dropped. Reading UTF-16 as UTF-8
    would keep the ASCII half of every code unit and drop the rest — the
    Latin letters of ``Dialogue:`` survive, the CJK text does not.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "ignore")
    head = data[:2048]
    if head and head.count(b"\x00") > len(head) // 4:
        return data.decode("utf-16-le", "ignore")
    return data.decode("utf-8", "ignore")


def _dialogue_text(text: str) -> str:
    """Return only the cue text of an ASS/SSA script; other formats unchanged.

    The ``[Script Info]`` and ``[V4+ Styles]`` sections are hundreds of Latin
    letters (``ScriptType``, ``Fontname``, ``Arial``) that would outvote the
    dialogue of a short file.
    """
    if "[Script Info]" not in text and "\nDialogue:" not in text:
        return text
    cues = []
    for line in text.splitlines():
        if line.startswith(("Dialogue:", "Comment:")):
            parts = line.split(",", 9)
            if len(parts) == 10:
                cues.append(parts[9])
    return "\n".join(cues)


def expected_script(lang: str | None) -> str | None:
    """Return the script a language is written in, or None when unknown."""
    from config_language_data import normalize_language_code

    code = normalize_language_code((lang or "").strip().lower())
    if not code:
        return None
    if code in _SCRIPT_BY_LANGUAGE:
        return _SCRIPT_BY_LANGUAGE[code]
    return _SCRIPT_BY_LANGUAGE.get(code.split("-", 1)[0])


def _script_of(char: str) -> str | None:
    cp = ord(char)
    for lo, hi, script in _RANGES:
        if lo <= cp < hi:
            return script
    return None


def script_shares(text: str) -> tuple[Counter, int]:
    """Count letters per script. Returns (counter, total_letters)."""
    counts: Counter = Counter()
    total = 0
    for ch in text:
        if not ch.isalpha():
            continue
        total += 1
        script = _script_of(ch)
        if script is not None:
            counts[script] += 1
    return counts, total


def script_mismatch(
    text: str | None,
    lang: str | None,
    *,
    min_letters: int = 40,
    min_share: float = 0.2,
) -> str | None:
    """Return a reason when ``text`` is clearly not written in ``lang``'s script.

    None means "no objection": the text fits, the language's script is not
    known here or is one the check does not judge (CJK), or there is too
    little text to judge.
    """
    expected = expected_script(lang)
    if expected is None or expected not in _JUDGED_SCRIPTS or not text:
        return None
    sample = _MARKUP_RE.sub(" ", _dialogue_text(text[:_SAMPLE_CHARS]))
    counts, total = script_shares(sample)
    if total < min_letters:
        return None
    share = counts.get(expected, 0) / total
    if share >= min_share:
        return None
    dominant, dominant_n = (counts.most_common(1) or [("unknown", 0)])[0]
    return (
        f"expected {expected} script for '{lang}', found {dominant} "
        f"in {dominant_n * 100 // total}% of {total} letters"
    )


def find_script_mismatch(
    lines,
    lang: str | None,
    *,
    min_letters: int = 20,
) -> str | None:
    """``script_mismatch`` over a batch of lines; None entries are skipped."""
    text = "\n".join(line for line in lines if line)
    return script_mismatch(text, lang, min_letters=min_letters)
