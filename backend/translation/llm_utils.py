"""Shared LLM utilities for translation backends.

Extracted from ollama_client.py -- these functions are reused by all LLM-based
translation backends (Ollama, OpenAI-compatible) for prompt building, response
parsing, and CJK hallucination detection.
"""

import logging
import re
from collections import Counter

from translation.prompt_safety import MAX_LINE_CHARS, escape_for_prompt

logger = logging.getLogger(__name__)

# Back-compat alias — existing tests/callers import _MAX_LINE_LENGTH directly.
_MAX_LINE_LENGTH = MAX_LINE_CHARS

# CJK Unicode ranges for hallucination detection (Qwen2.5 sometimes drifts into Chinese)
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"  # CJK Unified Ideographs
    r"\u3400-\u4dbf"  # CJK Extension A
    r"\u2e80-\u2eff"  # CJK Radicals
    r"\uf900-\ufaff]"  # CJK Compatibility Ideographs
)

# Score extraction from LLM evaluation responses (matches 0-100, prefers last match)
_SCORE_RE = re.compile(r"\b(100|[1-9]?\d)\b")

# Default quality score when LLM evaluation fails or is not available
DEFAULT_QUALITY_SCORE = 50


def has_cjk_hallucination(text: str) -> bool:
    """Detect CJK characters in translated text (LLM hallucination).

    Qwen2.5 and other multilingual LLMs sometimes drift into Chinese characters
    when translating between non-CJK languages.

    Args:
        text: Translated text to check

    Returns:
        True if CJK characters are detected
    """
    return bool(_CJK_RE.search(text))


def parse_llm_response(response_text: str, expected_count: int) -> list[str] | None:
    """Parse LLM response into individual lines. **Legacy shim — unused.**

    Kept importable for out-of-tree callers only. No backend has ever called
    it: every LLM backend splits in its own ``_parse_response`` and the shared
    repair lives in :func:`repair_line_mapping`, which is what
    ``LLMBackend._attempt`` applies. Its merge-on-numbering branch was
    therefore never reached in production, while the default prompt forbade
    numbering outright — so even the shape it repairs could not occur.
    Prefer :func:`repair_line_mapping` for new code.

    Handles numbered responses (e.g. "1: text") and plain lines.
    Attempts to merge split lines before truncating.

    Single-line mode: when ``expected_count == 1`` the V8 model returns a
    single un-numbered line.  We accept it as-is (stripped) and reject
    empty or suspiciously long results (> 500 chars) by returning ``None``
    so the caller can trigger a retry.

    Args:
        response_text: Raw LLM response text
        expected_count: Number of lines expected

    Returns:
        List of parsed lines, or None if count mismatch cannot be resolved
    """
    # Single-line mode: model returns exactly one plain line (no numbering)
    if expected_count == 1:
        translation = response_text.strip()
        if not translation or len(translation) > 500:
            return None
        return [translation]

    lines = response_text.strip().split("\n")
    lines = [l for l in lines if l.strip()]

    # Strip numbering if present (e.g. "1: text" or "1. text")
    cleaned = []
    for line in lines:
        stripped = re.sub(r"^\d+[\.:]\s*", "", line)
        cleaned.append(stripped)

    if len(cleaned) == expected_count:
        return cleaned

    # Too many lines: try merging consecutive non-numbered lines
    if len(cleaned) > expected_count:
        logger.warning(
            "Got %d lines, expected %d. Trying to merge excess lines.",
            len(cleaned),
            expected_count,
        )
        merged = []
        for i, line in enumerate(cleaned):
            original = lines[i] if i < len(lines) else ""
            if re.match(r"^\d+[\.:]\s*", original):
                merged.append(line)
            elif merged:
                merged[-1] = merged[-1] + " " + line
            else:
                merged.append(line)

        if len(merged) == expected_count:
            return merged

        logger.warning("Merge failed (%d lines), returning None for retry", len(merged))
        return None

    logger.warning(
        "Line count mismatch: got %d, expected %d",
        len(cleaned),
        expected_count,
    )
    return None


_HARD_BREAK = "\\N"  # literal backslash-N, the ASS hard line break


def strip_invented_hard_breaks(source_lines: list[str], translated_lines: list[str]) -> list[str]:
    """Drop hard line breaks the model added where the source had none.

    Sublarr's contract with a translation backend is a 1:1 line mapping, and
    where a subtitle event carries no hard break the translation must not
    introduce one — it changes how the line renders against the original. LLMs
    do it anyway: one measured episode went from 28 source lines carrying a
    break to 158 in the German output. The line *count* stays correct, so no
    other check in the pipeline can see it.

    Only lines whose source has no break at all are touched, so a break the
    subtitle actually asked for survives untouched. An inner break becomes a
    single space (it was standing between two words); a trailing one simply
    goes. Lists of differing length are returned unchanged — pairing would be
    guesswork, and the caller already treats that as a failure.
    """
    if len(source_lines) != len(translated_lines):
        return translated_lines

    cleaned: list[str] = []
    for source, translated in zip(source_lines, translated_lines, strict=True):
        if _HARD_BREAK in source or _HARD_BREAK not in translated:
            cleaned.append(translated)
            continue
        without = translated.replace(_HARD_BREAK, " ")
        cleaned.append(re.sub(r"\s+", " ", without).strip())
    return cleaned


_SOFT_BREAK = "\\n"  # literal backslash-n; ASS's soft break, models emit it for \N

_MARKER_ONLY = {_HARD_BREAK, _SOFT_BREAK, _HARD_BREAK * 2, "\\"}

# "1: text", "1. text", "1) text", " 2: text", "3 : text" -- every shape the
# model was measured to produce once the prompt asks it to number its output.
_LINE_NUMBER_RE = re.compile(r"^\s*(\d+)\s*[.:)]\s*")

# How far a line number may exceed the batch length before it stops looking
# like an index into it. Two, because a batch can come back with a line or two
# too many and its numbering still be real.
_NUMBER_RANGE_SLACK = 2


def repair_line_mapping(raw_lines: list[str]) -> list[str]:
    """Turn a model's raw output lines into one line per source line.

    The model writes a hard break and then a real newline after it. Depending
    on where that happens the break marker ends up alone on a line of its own,
    or it ends a content line whose remainder lands on the next one. Both look
    like "too many lines" to every count-based check, and both are repairable
    without guessing: a translation is never merely a line break, and a line
    that carries no number of its own cannot be a line of its own once the
    model has been asked to number them.

    Measured against 65 recorded gemma3:12b batches: dropping marker-only
    lines alone repaired 3 of the 5 over-long batches and altered none of the
    57 correct ones. The looser rule of joining any line that ends in a break
    marker was measured too and rejected -- it damaged 33 of those 57, because
    a translation may legitimately end on a break.

    Whether a batch is numbered at all is decided for the batch as a whole by
    :func:`_looks_numbered`, never line by line — a single missing number would
    otherwise send every number behind it into the finished subtitle, which is
    what a per-line counter did on the live host. Where the batch is not
    numbered, leading numbers stay: ``13: Das Bankett`` is a subtitle that
    opens with a number, and the old ``^\\d+[.:]`` strip silently ate it.

    Output that carries no numbering at all is returned untouched apart from
    blank and marker-only lines, so a user template that forbids numbering
    keeps working exactly as before.
    """
    kept = [raw for raw in raw_lines if raw.strip() and raw.strip() not in _MARKER_ONLY]
    if not kept:
        return []

    matches = [_LINE_NUMBER_RE.match(raw) for raw in kept]
    numbers = [int(m.group(1)) for m in matches if m is not None]
    numbered = _looks_numbered(numbers, len(kept))

    out: list[str] = []
    for raw, match in zip(kept, matches, strict=True):
        if numbered and match is not None:
            out.append(_strip_repeated_number(raw, match))
        elif numbered and out:
            previous = out[-1].rstrip()
            joiner = "" if previous.endswith((_HARD_BREAK, _SOFT_BREAK)) else " "
            out[-1] = previous + joiner + raw.strip()
        else:
            out.append(raw)
    return out


def _strip_repeated_number(raw: str, match: re.Match) -> str:
    """Remove the line's number, and a second copy of it if the model wrote one.

    Asked to prefix each output line with the number of its input line, gemma3
    copies the input's number and then adds its own: ``2: 2: Wenn wir jetzt
    aufgeben, ...``. Measured live, 14 of one batch's 15 lines came back that
    way. Removing one prefix leaves the other in the finished subtitle.

    Only a repeat of the *same* number goes. ``5: 13: Das Bankett`` is line
    five whose text opens with a number, and stripping greedily would eat it.
    """
    rest = raw[match.end() :]
    repeat = _LINE_NUMBER_RE.match(rest)
    if repeat is not None and repeat.group(1) == match.group(1):
        return rest[repeat.end() :]
    return rest


def _looks_numbered(numbers: list[int], line_count: int) -> bool:
    """Is this batch numbered, judged as a whole rather than line by line?

    Deciding per line was measured wrong on the live host: gemma3 answered the
    one-word line ``No.`` with ``Nein.`` and no number, then numbered 2 through
    15 correctly. A counter waiting for a 1 never advanced, and all fourteen
    numbers behind it reached the finished subtitle. Judging the batch as a
    whole survives a single missing number.

    Two independent signals have to agree, because either alone misfires:

    * an ascending run of at least two numbers, or a first number of 1 — a
      solitary ``13:`` is a subtitle that opens with a number, not numbering;
    * numbers that could plausibly index these lines. Two content lines opening
      with ``1995:`` and ``2001:`` ascend perfectly and are still just text.
    """
    if not numbers:
        return False
    if max(numbers) > line_count + _NUMBER_RANGE_SLACK:
        return False
    if numbers[0] == 1:
        return True
    return len(numbers) >= 2 and all(b > a for a, b in zip(numbers, numbers[1:]))


# A token that tends to come through a translation unchanged, so it can tie an
# output line back to the source line it belongs to: a run of digits, or a word
# of three letters or more — names, places, numbers, cognates. Very common short
# words are no danger because only tokens unique within the batch are used, and
# "the"/"und" are never unique; the length floor exists to keep the token set
# small. Re-measured on the numbered prompt over 1728 correct batches from five
# episodes: a floor of 3 is the shortest that never called one of them shifted.
# Two would see 34.9% of the defect against 31.2%, and costs a false alarm.
_ANCHOR_RE = re.compile(r"[0-9]+|[^\W\d_]{3,}", re.UNICODE)

# How many anchors must agree on the same offset before we call a batch shifted.
# One is a coincidence and unusable: over the same 1728 correct batches a lone
# anchor wandered on 181 of them, while two never agreed on a single one. Three
# buys nothing — it is no safer, it only halves what the check can see, from
# 31.2% of the defect to 17.4%.
_MIN_AGREEING_ANCHORS = 2


def _anchor_tokens(line: str) -> set[str]:
    """Lower-cased tokens from ``line`` that can anchor it to its translation."""
    text = line.replace(_HARD_BREAK, " ").replace(_SOFT_BREAK, " ")
    return {match.group(0).lower() for match in _ANCHOR_RE.finditer(text)}


def _unique_homes(lines: list[str]) -> dict[str, int]:
    """Map each anchor token to its line index, or -1 if it occurs in several.

    Only a token that appears exactly once carries positional information; one
    that repeats could be matched to any of its occurrences and would invent
    offsets that are not there.
    """
    homes: dict[str, int] = {}
    for index, tokens in enumerate(lines):
        for token in tokens:
            homes[token] = index if token not in homes else -1
    return homes


def find_line_shift(source_lines: list[str], translated_lines: list[str]) -> int | None:
    """Return the offset a batch's lines drifted by, or ``None`` if aligned.

    A model can return exactly the requested number of lines and still hand
    back a batch in which the lines no longer correspond to the source. It
    splits one source line across two output lines and merges two others
    further down, so the total comes out right while every line in between sits
    against the wrong subtitle event — the dialogue runs out of sync on screen.
    A count check cannot see this by construction, which is why the defect
    survived every guard in the pipeline.

    Detection works off anchors: digits and longer words usually survive
    translation intact, so a token that occurs on exactly one source line and
    exactly one output line says where that line ended up. Anchors that landed
    where they started say nothing; the rest vote on an offset, and a batch is
    reported as shifted when at least ``_MIN_AGREEING_ANCHORS`` of them agree.

    Returns the offset (positive: output sits later than its source) so callers
    can log something diagnosable. Lists of differing length return ``None`` —
    that is the caller's line-count failure, not this one.

    Silence is not a clean bill of health, and the gap is wide: an anchor only
    votes when it sits inside the displaced run, so where the defect falls in
    the batch decides whether it can be seen at all. Injected into every place
    it could sit across 123 real batches, 31.2% were seen and 68.8% were not,
    and a quarter of the batches are blind wherever it sits. The share rises
    with the size of the damage — 4.5% when two lines are displaced, 74.6% when
    fourteen are — so this catches the wrecked batches and misses the small
    ones. It never pointed the wrong way: all 3332 it saw, it measured
    correctly, and it called none of 1728 correct batches shifted.
    """
    if len(source_lines) != len(translated_lines) or len(source_lines) < 2:
        return None

    source_homes = _unique_homes([_anchor_tokens(line) for line in source_lines])
    target_homes = _unique_homes([_anchor_tokens(line) for line in translated_lines])

    votes: Counter[int] = Counter()
    for token, source_index in source_homes.items():
        target_index = target_homes.get(token, -1)
        if source_index < 0 or target_index < 0 or target_index == source_index:
            continue
        votes[target_index - source_index] += 1

    if not votes:
        return None
    shift, agreeing = votes.most_common(1)[0]
    return shift if agreeing >= _MIN_AGREEING_ANCHORS else None


def _escape_subtitle_line(line: str) -> str:
    """Back-compat shim — escape subtitle text for inclusion in an LLM prompt.

    Source of truth lives in :mod:`translation.prompt_safety`. New code should
    import :func:`translation.prompt_safety.escape_for_prompt` directly; this
    wrapper exists so legacy imports
    (``from translation.llm_utils import _escape_subtitle_line``) keep working.
    """
    return escape_for_prompt(line, max_chars=_MAX_LINE_LENGTH)


def _is_valid_glossary_entry(term: str) -> bool:
    """Validate a glossary term before including it in a prompt.

    Returns False if the term is too long or contains newlines that could
    inject prompt breaks.
    """
    return len(term) <= 100 and "\n" not in term and "\r" not in term


def build_prompt_with_glossary(
    prompt_template: str,
    glossary_entries: list[dict] | None,
    lines: list[str],
    *,
    strict: bool = False,
) -> str:
    """Build a translation prompt with glossary terms prepended.

    Only approved entries (approved != 0) are injected, capped at 15.
    The glossary is rendered as a comma-separated inline line in the format
    the V8 fine-tuned model was trained on:
      ``Glossary: term1 → trans1, term2 → trans2``

    Single-line mode: when only one subtitle line is provided the line is
    appended to the template un-numbered, so the model returns a single
    un-numbered translation. The template itself is always included — it
    carries the output-format constraint and the target language.

    Args:
        prompt_template: Base prompt template (used for every batch size)
        glossary_entries: List of {source_term, target_term[, approved]} dicts
        lines: List of subtitle lines to translate
        strict: Harden the line-count constraint — used by the retry after a
            count mismatch, so the retry does not re-send an identical prompt

    Returns:
        Complete prompt with optional glossary prefix, the expected line
        count, and the subtitle lines (numbered for batches)
    """
    # Escape subtitle lines to prevent prompt injection via embedded newlines
    escaped_lines = [_escape_subtitle_line(line) for line in lines]

    # Filter out non-approved entries (approved == 0 means pending suggestion)
    # Also reject entries whose terms contain newlines or exceed the max length
    approved_entries: list[dict] = []
    if glossary_entries:
        approved_entries = [
            e
            for e in glossary_entries
            if e.get("approved", 1) != 0
            and _is_valid_glossary_entry(e.get("source_term", ""))
            and _is_valid_glossary_entry(e.get("target_term", ""))
        ]

    # Drop entries whose source term does not occur in the lines being
    # translated. Such an entry cannot change the output, and it measurably
    # harms it: with a glossary of one non-occurring entry, gemma3:12b
    # returned the glossary line itself ("Onii-sama → Bruder") instead of a
    # translation in 8 of 16 runs over short subtitle lines — a one-line
    # answer, so _verify_line_count accepts it and the garbage is written to
    # the subtitle file. Three entries, or none, showed 0 of 16. Matching is
    # done against the escaped lines because that is exactly what the model
    # sees, and case-insensitively so inflected/lower-cased mentions count.
    if approved_entries:
        haystack = "\n".join(escaped_lines).lower()
        approved_entries = [
            e for e in approved_entries if e.get("source_term", "").lower() in haystack
        ]

    # Build glossary prefix (V8-compatible comma-separated format, max 15 entries).
    # Even though _is_valid_glossary_entry already rejects newlines + over-long
    # terms, run every term through escape_for_prompt as well so zero-width /
    # bidi-override / Unicode-tag obfuscation attempts are stripped before
    # they reach the model. Belt + braces \u2014 the entries are operator-curated
    # but flow through DB rows (config_entries / glossary table) and are
    # therefore treated as untrusted at this boundary.
    glossary_str = ""
    if approved_entries:
        pairs = ", ".join(
            f"{escape_for_prompt(e['source_term'], max_chars=100)} "
            f"\u2192 "
            f"{escape_for_prompt(e['target_term'], max_chars=100)}"
            for e in approved_entries[:15]
        )
        glossary_str = f"Glossary: {pairs}\n\n"

    # Name the expected line count explicitly. Every instruction has to sit
    # BEFORE the subtitle input: the fine-tune echoes a trailing instruction
    # back as an extra output line, which is itself a count mismatch.
    count = len(escaped_lines)
    plural = "lines" if count != 1 else "line"
    # A one-line batch is handed over un-numbered, which contradicts a template
    # that says every input line carries a number. Saying so costs one sentence
    # and matters more since a failed batch is split: the split bottoms out at
    # exactly this shape, and this is the shape that answered the prod "expected
    # 1" storm with conversation instead of a translation.
    single = (
        " The single line below is not numbered — reply with the translation only."
        if count == 1
        else ""
    )
    if strict:
        # "no numbering" used to stand here and contradicted the template,
        # which asks for the input's numbers back. The retry now hardens the
        # count and the numbering together instead of fighting the prompt it
        # is retrying.
        constraint = (
            f"Return exactly {count} {plural} — no more, no fewer. "
            "Keep each line's own number and merge nothing. "
            f"No commentary, no alternatives.{single}\n\n"
        )
    else:
        constraint = f"Return exactly {count} {plural}.{single}\n\n"

    # Single-line batches pass the line un-numbered (the V8 fine-tune was
    # trained that way); batches stay numbered.
    #
    # Both keep the template + the count line. The former single-line shape
    # was a bare f"Translate to German: {line}" that dropped the template
    # entirely, and with it the output-format rule and the real target
    # language. Measured against the two deployed models, 10 real subtitle
    # lines each, scored the way LLMBackend._verify_line_count scores them:
    #   gemma3:12b (prod)           bare 0/10 — answered with prose,
    #                               "There are a few ways to translate ..."
    #                               template only 7/10, + count line 10/10
    #   anime-translator-en-de-v15  bare 9/10, template only 10/10,
    #                               + count line 10/10
    # The 0/10 is what produced the prod "expected 1" storm. On numbered
    # batches the count line measured neutral (identical hit rate), so both
    # paths carry it and there is one shape to reason about.
    if count == 1:
        body = escaped_lines[0]
    else:
        body = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(escaped_lines))

    return glossary_str + prompt_template + constraint + body


def build_translation_prompt(
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    prompt_template: str | None = None,
    *,
    strict: bool = False,
) -> str:
    """Build a complete translation prompt for LLM backends.

    If no prompt_template is provided, loads the current template from config
    via get_settings().get_prompt_template().

    Args:
        lines: List of subtitle lines to translate
        source_lang: ISO 639-1 source language code
        target_lang: ISO 639-1 target language code
        glossary_entries: Optional glossary terms
        prompt_template: Optional explicit prompt template
        strict: Harden the line-count constraint (used by the retry after a
            count mismatch)

    Returns:
        Complete prompt ready to send to an LLM
    """
    if prompt_template is None:
        from config import get_settings

        prompt_template = get_settings().get_prompt_template()

    return build_prompt_with_glossary(prompt_template, glossary_entries, lines, strict=strict)


def build_evaluation_prompt(
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
) -> str:
    """Build a quality evaluation prompt for a single translation pair.

    Args:
        source_text: Original source subtitle line
        translated_text: Translated subtitle line
        source_lang: ISO 639-1 source language code
        target_lang: ISO 639-1 target language code

    Returns:
        Prompt string asking LLM to rate translation quality 0-100
    """
    safe_source = _escape_subtitle_line(source_text)
    safe_translated = _escape_subtitle_line(translated_text)
    return (
        f"Rate the quality of this subtitle translation from {source_lang} to {target_lang} "
        f"on a scale from 0 to 100, where 100 is a perfect translation. "
        f"Reply with only a single integer number.\n\n"
        f"Original ({source_lang}): {safe_source}\n"
        f"Translation ({target_lang}): {safe_translated}"
    )


def parse_quality_score(response_text: str) -> int:
    """Parse a quality score (0-100) from an LLM evaluation response.

    Extracts the first integer found in the response and clamps it to [0, 100].
    Falls back to DEFAULT_QUALITY_SCORE (50) if no valid number is found.

    Args:
        response_text: Raw LLM response, expected to contain a number

    Returns:
        Integer quality score clamped to [0, 100]
    """
    matches = _SCORE_RE.findall(response_text.strip())
    if not matches:
        logger.debug("Quality score parsing failed for response: %r", response_text[:100])
        return DEFAULT_QUALITY_SCORE

    try:
        score = int(matches[-1])
        return max(0, min(100, score))
    except (ValueError, OverflowError):
        return DEFAULT_QUALITY_SCORE
