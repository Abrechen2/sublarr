"""ClaudeBackend tests — mocked Anthropic client."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SUBLARR_DB_PATH", str(tmp_path / "app.db"))
    from config import reload_settings

    reload_settings()
    from app import create_app

    app = create_app(testing=True)
    from extensions import db as sa_db

    with app.app_context():
        sa_db.create_all()
    yield app


@pytest.fixture
def reset_conc():
    from translation.concurrency import reset_for_tests

    reset_for_tests()


def _claude(api_key="sk-test", model="claude-sonnet-4-6"):
    from translation.claude import ClaudeBackend

    return ClaudeBackend(api_key=api_key, model=model)


def test_construction_requires_api_key():
    from translation.claude import ClaudeBackend

    with pytest.raises(ValueError, match="api_key"):
        ClaudeBackend(api_key="", model="claude-sonnet-4-6")


def test_default_model_and_prices():
    from translation.claude import ClaudeBackend

    b = ClaudeBackend(api_key="sk-test", model="claude-sonnet-4-6")
    assert b.name == "claude"
    assert b.default_model == "claude-sonnet-4-6"
    assert b.cost_per_1m_tokens_in == Decimal("3.00")
    assert b.cost_per_1m_tokens_out == Decimal("15.00")
    assert b.supports_glossary is True
    assert b.supports_batch is True
    assert b.max_batch_size == 50


def test_build_request_splits_system_from_messages():
    """Anthropic wants system as a separate param, not inside messages."""
    b = _claude()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    # System is a TOP-LEVEL parameter, may be a list with cache_control
    assert "system" in payload
    # messages array must NOT contain the system message
    assert all(m["role"] != "system" for m in payload["messages"])
    assert payload["max_tokens"] == 500
    assert payload["model"] == "claude-sonnet-4-6"


def test_build_request_enables_prompt_caching():
    """System prompt should be wrapped with cache_control for 90% cost savings."""
    b = _claude()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    # System should be a list of blocks with cache_control
    assert isinstance(payload["system"], list)
    assert payload["system"][0]["type"] == "text"
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_parse_response_extracts_tokens():
    from translation.llm_base import LLMResponse

    b = _claude()
    raw = {
        "content": [{"type": "text", "text": "hallo\nwelt"}],
        "usage": {"input_tokens": 30, "output_tokens": 20},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    resp = b._parse_response(raw)
    assert isinstance(resp, LLMResponse)
    assert resp.translations == ["hallo", "welt"]
    assert resp.tokens_in == 30
    assert resp.tokens_out == 20
    assert resp.finish_reason == "end_turn"


def test_parse_response_refusal_surfaces_as_content_filter():
    b = _claude()
    raw = {
        "content": [{"type": "text", "text": "I cannot do that"}],
        "usage": {"input_tokens": 10, "output_tokens": 10},
        "model": "claude-sonnet-4-6",
        "stop_reason": "refusal",
    }
    resp = b._parse_response(raw)
    assert resp.finish_reason == "content_filter"


def test_parse_response_splits_cache_tokens_from_fresh_input():
    """Cache-read and cache-write tokens are split from tokens_in so the cost
    calculator can bill them at the right rate (0.1× / 1.25×).
    """
    b = _claude()
    raw = {
        "content": [{"type": "text", "text": "ok"}],
        "usage": {
            "input_tokens": 10,
            "cache_creation_input_tokens": 50,
            "cache_read_input_tokens": 200,
            "output_tokens": 5,
        },
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    resp = b._parse_response(raw)
    # Fresh input only — cache reads/writes now tracked separately
    assert resp.tokens_in == 10
    assert resp.cache_read_tokens == 200
    assert resp.cache_write_tokens == 50
    assert resp.tokens_out == 5


def test_call_api_uses_anthropic_client():
    b = _claude()
    fake_resp = MagicMock()
    fake_resp.model_dump.return_value = {
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    with patch("translation.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_resp
        mock_cls.return_value = mock_client
        b._client = None
        raw = b._call_api(
            {
                "model": "claude-sonnet-4-6",
                "system": [{"type": "text", "text": "x", "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": "y"}],
                "max_tokens": 100,
            },
            timeout_s=60,
        )
    assert raw["content"][0]["text"] == "hi"


def test_cost_calculation_matches_price_sheet():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    b = _claude()
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=b.cost_per_1m_tokens_in,
        price_out_per_1m=b.cost_per_1m_tokens_out,
    )
    assert cost == 10500


def test_config_fields_present():
    b = _claude()
    field_names = {f["key"] if isinstance(f, dict) else f.key for f in b.config_fields}
    assert "api_key" in field_names
    assert "model" in field_names


def test_end_to_end_with_mock(app, reset_conc):
    """translate_batch happy path with mocked anthropic."""
    from translation.concurrency import get_concurrency

    get_concurrency().register("claude", 2)
    b = _claude()

    fake_resp = MagicMock()
    fake_resp.model_dump.return_value = {
        "content": [{"type": "text", "text": "hallo\nwelt\ntest"}],
        "usage": {"input_tokens": 30, "output_tokens": 20},
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
    }
    with patch("translation.claude.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = fake_resp
        mock_cls.return_value = mock_client
        b._client = None
        with app.app_context():
            result = b.translate_batch(
                ["hi", "world", "test"],
                source_lang="en",
                target_lang="de",
            )
    assert result.success is True
    assert result.translated_lines == ["hallo", "welt", "test"]
