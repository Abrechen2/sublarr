"""#201 (rest) — tell a rejected key apart from a host that is gone.

"Unhealthy" is not actionable. The reporting install had all three at once:
jimaku rejecting every request on an auth-scheme bug, podnapisi pointed at a
domain with no DNS record, and providers hitting rate limits — and the panel
showed one shape for all of them.
"""

import pytest

from providers.error_classification import classify_provider_error


class TestClassifyByType:
    def test_auth_error(self):
        from providers.base import ProviderAuthError

        assert classify_provider_error(ProviderAuthError("nope")) == "auth"

    def test_rate_limit(self):
        from providers.base import ProviderRateLimitError

        assert classify_provider_error(ProviderRateLimitError("slow down")) == "rate_limit"

    def test_timeout(self):
        from providers.base import ProviderTimeoutError

        assert classify_provider_error(ProviderTimeoutError("too slow")) == "timeout"

    def test_builtin_timeout_counts_too(self):
        assert classify_provider_error(TimeoutError()) == "timeout"


class TestClassifyByMessage:
    def test_the_podnapisi_shape(self):
        """The exact case from the field report: the domain stopped
        resolving, and requests wraps that in a ConnectionError whose class
        name says nothing at all."""
        exc = ConnectionError(
            "HTTPSConnectionPool(host='www.podnapisi.net', port=443): Max retries exceeded "
            "with url: /subtitles/search/old (Caused by NameResolutionError("
            "\"Failed to resolve 'www.podnapisi.net' ([Errno -2] Name or service not known)\"))"
        )
        assert classify_provider_error(exc) == "network"

    def test_a_wrapped_cause_is_found(self):
        inner = OSError("[Errno -2] Name or service not known")
        outer = RuntimeError("provider blew up")
        outer.__cause__ = inner
        assert classify_provider_error(outer) == "network"

    def test_a_401_in_the_text(self):
        assert classify_provider_error(RuntimeError("HTTP 401 Unauthorized")) == "auth"

    def test_anything_else_is_other(self):
        assert classify_provider_error(ValueError("weird")) == "other"

    def test_a_cycle_in_the_cause_chain_terminates(self):
        """Defensive: __context__ can loop, and a classifier that hangs is
        worse than one that guesses."""
        a = RuntimeError("a")
        b = RuntimeError("b")
        a.__context__ = b
        b.__context__ = a
        assert classify_provider_error(a) in ("other", "network", "auth", "timeout")


class TestHealthMapsTheKind:
    @pytest.mark.parametrize(
        ("kind", "reason"),
        [
            ("auth", "credentials_rejected"),
            ("network", "host_unreachable"),
        ],
    )
    def test_a_failing_provider_says_why(self, kind, reason):
        from providers.manager_status_mixin import _classify_health

        healthy, msg, got = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=4,
            total_searches=100,
            results=10,
            downloads=2,
            last_failure_kind=kind,
        )
        assert healthy is False
        assert got == reason
        assert msg

    def test_without_a_kind_it_stays_the_generic_reason(self):
        from providers.manager_status_mixin import _classify_health

        _healthy, _msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=4,
            total_searches=100,
            results=10,
            downloads=2,
            last_failure_kind=None,
        )
        assert reason == "consecutive_failures"

    def test_the_kind_does_not_invent_a_failure(self):
        """A stale last_failure_kind from weeks ago must not make a working
        provider look broken."""
        from providers.manager_status_mixin import _classify_health

        healthy, _msg, reason = _classify_health(
            auto_disabled=False,
            cb_state="closed",
            consecutive_failures=0,
            total_searches=100,
            results=40,
            downloads=9,
            last_failure_kind="network",
        )
        assert (healthy, reason) == (True, "ok")


class TestReasonsAreDeclared:
    @pytest.mark.parametrize("reason", ["credentials_rejected", "host_unreachable"])
    def test_declared_for_the_frontend(self, reason):
        from providers.manager_status_mixin import STATUS_REASONS

        assert reason in STATUS_REASONS


class TestItIsActuallyRecorded:
    """The classifier is inert unless the failure path feeds it and the row
    stores it — the same wiring gap that would have made #198 decoration."""

    def test_record_search_stores_the_kind(self, app_ctx):
        from db.models.providers import ProviderStats
        from db.providers import record_search
        from extensions import db

        p = "i201_store"
        row = db.session.get(ProviderStats, p)
        if row:
            db.session.delete(row)
            db.session.commit()
        try:
            record_search(p, success=False, response_time_ms=5.0, failure_kind="network")
            assert db.session.get(ProviderStats, p).last_failure_kind == "network"
            record_search(p, success=False, response_time_ms=5.0, failure_kind="auth")
            assert db.session.get(ProviderStats, p).last_failure_kind == "auth"
        finally:
            row = db.session.get(ProviderStats, p)
            if row:
                db.session.delete(row)
                db.session.commit()

    def test_a_success_does_not_wipe_the_last_known_cause(self, app_ctx):
        """The kind is only consulted while the provider is failing, so a
        recovery need not clear it — but it must not be overwritten with
        nonsense either."""
        from db.models.providers import ProviderStats
        from db.providers import record_search
        from extensions import db

        p = "i201_success"
        row = db.session.get(ProviderStats, p)
        if row:
            db.session.delete(row)
            db.session.commit()
        try:
            record_search(p, success=False, response_time_ms=5.0, failure_kind="auth")
            record_search(p, success=True, response_time_ms=5.0, had_results=True)
            assert db.session.get(ProviderStats, p).last_failure_kind == "auth"
        finally:
            row = db.session.get(ProviderStats, p)
            if row:
                db.session.delete(row)
                db.session.commit()

    def test_the_coordinator_classifies_what_it_caught(self, app_ctx, monkeypatch):
        from unittest.mock import MagicMock

        from providers.base import ProviderAuthError
        from services.provider_budget import BudgetDecision, ProviderBudgetManager
        from tests.test_search_coordinator_budget import (
            _build_manager,
            _make_provider,
            _make_query,
        )

        provider = _make_provider("i201_wiring")
        provider.search.side_effect = ProviderAuthError("401 Unauthorized")
        manager = _build_manager(monkeypatch, provider)

        budget = MagicMock(spec=ProviderBudgetManager)
        budget.check.return_value = BudgetDecision(allow=True)
        monkeypatch.setattr("providers.search_coordinator.get_budget_manager", lambda: budget)
        ks = MagicMock()
        ks.pick.return_value = {"id": 1, "api_key": "x", "username": None, "password": None}
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks)

        calls = []
        monkeypatch.setattr("db.providers.update_provider_stats", lambda *a, **kw: calls.append(kw))
        manager.search(_make_query())
        assert provider.search.called
        assert calls, "the failure path never recorded anything"
        assert calls[0]["failure_kind"] == "auth"
