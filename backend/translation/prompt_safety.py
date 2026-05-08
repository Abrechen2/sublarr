"""Prompt-injection guard primitives for LLM translation backends (P3).

Centralises every defence the translation layer applies to provider-supplied
subtitle text BEFORE handing it to a remote or local LLM. All translation
backends - Ollama, OpenAI/ChatGPT, Claude, Gemini, Mistral, DeepSeek - must
funnel untrusted input through these helpers so a compromised subtitle
provider cannot pivot a translation request into prompt injection, token
flooding, or Trojan-Source obfuscation.

Threat model:
- Attacker controls subtitle text via a compromised or malicious provider.
- Output of the LLM lands back in the user's subtitle file. Local LLMs
  (Ollama on the LAN) prevent direct exfiltration, but the same payload
  could weaponise a remote backend (OpenAI etc.).
- Defences here are character-level + geometric, not pattern-based:
  pattern matching for "Ignore previous instructions" is too brittle and
  modern LLMs are reasonably resistant when the prompt structure is firm.

Defences applied:
- Newline / carriage-return escaping prevents breaking the trained
  numbered prompt format ("1: ...\\n2: ...").
- Null-byte stripping.
- Zero-width + bidirectional-override stripping mitigates Trojan Source
  (CVE-2021-42574) where invisible chars hide adversarial directives.
- Per-line character cap bounds token cost and stops single-line
  context-window blowups.
- Per-batch line/character caps (``enforce_batch_size``) bound total
  cost, prevent token-flooding, and surface malicious-batch input early.
"""

from __future__ import annotations

# Subtitle lines rarely exceed ~250 chars; 2000 is a generous upper bound
# that still cuts off pathological payloads cleanly.
MAX_LINE_CHARS = 2000

# Max lines per single LLM call. Existing backends declare smaller limits
# (Ollama batches at 25, OpenAI-compat at 50). 100 is the absolute ceiling
# enforced at the orchestration layer regardless of caller.
MAX_BATCH_LINES = 100

# Max total characters across an entire batch. Subtitles average 40-70 chars;
# 100 lines at average length sit well under this cap. A batch above 50k
# chars is either a corrupt file or an attack - fail closed.
MAX_BATCH_CHARS_TOTAL = 50_000

# Zero-width + bidirectional-format + Unicode-tag codepoints that an attacker
# can use to hide adversarial instructions inside otherwise-innocuous subtitle
# text. Includes Trojan Source (CVE-2021-42574) bidi-override characters and
# Unicode Tag block (U+E0000-U+E007F) used for invisible metadata smuggling.
_ZERO_WIDTH_CODEPOINTS = (
    # Soft hyphen — invisible word-break, can split adversarial keywords.
    0x00AD,
    # Zero-width formatting.
    0x200B,  # zero-width space
    0x200C,  # zero-width non-joiner
    0x200D,  # zero-width joiner
    0x2060,  # word joiner
    0xFEFF,  # zero-width no-break space (BOM)
    # Line/paragraph separators - parsers treat these as newlines but
    # str.replace("\n", ...) does NOT catch them; strip outright.
    0x2028,  # LINE SEPARATOR
    0x2029,  # PARAGRAPH SEPARATOR
    # Bidirectional-override / isolate chars (Trojan Source CVE-2021-42574).
    0x202A,  # LRE - Left-to-Right Embedding
    0x202B,  # RLE - Right-to-Left Embedding
    0x202C,  # PDF - Pop Directional Formatting
    0x202D,  # LRO - Left-to-Right Override
    0x202E,  # RLO - Right-to-Left Override
    # Invisible math/operator codepoints used for obfuscation.
    0x2061,  # FUNCTION APPLICATION
    0x2062,  # INVISIBLE TIMES
    0x2063,  # INVISIBLE SEPARATOR
    0x2064,  # INVISIBLE PLUS
    # Deprecated language-tag formatting block.
    0x206A,  # INHIBIT SYMMETRIC SWAPPING
    0x206B,  # ACTIVATE SYMMETRIC SWAPPING
    0x206C,  # INHIBIT ARABIC FORM SHAPING
    0x206D,  # ACTIVATE ARABIC FORM SHAPING
    0x206E,  # NATIONAL DIGIT SHAPES
    0x206F,  # NOMINAL DIGIT SHAPES
    # Bidirectional isolates.
    0x2066,  # LRI - Left-to-Right Isolate
    0x2067,  # RLI - Right-to-Left Isolate
    0x2068,  # FSI - First Strong Isolate
    0x2069,  # PDI - Pop Directional Isolate
)

# Unicode Tag block (U+E0000-U+E007F): designed for language tagging but
# repurposed for hidden-payload smuggling. We strip the entire block via a
# range check in escape_for_prompt rather than enumerating 128 codepoints.
_TAG_BLOCK_START = 0xE0000
_TAG_BLOCK_END = 0xE007F


class PromptBatchTooLargeError(ValueError):
    """Raised when a translate batch exceeds line or character caps."""


def escape_for_prompt(text: str | None, max_chars: int = MAX_LINE_CHARS) -> str:
    """Sanitise a single piece of untrusted text for inclusion in an LLM prompt.

    - Replaces ``\\r\\n`` / ``\\r`` / ``\\n`` with their literal escape
      sequences so they cannot break the surrounding numbered/structured
      prompt format.
    - Strips null bytes.
    - Strips zero-width + bidi-override Unicode.
    - Truncates to ``max_chars``.

    ``None`` is treated as the empty string so callers can pipe optional
    fields (``series_context`` etc.) through without a guard.
    """
    if not text:
        return ""
    escaped = text.replace("\r\n", "\\r\\n").replace("\r", "\\r").replace("\n", "\\n")
    # Strip C0 control bytes that LLM tokenisers/parsers may treat as
    # delimiters or string terminators: NUL, vertical tab, form feed.
    for ctrl in ("\x00", "\x0b", "\x0c"):
        escaped = escaped.replace(ctrl, "")
    for cp in _ZERO_WIDTH_CODEPOINTS:
        escaped = escaped.replace(chr(cp), "")
    # Strip the entire Unicode Tag block (U+E0000-U+E007F) in one pass.
    # Iterating ord() once is cheaper than 128 .replace() calls.
    if any(_TAG_BLOCK_START <= ord(ch) <= _TAG_BLOCK_END for ch in escaped):
        escaped = "".join(
            ch for ch in escaped if not (_TAG_BLOCK_START <= ord(ch) <= _TAG_BLOCK_END)
        )
    if len(escaped) > max_chars:
        escaped = escaped[:max_chars]
    return escaped


def enforce_batch_size(lines: list[str]) -> None:
    """Reject batches that exceed the line or total-character cap.

    Raises:
        PromptBatchTooLargeError: when ``len(lines) > MAX_BATCH_LINES`` or
            the summed character count exceeds ``MAX_BATCH_CHARS_TOTAL``.
    """
    if len(lines) > MAX_BATCH_LINES:
        raise PromptBatchTooLargeError(
            f"Batch has {len(lines)} lines, exceeds cap of {MAX_BATCH_LINES}"
        )
    total = sum(len(line) for line in lines)
    if total > MAX_BATCH_CHARS_TOTAL:
        raise PromptBatchTooLargeError(
            f"Batch has {total} characters, exceeds cap of {MAX_BATCH_CHARS_TOTAL}"
        )
