from translation.llm_utils import build_prompt_with_glossary


def test_glossary_block_format():
    entries = [{"source_term": "Naruto", "target_term": "Naruto"}]
    result = build_prompt_with_glossary("Translate:", entries, ["Hello"])
    assert "<glossary>" in result
    assert "Naruto → Naruto" in result
    assert "</glossary>" in result


def test_glossary_limit_50():
    entries = [{"source_term": f"term{i}", "target_term": f"trans{i}"} for i in range(60)]
    result = build_prompt_with_glossary("Translate:", entries, ["Hello"])
    # Max 50 entries injected
    assert result.count("→") == 50


def test_only_approved_entries_injected():
    entries = [
        {"source_term": "Konoha", "target_term": "Konoha", "approved": 1},
        {"source_term": "Pending", "target_term": "Pending", "approved": 0},
    ]
    result = build_prompt_with_glossary("Translate:", entries, ["Hello"])
    assert "Konoha" in result
    assert "Pending" not in result


def test_no_glossary_entries_no_block():
    result = build_prompt_with_glossary("Translate:", [], ["Hello"])
    assert "<glossary>" not in result


def test_none_glossary_no_block():
    result = build_prompt_with_glossary("Translate:", None, ["Hello"])
    assert "<glossary>" not in result
