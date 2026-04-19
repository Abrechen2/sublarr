"""Cost tracker — integer micro-USD math for translation events.

1 USD = 1_000_000 micro_usd. Integer math avoids float drift over
aggregation of millions of events.
"""

from decimal import ROUND_HALF_EVEN, Decimal

_MICRO_PER_USD = Decimal(1_000_000)
_PER_1M = Decimal(1_000_000)


def calculate_llm_cost_micro_usd(
    tokens_in: int,
    tokens_out: int,
    price_in_per_1m: Decimal,
    price_out_per_1m: Decimal,
) -> int:
    """Cost in micro-USD for an LLM call.

    Prices are quoted per 1,000,000 tokens (standard LLM provider format).
    """
    cost_usd = (
        Decimal(tokens_in) * price_in_per_1m / _PER_1M
        + Decimal(tokens_out) * price_out_per_1m / _PER_1M
    )
    return int((cost_usd * _MICRO_PER_USD).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def calculate_char_cost_micro_usd(
    chars_in: int,
    price_per_1m: Decimal,
) -> int:
    """Cost in micro-USD for a char-priced translation call."""
    cost_usd = Decimal(chars_in) * price_per_1m / _PER_1M
    return int((cost_usd * _MICRO_PER_USD).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def micro_usd_to_usd(micro: int) -> Decimal:
    """Convert integer micro-USD to Decimal USD for display."""
    return (Decimal(micro) / _MICRO_PER_USD).normalize()
