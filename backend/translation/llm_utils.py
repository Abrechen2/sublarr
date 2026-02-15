"""Shared LLM utilities for translation backends.

Extracted from ollama_client.py -- these functions are reused by all LLM-based
translation backends (Ollama, OpenAI-compatible) for prompt building, response
parsing, and CJK hallucination detection.
"""

import re
import logging

logger = logging.getLogger(__name__)

# CJK Unicode ranges for hallucination detection (Qwen2.5 sometimes drifts into Chinese)
_CJK_RE = re.compile(
    r"[\u4e00-\u9fff"    # CJK Unified Ideographs
    r"\u3400-\u4dbf"     # CJK Extension A
    r"\u2e80-\u2eff"     # CJK Radicals
    r"\uf900-\ufaff]"    # CJK Compatibility Ideographs
)


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

    Args:
        response_text: Raw LLM response text
        expected_count: Number of lines expected

    Returns:
        List of parsed lines, or None if count mismatch cannot be resolved
    """
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
            len(cleaned), expected_count,
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

        logger.warning("Merge failed (%d lines), truncating to %d", len(merged), expected_count)
        return cleaned[:expected_count]

    logger.warning(
        "Line count mismatch: got %d, expected %d", len(cleaned), expected_count,
    )
    return None


def build_prompt_with_glossary(
    prompt_template: str,
    glossary_entries: list[dict] | None,
    lines: list[str],
) -> str:
    """Build a translation prompt with glossary terms prepended.

    Args:
        prompt_template: Base prompt template
        glossary_entries: List of {source_term, target_term} dicts (max 15)
        lines: List of subtitle lines to translate

    Returns:
        Complete prompt with glossary and numbered lines
    """
    if not glossary_entries:
        numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
        return prompt_template + numbered

    # Build glossary string (max 15 entries)
    glossary_parts = [
        f"{entry['source_term']} \u2192 {entry['target_term']}"
        for entry in glossary_entries[:15]
    ]
    glossary_str = "Glossary: " + ", ".join(glossary_parts) + "\n\n"

    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
    return glossary_str + prompt_template + numbered


def build_translation_prompt(
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    prompt_template: str | None = None,
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

    Returns:
        Complete prompt ready to send to an LLM
    """
    if prompt_template is None:
        from config import get_settings
        prompt_template = get_settings().get_prompt_template()

    return build_prompt_with_glossary(prompt_template, glossary_entries, lines)
