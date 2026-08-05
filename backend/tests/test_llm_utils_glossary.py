"""Tests for V8-compatible glossary injection and single-line mode in llm_utils."""

from translation.llm_utils import build_prompt_with_glossary, parse_llm_response

# ---------------------------------------------------------------------------
# build_prompt_with_glossary — format
# ---------------------------------------------------------------------------


def test_glossary_uses_comma_separated_format():
    """Glossary must use 'Glossary: term → trans' prefix, not XML blocks."""
    entries = [{"source_term": "Nakama", "target_term": "Gruppe"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Hello Nakama", "World"])
    assert result.startswith("Glossary: Nakama \u2192 Gruppe")
    assert "<glossary>" not in result
    assert "</glossary>" not in result


def test_glossary_multiple_entries_comma_joined():
    entries = [
        {"source_term": "Nakama", "target_term": "Gruppe"},
        {"source_term": "Jutsu", "target_term": "Technik"},
    ]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Nakama used a Jutsu"])
    # Single-line mode — check glossary prefix
    assert "Glossary: Nakama \u2192 Gruppe, Jutsu \u2192 Technik" in result


def test_glossary_limit_is_15():
    """Only 15 entries may be injected (V8 training constraint)."""
    entries = [{"source_term": f"term{i}", "target_term": f"trans{i}"} for i in range(20)]
    # All 20 occur in the input, so only the cap can reduce them.
    line = " ".join(f"term{i}" for i in range(20))
    result = build_prompt_with_glossary("Translate:\n", entries, [line, "World"])
    assert result.count("\u2192") == 15


def test_only_approved_entries_injected():
    """Entries with approved == 0 must be excluded."""
    entries = [
        {"source_term": "Konoha", "target_term": "Konoha", "approved": 1},
        {"source_term": "Pending", "target_term": "Pending", "approved": 0},
    ]
    # Both terms occur in the input, so only the approved flag can filter.
    result = build_prompt_with_glossary("Translate:\n", entries, ["Konoha Pending", "World"])
    glossary_line = result.split("\n\n")[0]
    assert "Konoha" in glossary_line
    assert "Pending" not in glossary_line


def test_glossary_drops_terms_absent_from_the_lines():
    """A term that cannot apply to this batch is prompt noise."""
    entries = [
        {"source_term": "Nakama", "target_term": "Gruppe"},
        {"source_term": "Jutsu", "target_term": "Technik"},
    ]
    result = build_prompt_with_glossary("Translate:\n", entries, ["The Jutsu failed."])
    assert "Jutsu → Technik" in result
    assert "Nakama" not in result


def test_glossary_match_is_case_insensitive():
    entries = [{"source_term": "Nakama", "target_term": "Gruppe"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["my nakama are here"])
    assert "Nakama → Gruppe" in result


def test_glossary_omitted_entirely_when_no_term_applies():
    """Measured harm, not just tidiness.

    gemma3:12b returned the glossary line itself instead of a translation in
    8 of 16 runs over short subtitle lines when the glossary held a single
    entry that did not occur in the input. That answer is one line, so
    _verify_line_count accepts it and the garbage reaches the subtitle file.
    """
    entries = [{"source_term": "Onii-sama", "target_term": "Onii-sama"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Understood."])
    assert "Glossary:" not in result


def test_no_glossary_entries_no_prefix():
    result = build_prompt_with_glossary("Translate:\n", [], ["Hello", "World"])
    assert "Glossary:" not in result
    assert "<glossary>" not in result


def test_none_glossary_no_prefix():
    result = build_prompt_with_glossary("Translate:\n", None, ["Hello", "World"])
    assert "Glossary:" not in result


def test_all_unapproved_no_prefix():
    entries = [{"source_term": "X", "target_term": "Y", "approved": 0}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Hello", "World"])
    assert "Glossary:" not in result


# ---------------------------------------------------------------------------
# build_prompt_with_glossary — single-line mode
# ---------------------------------------------------------------------------


def test_single_line_appends_line_to_template_unnumbered():
    """When len(lines) == 1, the line follows the template un-numbered."""
    result = build_prompt_with_glossary("Translate:\n", None, ["Guten Morgen"])
    assert result == "Translate:\nReturn exactly 1 line.\n\nGuten Morgen"


def test_single_line_with_glossary():
    entries = [{"source_term": "Nakama", "target_term": "Gruppe"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Nakama wa doko?"])
    assert result.startswith("Glossary: Nakama \u2192 Gruppe\n\n")
    assert result.endswith("Nakama wa doko?")


def test_single_line_no_numbered_prefix():
    """Single-line prompt must NOT contain '1:' numbering."""
    result = build_prompt_with_glossary("Translate:\n", None, ["Hello"])
    assert "1:" not in result


def test_multi_line_uses_numbered_format():
    result = build_prompt_with_glossary("Translate:\n", None, ["Line A", "Line B"])
    assert "1: Line A" in result
    assert "2: Line B" in result


# ---------------------------------------------------------------------------
# build_prompt_with_glossary — single line must carry the same constraints
# as a batch.  Regression guard for the prod "expected 1" line-count storm:
# a bare "Translate to German: <line>" prompt has no output-format rule, so
# the model answers with prose/alternatives spanning several lines and
# LLMBackend._verify_line_count rejects the whole job.
# ---------------------------------------------------------------------------

_REAL_TEMPLATE = (
    "Translate these anime subtitle lines from English to German.\n"
    "Return ONLY the translated lines, one per line, same count.\n"
    "Preserve \\N exactly as \\N (hard line break).\n"
    "Do NOT add numbering or prefixes to the output lines.\n\n"
)


def test_single_line_carries_output_format_constraint():
    """A one-line batch must still tell the model to return exactly the lines."""
    result = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello"])
    assert _REAL_TEMPLATE in result


def test_single_line_respects_target_language_from_template():
    """Target language comes from the template — never hardcoded to German."""
    template = "Translate these anime subtitle lines from English to French.\n\n"
    result = build_prompt_with_glossary(template, None, ["Hello"])
    assert "French" in result
    assert "German" not in result


def test_single_line_states_the_expected_line_count():
    """Naming the count is what stops the model inventing extra lines."""
    result = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello"])
    assert "Return exactly 1 line." in result


def test_batch_states_the_expected_line_count():
    result = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello", "World", "Again"])
    assert "Return exactly 3 lines." in result


def test_constraints_precede_the_subtitle_input():
    """Instructions must come BEFORE the lines, never after.

    The fine-tuned model echoes a trailing instruction back as an extra
    output line (measured 4/10 on anime-translator-en-de-v15), which is
    itself the line-count mismatch we are trying to prevent.
    """
    result = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello"], strict=True)
    assert result.index("exactly 1 line") < result.index("Hello")
    assert result.rstrip().endswith("Hello")


def test_strict_mode_hardens_the_constraint():
    normal = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello"])
    strict = build_prompt_with_glossary(_REAL_TEMPLATE, None, ["Hello"], strict=True)
    assert strict != normal
    assert "no more, no fewer" in strict


# ---------------------------------------------------------------------------
# parse_llm_response — single-line mode
# ---------------------------------------------------------------------------


def test_parse_single_line_returns_list_with_one_element():
    result = parse_llm_response("Guten Morgen", 1)
    assert result == ["Guten Morgen"]


def test_parse_single_line_strips_whitespace():
    result = parse_llm_response("  Hallo Welt  \n", 1)
    assert result == ["Hallo Welt"]


def test_parse_single_line_empty_returns_none():
    result = parse_llm_response("   ", 1)
    assert result is None


def test_parse_single_line_too_long_returns_none():
    result = parse_llm_response("x" * 501, 1)
    assert result is None


def test_parse_single_line_exactly_500_chars_ok():
    result = parse_llm_response("a" * 500, 1)
    assert result == ["a" * 500]


def test_parse_multi_line_unchanged():
    """Multi-line parsing must still work as before."""
    response = "1: Hallo\n2: Welt"
    result = parse_llm_response(response, 2)
    assert result == ["Hallo", "Welt"]


def test_parse_multi_line_count_mismatch_returns_none():
    result = parse_llm_response("Only one line", 3)
    assert result is None
