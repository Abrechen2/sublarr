"""GeminiBackend tests — mocked requests.post."""

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


def _gemini(api_key="AIza-test", model="gemini-2.5-pro"):
    from translation.gemini import GeminiBackend

    return GeminiBackend(api_key=api_key, model=model)


def test_construction_requires_api_key():
    from translation.gemini import GeminiBackend

    with pytest.raises(ValueError, match="api_key"):
        GeminiBackend(api_key="", model="gemini-2.5-pro")


def test_default_model_and_prices():
    b = _gemini()
    assert b.name == "gemini"
    assert b.default_model == "gemini-2.5-pro"
    assert b.cost_per_1m_tokens_in == Decimal("1.25")
    assert b.cost_per_1m_tokens_out == Decimal("5.00")
    assert b.supports_glossary is True
    assert b.supports_batch is True


def test_build_request_converts_openai_to_gemini_shape():
    """Convert {role:system, content:...} → systemInstruction.parts."""
    b = _gemini()
    messages = [
        {"role": "system", "content": "translate to de"},
        {"role": "user", "content": "hello"},
    ]
    payload = b._build_request(messages, max_tokens=500)
    assert "systemInstruction" in payload
    assert payload["systemInstruction"]["parts"][0]["text"] == "translate to de"
    assert "contents" in payload
    assert payload["contents"][0]["role"] == "user"
    assert payload["contents"][0]["parts"][0]["text"] == "hello"
    # No top-level "system" or OpenAI-style messages
    assert "system" not in payload
    assert "messages" not in payload


def test_build_request_has_generation_config():
    """max_tokens should translate to generationConfig.maxOutputTokens."""
    b = _gemini()
    payload = b._build_request([{"role": "user", "content": "x"}], max_tokens=500)
    assert payload.get("generationConfig", {}).get("maxOutputTokens") == 500


def test_parse_response_extracts_tokens():
    from translation.llm_base import LLMResponse

    b = _gemini()
    raw = {
        "candidates": [
            {
                "content": {"parts": [{"text": "hallo\nwelt"}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 30,
            "candidatesTokenCount": 20,
            "totalTokenCount": 50,
        },
        "modelVersion": "gemini-2.5-pro",
    }
    resp = b._parse_response(raw)
    assert isinstance(resp, LLMResponse)
    assert resp.translations == ["hallo", "welt"]
    assert resp.tokens_in == 30
    assert resp.tokens_out == 20
    assert resp.finish_reason == "STOP"


def test_parse_response_safety_surfaces_as_content_filter():
    b = _gemini()
    raw = {
        "candidates": [
            {
                "content": {"parts": [{"text": ""}], "role": "model"},
                "finishReason": "SAFETY",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 0,
            "totalTokenCount": 10,
        },
        "modelVersion": "gemini-2.5-pro",
    }
    resp = b._parse_response(raw)
    assert resp.finish_reason == "content_filter"


def test_call_api_uses_api_key_in_query():
    """API key is passed as ?key=... query param (not Authorization header)."""
    b = _gemini()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {"parts": [{"text": "ok"}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 1,
            "candidatesTokenCount": 1,
            "totalTokenCount": 2,
        },
        "modelVersion": "gemini-2.5-pro",
    }
    with patch("translation.gemini.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        b._call_api(
            {
                "systemInstruction": {"parts": [{"text": "x"}]},
                "contents": [{"role": "user", "parts": [{"text": "y"}]}],
                "generationConfig": {"maxOutputTokens": 100},
            },
            timeout_s=60,
        )
    call_args = mock_post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
    # URL must include the model + ?key=
    assert "gemini-2.5-pro" in url
    assert "key=AIza-test" in url
    # Headers should NOT include Authorization
    headers = call_args.kwargs.get("headers") or {}
    assert "Authorization" not in headers


def test_cost_calculation_matches_price_sheet():
    from translation.cost_tracker import calculate_llm_cost_micro_usd

    b = _gemini()
    # 1000 * 1.25/1M + 500 * 5/1M = 0.00125 + 0.0025 = 0.00375 = 3750 micro_usd
    cost = calculate_llm_cost_micro_usd(
        tokens_in=1000,
        tokens_out=500,
        price_in_per_1m=b.cost_per_1m_tokens_in,
        price_out_per_1m=b.cost_per_1m_tokens_out,
    )
    assert cost == 3750


def test_end_to_end_with_mock(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("gemini", 2)
    b = _gemini()

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {"parts": [{"text": "hallo\nwelt\ntest"}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 30,
            "candidatesTokenCount": 20,
            "totalTokenCount": 50,
        },
        "modelVersion": "gemini-2.5-pro",
    }
    with patch("translation.gemini.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            result = b.translate_batch(
                ["hi", "world", "test"],
                source_lang="en",
                target_lang="de",
            )
    assert result.success is True
    assert result.translated_lines == ["hallo", "welt", "test"]
