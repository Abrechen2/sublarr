"""Translation price sheet — USD per 1M tokens / characters.

Intentionally code-owned (not UI-configurable) to prevent operators from
silently desyncing local prices from reality. Updates go via version bumps.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

# USD per 1M tokens (in, out). Wildcard "*" matches any model.
PRICE_SHEET_LLM: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    # Anthropic Claude
    ("claude", "claude-sonnet-4-6"): (Decimal("3.00"), Decimal("15.00")),
    ("claude", "claude-opus-4-7"): (Decimal("15.00"), Decimal("75.00")),
    ("claude", "claude-haiku-4-5"): (Decimal("0.25"), Decimal("1.25")),
    # Google Gemini
    ("gemini", "gemini-2.5-pro"): (Decimal("1.25"), Decimal("5.00")),
    ("gemini", "gemini-2.5-flash"): (Decimal("0.075"), Decimal("0.30")),
    # DeepSeek
    ("deepseek", "deepseek-chat"): (Decimal("0.14"), Decimal("0.28")),
    ("deepseek", "deepseek-coder"): (Decimal("0.14"), Decimal("0.28")),
    # OpenAI / OpenAI-compatible
    ("openai_compat", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("openai_compat", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("chatgpt", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("chatgpt", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    # Mistral
    ("mistral", "mistral-large-latest"): (Decimal("2.00"), Decimal("6.00")),
    ("mistral", "mistral-small-latest"): (Decimal("0.20"), Decimal("0.60")),
    # Self-hosted
    ("ollama", "*"): (Decimal("0"), Decimal("0")),
}

# USD per 1M characters for char-priced backends.
PRICE_SHEET_CHARS: dict[str, Decimal] = {
    "deepl": Decimal("20.00"),
    "deepl_pro": Decimal("25.00"),
    "google_translate": Decimal("20.00"),
    "azure_translator": Decimal("10.00"),
    "libretranslate": Decimal("0"),  # self-hosted free
    "mymemory": Decimal("0"),  # free tier only
}

_warned_unknown: set[tuple[str, str | None]] = set()


def _reset_warned() -> None:
    """Test helper — clear the 'warned once' memo."""
    _warned_unknown.clear()


def get_llm_price(backend: str, model: str) -> tuple[Decimal, Decimal]:
    """Look up (input_price, output_price) for an LLM backend+model.

    Returns (0, 0) for unknown combos; logs WARN once per combo.
    """
    key = (backend, model)
    if key in PRICE_SHEET_LLM:
        return PRICE_SHEET_LLM[key]
    wildcard = (backend, "*")
    if wildcard in PRICE_SHEET_LLM:
        return PRICE_SHEET_LLM[wildcard]
    if key not in _warned_unknown:
        _warned_unknown.add(key)
        logger.warning("price unknown for backend=%s model=%s; cost will be 0", backend, model)
    return (Decimal("0"), Decimal("0"))


def get_char_price(backend: str) -> Decimal:
    """Look up USD per 1M characters for a char-priced backend.

    Returns 0 for unknown backends; logs WARN once per backend.
    """
    if backend in PRICE_SHEET_CHARS:
        return PRICE_SHEET_CHARS[backend]
    key = (backend, None)
    if key not in _warned_unknown:
        _warned_unknown.add(key)
        logger.warning("char price unknown for backend=%s; cost will be 0", backend)
    return Decimal("0")
