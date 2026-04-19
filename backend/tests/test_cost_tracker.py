"""Cost tracker math tests — integer micro-USD."""

from decimal import Decimal


def test_llm_cost_simple():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 1000 tokens in @ $3/1M, 500 tokens out @ $15/1M
    # in: 1000 * 3 / 1M = $0.003 = 3000 micro_usd
    # out: 500 * 15 / 1M = $0.0075 = 7500 micro_usd
    # total: 10500 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
    )
    assert cost == 10500


def test_llm_cost_zero_tokens_is_zero():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    cost = calculate_llm_cost_micro_usd(0, 0, Decimal("3"), Decimal("15"))
    assert cost == 0


def test_llm_cost_zero_price_is_zero():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    cost = calculate_llm_cost_micro_usd(1000, 500, Decimal("0"), Decimal("0"))
    assert cost == 0


def test_char_cost_simple():
    from translation.cost_tracker import calculate_char_cost_micro_usd

    # 10000 chars @ $20/1M = $0.20 = 200000 micro_usd
    cost = calculate_char_cost_micro_usd(chars_in=10000, price_per_1m=Decimal("20.00"))
    assert cost == 200000


def test_no_float_drift_on_large_sum():
    """Aggregating millions of small events must not drift."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # Each call: 100 tokens in @ $3/1M = $0.0003 = 300 micro_usd
    per_call = calculate_llm_cost_micro_usd(
        tokens_in=100,
        tokens_out=0,
        price_in_per_1m=Decimal("3"),
        price_out_per_1m=Decimal("0"),
    )
    assert per_call == 300
    # 1 million such calls: $300 = 300_000_000 micro_usd exactly
    assert per_call * 1_000_000 == 300_000_000


def test_usd_display_conversion():
    from translation.cost_tracker import micro_usd_to_usd

    assert micro_usd_to_usd(1_000_000) == Decimal("1.00")
    assert micro_usd_to_usd(42) == Decimal("0.000042")
    assert micro_usd_to_usd(0) == Decimal("0")


def test_rounding_deterministic():
    """Half-even rounding — integer result must be stable."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 1 token @ $3/1M = 0.000003 USD = 3.0 micro_usd — exactly 3
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1,
        tokens_out=0,
        price_in_per_1m=Decimal("3"),
        price_out_per_1m=Decimal("0"),
    )
    assert cost == 3
