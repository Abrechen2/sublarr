"""MyMemoryBackend tests."""

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


def _mymemory(email=""):
    from translation.mymemory import MyMemoryBackend

    return MyMemoryBackend(email=email)


def test_no_auth_required_for_construction():
    """MyMemory works with no email — free tier."""
    b = _mymemory()
    assert b.name == "mymemory"
    assert b.email == ""


def test_email_config_optional():
    b = _mymemory(email="user@example.com")
    assert b.email == "user@example.com"


def test_char_price_is_zero():
    """MyMemory free tier — cost is 0."""
    b = _mymemory()
    assert b.cost_per_1m_chars == Decimal("0")


def test_call_uses_get_with_langpair(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("mymemory", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "responseData": {"translatedText": "hallo"},
        "responseStatus": 200,
    }
    b = _mymemory()
    with patch("translation.mymemory.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        with app.app_context():
            result = b.translate_batch(["hello"], source_lang="en", target_lang="de")

    assert result.success is True
    assert result.translated_lines == ["hallo"]
    params = mock_get.call_args.kwargs.get("params") or {}
    assert params["q"] == "hello"
    assert params["langpair"] == "en|de"


def test_email_passed_when_configured(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("mymemory", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "responseData": {"translatedText": "hallo"},
        "responseStatus": 200,
    }
    b = _mymemory(email="user@test.com")
    with patch("translation.mymemory.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        with app.app_context():
            b.translate_batch(["hello"], source_lang="en", target_lang="de")
    params = mock_get.call_args.kwargs.get("params") or {}
    assert params["de"] == "user@test.com"


def test_per_line_loop_multiple_requests(app, reset_conc):
    """3 lines -> 3 GET calls."""
    from translation.concurrency import get_concurrency

    get_concurrency().register("mymemory", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "responseData": {"translatedText": "t"},
        "responseStatus": 200,
    }
    b = _mymemory()
    with patch("translation.mymemory.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        with app.app_context():
            b.translate_batch(["a", "b", "c"], source_lang="en", target_lang="de")
    assert mock_get.call_count == 3


def test_quota_exceeded_raises(app, reset_conc):
    from translation.concurrency import get_concurrency

    get_concurrency().register("mymemory", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "responseData": {},
        "responseStatus": 429,
        "responseDetails": "MYMEMORY WARNING: YOU USED ALL YOUR ... QUOTA.",
    }
    b = _mymemory()
    with patch("translation.mymemory.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        with app.app_context(), pytest.raises(RuntimeError, match="MyMemory"):
            b.translate_batch(["x"], source_lang="en", target_lang="de")


def test_cost_always_zero(app, reset_conc):
    from db.models.translation import TranslationEvent
    from extensions import db
    from translation.concurrency import get_concurrency

    get_concurrency().register("mymemory", 2)

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "responseData": {"translatedText": "hallo"},
        "responseStatus": 200,
    }
    b = _mymemory()
    with patch("translation.mymemory.requests.get") as mock_get:
        mock_get.return_value = mock_resp
        with app.app_context():
            b.translate_batch(["hello"], source_lang="en", target_lang="de")

    with app.app_context():
        row = db.session.query(TranslationEvent).filter_by(backend="mymemory").one()
        assert row.cost_estimate_micro_usd == 0
