"""ChatGPTBackend tests — mocked requests.post."""

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


def _chatgpt(api_key="sk-test", model="gpt-4o-mini"):
    from translation.chatgpt import ChatGPTBackend

    return ChatGPTBackend(api_key=api_key, model=model)


def test_construction_requires_api_key():
    from translation.chatgpt import ChatGPTBackend

    with pytest.raises(ValueError, match="api_key"):
        ChatGPTBackend(api_key="", model="gpt-4o-mini")


def test_default_model_and_prices():
    b = _chatgpt()
    assert b.name == "chatgpt"
    assert b.default_model == "gpt-4o-mini"
    assert b.cost_per_1m_tokens_in == Decimal("0.15")
    assert b.cost_per_1m_tokens_out == Decimal("0.60")
    assert b.supports_glossary is True
    assert b.supports_batch is True


def test_build_request_preserves_openai_shape():
    """ChatGPT uses native OpenAI chat/completions format."""
    b = _chatgpt()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["messages"] == messages  # unchanged
    assert payload["max_tokens"] == 500


def test_parse_response_extracts_tokens():
    from translation.llm_base import LLMResponse

    b = _chatgpt()
    raw = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "hallo\nwelt"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 30,
            "completion_tokens": 20,
            "total_tokens": 50,
        },
        "model": "gpt-4o-mini",
    }
    resp = b._parse_response(raw)
    assert isinstance(resp, LLMResponse)
    assert resp.translations == ["hallo", "welt"]
    assert resp.tokens_in == 30
    assert resp.tokens_out == 20
    assert resp.finish_reason == "stop"


def test_call_api_uses_bearer_auth():
    b = _chatgpt()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
        "model": "gpt-4o-mini",
    }
    with patch("translation.chatgpt.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        b._call_api(
            {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "y"}],
                "max_tokens": 100,
            },
            timeout_s=60,
        )
    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert "api.openai.com" in url
    assert "chat/completions" in url
    headers = call_args.kwargs.get("headers") or {}
    assert headers.get("Authorization") == "Bearer sk-test"


def test_cost_calculation_matches_price_sheet():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    b = _chatgpt()
    # 1000 * 0.15/1M + 500 * 0.60/1M = 0.00015 + 0.0003 = 0.00045 = 450 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=b.cost_per_1m_tokens_in,
        price_out_per_1m=b.cost_per_1m_tokens_out,
    )
    assert cost == 450


def test_gpt4o_model_also_priced():
    b = _chatgpt(model="gpt-4o")
    assert b.cost_per_1m_tokens_in == Decimal("2.50")
    assert b.cost_per_1m_tokens_out == Decimal("10.00")


def test_config_fields_present():
    b = _chatgpt()
    field_names = {f["key"] if isinstance(f, dict) else f.key for f in b.config_fields}
    assert "api_key" in field_names
    assert "model" in field_names


def test_end_to_end_with_mock(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("chatgpt", 2)
    b = _chatgpt()

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "hallo\nwelt\ntest"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 30,
            "completion_tokens": 20,
            "total_tokens": 50,
        },
        "model": "gpt-4o-mini",
    }
    with patch("translation.chatgpt.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            result = b.translate_batch(
                ["hi", "world", "test"],
                source_lang="en",
                target_lang="de",
            )
    assert result.success is True
    assert result.translated_lines == ["hallo", "welt", "test"]
