"""LLMBackend base class tests using a fake subclass."""

from decimal import Decimal

import pytest


class _FakeLLM:
    """Fake LLMBackend subclass — deterministic responses, counts hook calls."""

    name = "fake_llm"
    display_name = "Fake LLM"
    default_model = "fake-model-1"
    config_fields = []
    supports_glossary = True
    supports_batch = True
    max_batch_size = 50

    def __init__(self, should_raise=None, line_count_override=None, **kw):
        self.should_raise = should_raise
        self.line_count_override = line_count_override
        self.build_calls = 0
        self.call_calls = 0
        self.parse_calls = 0

    def _build_request(self, messages, max_tokens):
        self.build_calls += 1
        return {"messages": messages, "max_tokens": max_tokens}

    def _call_api(self, payload, timeout_s):
        self.call_calls += 1
        if self.should_raise:
            raise self.should_raise
        return {
            "text": "\n".join(f"translated {i}" for i in range(3)),
            "tokens_in": 30,
            "tokens_out": 40,
        }

    def _parse_response(self, raw):
        self.parse_calls += 1
        from translation.llm_base import LLMResponse

        lines = raw["text"].split("\n")
        if self.line_count_override is not None:
            lines = lines[: self.line_count_override]
        return LLMResponse(
            translations=lines,
            tokens_in=raw["tokens_in"],
            tokens_out=raw["tokens_out"],
            model="fake-model-1",
            finish_reason="stop",
            raw_latency_ms=42,
        )

    def health_check(self):
        return (True, "ok")

    def get_config_fields(self):
        return []


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


def _build_backend(should_raise=None, line_count_override=None):
    from translation.concurrency import get_concurrency, reset_for_tests
    from translation.llm_base import LLMBackend

    reset_for_tests()
    get_concurrency().register("fake_llm", 2)

    class TestLLM(_FakeLLM, LLMBackend):
        cost_per_1m_tokens_in = Decimal("3.00")
        cost_per_1m_tokens_out = Decimal("15.00")

    return TestLLM(should_raise=should_raise, line_count_override=line_count_override)


def test_happy_path_invokes_hooks_in_order(app):
    with app.app_context():
        backend = _build_backend()
        result = backend.translate_batch(
            ["line one", "line two", "line three"],
            source_lang="en",
            target_lang="de",
        )
    assert result.success is True
    assert len(result.translated_lines) == 3
    assert backend.build_calls == 1
    assert backend.call_calls == 1
    assert backend.parse_calls == 1


def test_error_writes_event_and_raises(app):
    with app.app_context():
        backend = _build_backend(should_raise=RuntimeError("api down"))
        with pytest.raises(RuntimeError, match="api down"):
            backend.translate_batch(
                ["x"],
                source_lang="en",
                target_lang="de",
            )

    # Event should be in DB
    from db.models.translation import TranslationEvent
    from extensions import db

    with app.app_context():
        rows = db.session.query(TranslationEvent).filter_by(backend="fake_llm").all()
        assert len(rows) == 1
        assert rows[0].status == "error"
        assert rows[0].error_type == "RuntimeError"


def test_cost_tracked_on_success(app):
    with app.app_context():
        backend = _build_backend()
        backend.translate_batch(
            ["x"] * 3,
            source_lang="en",
            target_lang="de",
        )

    from db.models.translation import TranslationEvent
    from extensions import db

    with app.app_context():
        row = db.session.query(TranslationEvent).filter_by(backend="fake_llm").one()
        # 30 in @ $3/1M + 40 out @ $15/1M = 0.00009 + 0.0006 = 0.00069 USD = 690 micro_usd
        assert row.cost_estimate_micro_usd == 690


def test_line_count_mismatch_retries_once(app):
    """LLM returns fewer lines than requested -> retry once then raise."""
    with app.app_context():
        # line_count_override=2 means subclass always returns 2 lines — retry won't help
        backend = _build_backend(line_count_override=2)
        from translation.llm_base import LineCountMismatchError

        with pytest.raises(LineCountMismatchError):
            backend.translate_batch(
                ["a", "b", "c"],
                source_lang="en",
                target_lang="de",
            )
    # build+call+parse should have been called twice (initial + 1 retry)
    assert backend.build_calls == 2
    assert backend.call_calls == 2


def test_semaphore_released_on_exception(app):
    """If API raises, the concurrency slot must be released."""
    from translation.concurrency import get_concurrency

    with app.app_context():
        backend = _build_backend(should_raise=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            backend.translate_batch(["x"], source_lang="en", target_lang="de")

        # Slot must be free — acquire should not block
        with get_concurrency().slot("fake_llm", timeout_s=0.1):
            pass  # if slot leaked, this would timeout


def test_cancel_flag_respected(app):
    """If cancel is requested, translate_batch raises JobCancelledError."""
    from translation.llm_base import JobCancelledError
    from translation.queue_state import get_queue_state, reset_for_tests

    reset_for_tests()
    qs = get_queue_state()
    qs.register_job(
        job_id="test_cancel",
        file_path="/x/a.mkv",
        source_lang="en",
        target_lang="de",
        backend="fake_llm",
        total_lines=10,
    )
    qs.cancel("test_cancel")

    with app.app_context():
        backend = _build_backend()
        with pytest.raises(JobCancelledError):
            backend.translate_batch(
                ["a"] * 10,
                source_lang="en",
                target_lang="de",
                job_id="test_cancel",
            )
