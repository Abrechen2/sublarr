"""MistralBackend tests — mocked requests.post."""

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


def _mistral(api_key="sk-test", model="mistral-large-latest"):
    from translation.mistral import MistralBackend

    return MistralBackend(api_key=api_key, model=model)


def test_construction_requires_api_key():
    from translation.mistral import MistralBackend

    with pytest.raises(ValueError, match="api_key"):
        MistralBackend(api_key="", model="mistral-large-latest")


def test_default_model_and_prices():
    b = _mistral()
    assert b.name == "mistral"
    assert b.default_model == "mistral-large-latest"
    assert b.cost_per_1m_tokens_in == Decimal("2.00")
    assert b.cost_per_1m_tokens_out == Decimal("6.00")
    assert b.supports_glossary is True
    assert b.supports_batch is True


def test_build_request_preserves_openai_shape():
    """Mistral accepts OpenAI chat/completions format — no reshape."""
    b = _mistral()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    assert payload["model"] == "mistral-large-latest"
    assert payload["messages"] == messages  # unchanged
    assert payload["max_tokens"] == 500


def test_parse_response_extracts_tokens():
    from translation.llm_base import LLMResponse

    b = _mistral()
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
        "model": "mistral-large-latest",
    }
    resp = b._parse_response(raw)
    assert isinstance(resp, LLMResponse)
    assert resp.translations == ["hallo", "welt"]
    assert resp.tokens_in == 30
    assert resp.tokens_out == 20
    assert resp.finish_reason == "stop"


def test_call_api_uses_bearer_auth():
    b = _mistral()
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
        "model": "mistral-large-latest",
    }
    with patch("translation.mistral.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        b._call_api(
            {
                "model": "mistral-large-latest",
                "messages": [{"role": "user", "content": "y"}],
                "max_tokens": 100,
            },
            timeout_s=60,
        )
    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    assert "api.mistral.ai" in url
    assert "chat/completions" in url
    headers = call_args.kwargs.get("headers") or {}
    assert headers.get("Authorization") == "Bearer sk-test"


def test_cost_calculation_matches_price_sheet():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    b = _mistral()
    # 1000 * 2.00/1M + 500 * 6.00/1M = 0.002 + 0.003 = 0.005 = 5000 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=b.cost_per_1m_tokens_in,
        price_out_per_1m=b.cost_per_1m_tokens_out,
    )
    assert cost == 5000


def test_mistral_small_model_also_priced():
    b = _mistral(model="mistral-small-latest")
    assert b.cost_per_1m_tokens_in == Decimal("0.20")
    assert b.cost_per_1m_tokens_out == Decimal("0.60")


def test_config_fields_present():
    b = _mistral()
    field_names = {f["key"] if isinstance(f, dict) else f.key for f in b.config_fields}
    assert "api_key" in field_names
    assert "model" in field_names


def test_end_to_end_with_mock(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("mistral", 2)
    b = _mistral()

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
        "model": "mistral-large-latest",
    }
    with patch("translation.mistral.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            result = b.translate_batch(
                ["hi", "world", "test"],
                source_lang="en",
                target_lang="de",
            )
    assert result.success is True
    assert result.translated_lines == ["hallo", "welt", "test"]
