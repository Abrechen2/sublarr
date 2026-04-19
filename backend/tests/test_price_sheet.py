"""Price sheet lookup tests."""

from decimal import Decimal


def test_known_llm_combo():
    from translation.price_sheet import get_llm_price

    in_price, out_price = get_llm_price("claude", "claude-sonnet-4-6")
    assert in_price == Decimal("3.00")
    assert out_price == Decimal("15.00")


def test_known_char_backend():
    from translation.price_sheet import get_char_price

    assert get_char_price("deepl") == Decimal("20.00")


def test_unknown_llm_combo_returns_zero(caplog):
    from translation.price_sheet import get_llm_price

    with caplog.at_level("WARNING", logger="translation.price_sheet"):
        in_price, out_price = get_llm_price("unknown_backend", "unknown_model")
    assert in_price == Decimal("0")
    assert out_price == Decimal("0")
    assert any("price unknown" in r.message.lower() for r in caplog.records)


def test_unknown_char_backend_returns_zero():
    from translation.price_sheet import get_char_price

    assert get_char_price("unknown_char_backend") == Decimal("0")


def test_warn_emitted_once_per_combo(caplog):
    """Subsequent lookups for same unknown combo should not spam logs."""
    from translation.price_sheet import _reset_warned, get_llm_price

    _reset_warned()
    with caplog.at_level("WARNING", logger="translation.price_sheet"):
        get_llm_price("never_heard", "also_never")
        get_llm_price("never_heard", "also_never")
        get_llm_price("never_heard", "also_never")
    warn_count = sum(1 for r in caplog.records if "price unknown" in r.message.lower())
    assert warn_count == 1


def test_ollama_free_tier():
    from translation.price_sheet import get_llm_price

    in_price, out_price = get_llm_price("ollama", "any-model")
    assert in_price == Decimal("0")
    assert out_price == Decimal("0")
