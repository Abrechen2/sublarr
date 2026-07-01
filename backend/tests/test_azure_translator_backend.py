"""AzureTranslatorBackend tests."""

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


def _azure(api_key="sub-test", region="westeurope"):
    from translation.azure_translator import AzureTranslatorBackend

    return AzureTranslatorBackend(api_key=api_key, region=region)


def test_construction_requires_api_key():
    from translation.azure_translator import AzureTranslatorBackend

    with pytest.raises(ValueError, match="api_key"):
        AzureTranslatorBackend(api_key="", region="westeurope")


def test_default_region_westeurope():
    from translation.azure_translator import AzureTranslatorBackend

    b = AzureTranslatorBackend(api_key="k")
    assert b.region == "westeurope"


def test_char_price_from_sheet():
    b = _azure()
    assert b.cost_per_1m_chars == Decimal("10.00")
    assert b.name == "azure_translator"


def test_call_uses_subscription_key_header(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("azure_translator", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {"translations": [{"text": "hallo", "to": "de"}]},
        {"translations": [{"text": "welt", "to": "de"}]},
    ]
    b = _azure()
    with patch("translation.azure_translator.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            result = b.translate_batch(
                ["hello", "world"],
                source_lang="en",
                target_lang="de",
            )

    assert result.success is True
    assert result.translated_lines == ["hallo", "welt"]
    call_args = mock_post.call_args
    headers = call_args.kwargs.get("headers") or {}
    assert headers.get("Ocp-Apim-Subscription-Key") == "sub-test"
    assert headers.get("Ocp-Apim-Subscription-Region") == "westeurope"


def test_url_includes_target_lang(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("azure_translator", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {"translations": [{"text": "hallo", "to": "de"}]},
    ]
    b = _azure()
    with patch("translation.azure_translator.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            b.translate_batch(["hello"], source_lang="en", target_lang="de")
    url = mock_post.call_args.args[0]
    assert "to=de" in url
    assert "from=en" in url


def test_cost_calculation(app, reset_conc):
    """Cost should be chars_in * $10/1M."""
    from db.models.translation import TranslationEvent
    from extensions import db
    from translation.concurrency import get_concurrency

    get_concurrency().register("azure_translator", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = [
        {"translations": [{"text": "x" * 100, "to": "de"}]},
    ]
    b = _azure()
    with patch("translation.azure_translator.requests.post") as mock_post:
        mock_post.return_value = mock_resp
        with app.app_context():
            b.translate_batch(["helloworld"], source_lang="en", target_lang="de")

    with app.app_context():
        row = db.session.query(TranslationEvent).filter_by(backend="azure_translator").one()
        # 10 chars * 10/1M = 100 micro_usd
        assert row.cost_estimate_micro_usd == 100
        assert row.chars_in == 10
        assert row.chars_out == 100


def test_error_writes_error_event(app, reset_conc):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translation.concurrency import get_concurrency

    get_concurrency().register("azure_translator", 2)

    b = _azure()
    with patch("translation.azure_translator.requests.post") as mock_post:
        mock_post.side_effect = RuntimeError("api down")
        with app.app_context(), pytest.raises(RuntimeError):
            b.translate_batch(["x"], source_lang="en", target_lang="de")

    with app.app_context():
        row = db.session.query(TranslationEvent).filter_by(backend="azure_translator").one()
        assert row.status == "error"
        assert row.error_type == "RuntimeError"


def test_config_fields_present():
    b = _azure()
    field_names = {f["key"] if isinstance(f, dict) else f.key for f in b.config_fields}
    assert "api_key" in field_names
    assert "region" in field_names


def test_supports_batch_not_glossary():
    b = _azure()
    assert b.supports_batch is True
    assert b.supports_glossary is False
