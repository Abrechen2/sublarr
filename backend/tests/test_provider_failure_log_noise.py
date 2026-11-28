"""A provider's own HTTP failure is a warning line, not a traceback (Forgejo #83).

isubtitles answering HTTP 520 for a day logged a full traceback per search on
prod (12 in 24h) although nothing in Sublarr was wrong. Unexpected exceptions
still carry the traceback: they point at our code.
"""

import logging

import pytest

from providers.base import ProviderError, VideoQuery
from providers.search_coordinator.retry import SearchRetryMixin


class _Coordinator(SearchRetryMixin):
    def __init__(self):
        self._circuit_breakers = {}
        self._server_rate_limit_until = {}

    def _get_retries(self, name):
        return 0


class _Provider:
    session = object()

    def __init__(self, exc):
        self._exc = exc

    def search(self, query):
        raise self._exc


def _final_record(caplog, exc):
    caplog.set_level(logging.WARNING, logger="providers.search_coordinator.retry")
    with pytest.raises(type(exc)):
        _Coordinator()._do_search_provider_with_retry(
            "isubtitles", _Provider(exc), VideoQuery(title="X", languages=["en"])
        )
    return next(r for r in caplog.records if "failed after" in r.getMessage())


def test_provider_error_is_logged_without_a_traceback(caplog):
    record = _final_record(caplog, ProviderError("HTTP Error 520: <none>"))

    assert record.levelno == logging.WARNING
    assert "HTTP Error 520" in record.getMessage()
    assert not record.exc_info


def test_unexpected_error_keeps_the_traceback(caplog):
    record = _final_record(caplog, KeyError("title"))

    assert record.exc_info
