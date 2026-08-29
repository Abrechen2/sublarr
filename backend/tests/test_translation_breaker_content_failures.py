"""The translation health breaker must not open on content-shape failures.

A ``LineCountMismatchError`` proves the backend is *up* — it answered twice
(initial attempt plus strict retry) within the request timeout. Only the shape
of the answer was wrong, and that is a property of the one batch, not of the
backend's health.

Counting such a failure against the circuit breaker turns a per-item defect
into a fleet-wide outage: on prod, five wanted items reproduced a line-count
mismatch every day, which is exactly ``circuit_breaker_failure_threshold``.
The breaker opened and — with a single-element fallback chain — every other
translation job then failed with "No usable translation backend".
"""

import os

import pytest

from config import reload_settings
from db import close_db, init_db
from translation.base import TranslationBackend, TranslationResult
from translation.llm_base import (
    ContentFilterError,
    LineCountMismatchError,
    LineMisalignmentError,
)


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path):
    from app import create_app

    os.environ["SUBLARR_DB_PATH"] = str(tmp_path / "test_breaker.db")
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


@pytest.fixture()
def manager():
    from translation import TranslationManager

    return TranslationManager()


class _RaisingBackend(TranslationBackend):
    """Backend that always raises the exception configured on the subclass."""

    name = "raiser"
    display_name = "Raiser"
    config_fields = []
    supports_glossary = False
    supports_batch = True
    max_batch_size = 0
    exc: Exception = RuntimeError("boom")

    def translate_batch(
        self,
        lines,
        source_lang,
        target_lang,
        glossary_entries=None,
        series_context=None,
        *,
        lookback=None,
        lookahead=None,
    ):
        raise type(self).exc

    def health_check(self):
        return (True, "up")

    def get_config_fields(self):
        return self.config_fields


class _LineCountBackend(_RaisingBackend):
    name = "line_count"
    exc = LineCountMismatchError("line_count returned 13 lines after retry, expected 15")


class _ContentFilterBackend(_RaisingBackend):
    name = "content_filter"
    exc = ContentFilterError("content_filter refused with finish_reason=content_filter")


class _MisalignedBackend(_RaisingBackend):
    name = "misaligned"
    exc = LineMisalignmentError("misaligned returned lines shifted by +1 after retry")


class _UnreachableBackend(_RaisingBackend):
    name = "unreachable"
    exc = ConnectionError("connection refused")


def _drive_failures(manager, backend_cls) -> None:
    """Fail one more batch than the breaker threshold."""
    manager.register_backend(backend_cls)
    cb = manager._get_circuit_breaker(backend_cls.name)
    for _ in range(cb.failure_threshold + 1):
        result = manager.translate_with_fallback(
            ["Hi"], "en", "de", fallback_chain=[backend_cls.name]
        )
        assert result.success is False


def test_line_count_mismatch_does_not_open_the_breaker(manager):
    _drive_failures(manager, _LineCountBackend)

    cb = manager._get_circuit_breaker(_LineCountBackend.name)
    assert cb.is_open is False, "a wrong-shaped answer is not a sick backend"


def test_content_filter_refusal_does_not_open_the_breaker(manager):
    _drive_failures(manager, _ContentFilterBackend)

    cb = manager._get_circuit_breaker(_ContentFilterBackend.name)
    assert cb.is_open is False, "a refusal is about the content, not the backend"


def test_misaligned_lines_do_not_open_the_breaker(manager):
    """Same reasoning, newer check — the backend answered, twice."""
    _drive_failures(manager, _MisalignedBackend)

    cb = manager._get_circuit_breaker(_MisalignedBackend.name)
    assert cb.is_open is False, "lines against the wrong sources is a content defect"


def test_poison_batches_do_not_stall_unrelated_translations(manager):
    """The outage itself: healthy work must survive a run of poison batches."""
    _drive_failures(manager, _LineCountBackend)

    result = manager.translate_with_fallback(
        ["Hi"], "en", "de", fallback_chain=[_LineCountBackend.name]
    )
    assert "No usable translation backend" not in (result.error or "")


def test_unreachable_backend_still_opens_the_breaker(manager):
    """Guard against over-fixing — real outages must still trip the breaker."""
    _drive_failures(manager, _UnreachableBackend)

    cb = manager._get_circuit_breaker(_UnreachableBackend.name)
    assert cb.is_open is True
