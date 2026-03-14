"""Tests for V8-compatible glossary injection and single-line mode in llm_utils."""

from translation.llm_utils import build_prompt_with_glossary, parse_llm_response

# ---------------------------------------------------------------------------
# build_prompt_with_glossary — format
# ---------------------------------------------------------------------------


def test_glossary_uses_comma_separated_format():
    """Glossary must use 'Glossary: term → trans' prefix, not XML blocks."""
    entries = [{"source_term": "Nakama", "target_term": "Gruppe"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Hello", "World"])
    assert result.startswith("Glossary: Nakama \u2192 Gruppe")
    assert "<glossary>" not in result
    assert "</glossary>" not in result


def test_glossary_multiple_entries_comma_joined():
    entries = [
        {"source_term": "Nakama", "target_term": "Gruppe"},
        {"source_term": "Jutsu", "target_term": "Technik"},
    ]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Line"])
    # Single-line mode — check glossary prefix
    assert "Glossary: Nakama \u2192 Gruppe, Jutsu \u2192 Technik" in result


def test_glossary_limit_is_15():
    """Only 15 entries may be injected (V8 training constraint)."""
    entries = [{"source_term": f"term{i}", "target_term": f"trans{i}"} for i in range(20)]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Hello", "World"])
    assert result.count("\u2192") == 15


def test_only_approved_entries_injected():
    """Entries with approved == 0 must be excluded."""
    entries = [
        {"source_term": "Konoha", "target_term": "Konoha", "approved": 1},
        {"source_term": "Pending", "target_term": "Pending", "approved": 0},
    ]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Hello", "World"])
    assert "Konoha" in result
    assert "Pending" not in result


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


def test_single_line_uses_translate_to_german_format():
    """When len(lines) == 1, prompt uses 'Translate to German: ...' format."""
    result = build_prompt_with_glossary("Translate:\n", None, ["Guten Morgen"])
    assert result == "Translate to German: Guten Morgen"


def test_single_line_with_glossary():
    entries = [{"source_term": "Nakama", "target_term": "Gruppe"}]
    result = build_prompt_with_glossary("Translate:\n", entries, ["Nakama wa doko?"])
    assert result.startswith("Glossary: Nakama \u2192 Gruppe\n\n")
    assert "Translate to German: Nakama wa doko?" in result


def test_single_line_no_numbered_prefix():
    """Single-line prompt must NOT contain '1:' numbering."""
    result = build_prompt_with_glossary("Translate:\n", None, ["Hello"])
    assert "1:" not in result


def test_multi_line_uses_numbered_format():
    result = build_prompt_with_glossary("Translate:\n", None, ["Line A", "Line B"])
    assert "1: Line A" in result
    assert "2: Line B" in result


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
