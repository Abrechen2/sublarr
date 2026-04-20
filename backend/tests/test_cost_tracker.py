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


def test_llm_cost_with_cache_read_tokens_bills_at_tenth_rate():
    """Cache-read tokens are billed at 0.1× the fresh-input rate (90% discount)."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 100 fresh in + 1000 cache reads + 0 out @ $3/1M in, $15/1M out
    # fresh: 100 * 3 / 1M = $0.0003 = 300 micro_usd
    # cache read: 1000 * 3 * 0.1 / 1M = $0.0003 = 300 micro_usd
    # total: 600 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=100,
        tokens_out=0,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
        cache_read_tokens=1000,
    )
    assert cost == 600


def test_llm_cost_with_cache_write_tokens_bills_at_1_25_rate():
    """Cache-write tokens are billed at 1.25× the fresh-input rate (25% premium)."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    # 0 fresh + 1000 cache write + 0 out @ $3/1M in
    # cache write: 1000 * 3 * 1.25 / 1M = $0.00375 = 3750 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=0,
        tokens_out=0,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
        cache_write_tokens=1000,
    )
    assert cost == 3750


def test_llm_cost_cache_tokens_default_zero_preserves_legacy_behaviour():
    """Callers that don't pass cache_* kwargs get the same result as before."""
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    without_kwargs = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
    )
    with_explicit_zero = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    assert without_kwargs == with_explicit_zero == 10500


def test_llm_cost_realistic_claude_scenario_with_90pct_cache_hit():
    """Example: 10k tokens of stable system prompt cached, 500 fresh per call.

    Without caching: 10500 tokens_in @ $3/1M = $0.0315 = 31500 micro_usd
    With caching (first call + write):    500 fresh + 10000 cache_write + 200 out
                                          = 500*3/1M + 10000*3*1.25/1M + 200*15/1M
                                          = 1500 + 37500 + 3000 = 42000 micro_usd
    With caching (subsequent call):       500 fresh + 10000 cache_read + 200 out
                                          = 500*3/1M + 10000*3*0.1/1M + 200*15/1M
                                          = 1500 + 3000 + 3000 = 7500 micro_usd

    After N≥3 calls caching wins. This test pins the arithmetic.
    """
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    first_call = calculate_llm_cost_micro_usd(
        tokens_in=500,
        tokens_out=200,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
        cache_write_tokens=10000,
    )
    assert first_call == 42000

    subsequent_call = calculate_llm_cost_micro_usd(
        tokens_in=500,
        tokens_out=200,
        price_in_per_1m=Decimal("3.00"),
        price_out_per_1m=Decimal("15.00"),
        cache_read_tokens=10000,
    )
    assert subsequent_call == 7500


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
