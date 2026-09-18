"""Quality evaluation has to report to the breaker it consults.

``evaluate_line_quality`` asks ``allow_request()`` before calling a backend but
never recorded the outcome. Two consequences, both seen on prod 2026-09-17:

- ``allow_request()`` returns True for HALF_OPEN as well as CLOSED, and only a
  recorded success or failure leaves that state. A quality pass that probes
  first therefore latches the breaker in HALF_OPEN, where it lets *every*
  following evaluation through — the breaker is effectively disabled for this
  path while it looks armed.
- A failed evaluation returns ``DEFAULT_QUALITY_SCORE`` (50), which is not
  below the threshold, so the loop moves to the next line and pays the request
  timeout again, once per line, for the whole file.
"""

import os

import pytest

from config import reload_settings
from db import close_db, init_db
from translation.base import TranslationBackend, TranslationResult


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    from app import create_app

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "test_quality_breaker.db")
    os.environ["SUBLARR_API_KEY"] = ""
    os.environ["SUBLARR_LOG_LEVEL"] = "ERROR"
    reload_settings()
    app = create_app(testing=True)
    with app.app_context():
        init_db()
        yield
    close_db()
    for key in ("SUBLARR_DB_PATH", "SUBLARR_API_KEY", "SUBLARR_LOG_LEVEL"):
        os.environ.pop(key, None)


class _DeadOllama(TranslationBackend):
    """Stands in for an Ollama host that stopped answering."""

    name = "ollama"
    display_name = "Dead Ollama"
    config_fields = []
    supports_glossary = False
    supports_batch = True

    def __init__(self, *_args, **_kwargs):
        self.calls = 0

    def translate_batch(self, lines, source_lang, target_lang, **kwargs):
        return TranslationResult(translated_lines=[], backend_name=self.name, success=False)

    def get_config_fields(self):
        return []

    def health_check(self):
        return False

    def _call_ollama(self, prompt):
        self.calls += 1
        raise ConnectionError("HTTPConnectionPool(host='192.168.178.155', port=11434)")


@pytest.fixture()
def manager_with_dead_backend():
    from translation import TranslationManager

    mgr = TranslationManager()
    backend = _DeadOllama()
    mgr._backends["ollama"] = backend
    return mgr, backend


def test_failed_evaluation_opens_the_breaker(manager_with_dead_backend):
    mgr, backend = manager_with_dead_backend
    cb = mgr._get_circuit_breaker("ollama")
    cb.failure_threshold = 3

    for _ in range(3):
        mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])

    assert backend.calls == 3, "the backend should have been tried once per evaluation"
    assert not cb.allow_request(), "three dead calls in a row left the breaker closed"


def test_open_breaker_stops_further_evaluation_calls(manager_with_dead_backend):
    """Once open, the quality pass must stop paying the timeout per line."""
    mgr, backend = manager_with_dead_backend
    cb = mgr._get_circuit_breaker("ollama")
    cb.failure_threshold = 2

    for _ in range(2):
        mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])
    calls_when_opened = backend.calls

    for _ in range(10):
        mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])

    assert backend.calls == calls_when_opened, (
        f"the open breaker was bypassed: {backend.calls - calls_when_opened} extra calls"
    )


def test_half_open_does_not_latch(manager_with_dead_backend):
    """A HALF_OPEN probe that fails must return to OPEN, not stay half-open."""
    from circuit_breaker import CircuitState

    mgr, _backend = manager_with_dead_backend
    cb = mgr._get_circuit_breaker("ollama")
    cb.failure_threshold = 1
    cb.cooldown_seconds = 0  # elapse immediately, so the next look is HALF_OPEN

    mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])
    assert cb.state == CircuitState.HALF_OPEN, "cooldown 0 should offer a probe"

    mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])
    # The probe failed, so the breaker must have re-opened rather than staying
    # in the state that lets everything through.
    assert cb._state == CircuitState.OPEN


def test_successful_evaluation_closes_the_breaker(manager_with_dead_backend):
    """A backend that answers again must be allowed back in."""
    from circuit_breaker import CircuitState

    mgr, backend = manager_with_dead_backend
    cb = mgr._get_circuit_breaker("ollama")
    cb.failure_threshold = 1
    cb.cooldown_seconds = 0

    mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])
    assert cb._state == CircuitState.OPEN

    backend._call_ollama = lambda prompt: "87"
    score = mgr.evaluate_line_quality("Good morning.", "Guten Morgen.", "en", "de", ["ollama"])

    assert score == 87
    assert cb._state == CircuitState.CLOSED
