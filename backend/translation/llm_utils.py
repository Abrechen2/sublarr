"""Shared LLM utilities for translation backends.

Extracted from ollama_client.py -- these functions are reused by all LLM-based
translation backends (Ollama, OpenAI-compatible) for prompt building, response
parsing, and CJK hallucination detection.
"""

import logging
import re

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
    """Parse LLM response into individual lines.

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
    if strict:
        constraint = (
            f"Return exactly {count} {plural} — no more, no fewer. "
            "No commentary, no alternatives, no numbering.\n\n"
        )
    else:
        constraint = f"Return exactly {count} {plural}.\n\n"

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
