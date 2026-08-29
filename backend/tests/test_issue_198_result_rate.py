"""#198 — provider health must reflect whether searches produced results.

`successful_searches` was always meant to be the numerator of `result_rate`
(its own migration, 2026_05_08_2100, says so). The search coordinator fed it
`success=True` whenever the provider call merely returned, so a provider whose
upstream domain no longer resolves in DNS reported a 100% result rate over
1,666 searches and zero downloads.

The parameter cannot simply be re-pointed at ``len(results) > 0``: the same
flag also drives ``consecutive_failures``, which drives auto-disable. Reusing
it would auto-disable a perfectly healthy provider that legitimately found
nothing — the exact failure class we already have a rule against. So the two
axes are recorded separately.
"""

from db.models.providers import ProviderStats
from extensions import db


def _reset(provider: str) -> None:
    row = db.session.get(ProviderStats, provider)
    if row is not None:
        db.session.delete(row)
        db.session.commit()


class TestAnsweredButEmptyIsNotAResult:
    def test_empty_answer_does_not_count_as_a_result(self, app_ctx):
        from db.providers import record_search

        p = "i198_empty"
        _reset(p)
        try:
            record_search(p, success=True, response_time_ms=10.0, had_results=False)
            record_search(p, success=True, response_time_ms=10.0, had_results=False)
            row = db.session.get(ProviderStats, p)
            assert row.total_searches == 2
            assert (row.successful_searches or 0) == 0, (
                "a provider that answered but found nothing has produced no result"
            )
        finally:
            _reset(p)

    def test_empty_answer_is_not_a_failure_either(self, app_ctx):
        """The half that must NOT change: answering is success for the
        reliability axis. Counting an empty answer as a failure would raise
        consecutive_failures and auto-disable a healthy provider."""
        from db.providers import record_search

        p = "i198_empty_not_failure"
        _reset(p)
        try:
            for _ in range(6):
                record_search(p, success=True, response_time_ms=10.0, had_results=False)
            row = db.session.get(ProviderStats, p)
            assert (row.consecutive_failures or 0) == 0
            assert (row.failed_downloads or 0) == 0
            assert row.last_failure_at is None
            assert row.last_search_at is not None
        finally:
            _reset(p)

    def test_a_hit_counts(self, app_ctx):
        from db.providers import record_search

        p = "i198_hit"
        _reset(p)
        try:
            record_search(p, success=True, response_time_ms=10.0, had_results=True)
            record_search(p, success=True, response_time_ms=10.0, had_results=False)
            row = db.session.get(ProviderStats, p)
            assert row.total_searches == 2
            assert row.successful_searches == 1
        finally:
            _reset(p)

    def test_a_real_failure_still_counts_as_one(self, app_ctx):
        from db.providers import record_search

        p = "i198_failure"
        _reset(p)
        try:
            record_search(p, success=False, response_time_ms=10.0)
            record_search(p, success=False, response_time_ms=10.0)
            row = db.session.get(ProviderStats, p)
            assert row.consecutive_failures == 2
            assert row.failed_downloads == 2
            assert row.last_failure_at is not None
        finally:
            _reset(p)

    def test_omitting_had_results_keeps_the_old_meaning(self, app_ctx):
        """Callers that cannot tell must not silently zero the counter."""
        from db.providers import record_search

        p = "i198_backcompat"
        _reset(p)
        try:
            record_search(p, success=True, response_time_ms=10.0)
            row = db.session.get(ProviderStats, p)
            assert row.successful_searches == 1
        finally:
            _reset(p)


class TestCoordinatorPassesTheSecondAxis:
    """The repository change is inert unless the search path actually feeds it.

    This is the wiring the whole issue turns on: everything else can be
    correct and `result_rate` still lies if the coordinator keeps reporting
    every answered call as a result.
    """

    def _run(self, monkeypatch, results):
        from unittest.mock import MagicMock

        from services.provider_budget import BudgetDecision, ProviderBudgetManager
        from tests.test_search_coordinator_budget import (
            _build_manager,
            _make_provider,
            _make_query,
            _make_result,
        )

        provider = _make_provider("i198_wiring")
        provider.search.return_value = [_make_result("i198_wiring")] * results
        manager = _build_manager(monkeypatch, provider)

        # The budget gate and the key selector sit in front of the search; a
        # provider that never runs records no statistics at all.
        budget = MagicMock(spec=ProviderBudgetManager)
        budget.check.return_value = BudgetDecision(allow=True)
        monkeypatch.setattr("providers.search_coordinator.get_budget_manager", lambda: budget)
        ks = MagicMock()
        ks.pick.return_value = {"id": 1, "api_key": "x", "username": None, "password": None}
        monkeypatch.setattr("providers.search_coordinator.get_key_selector", lambda: ks)

        # The coordinator imports this inside search() and passes it down as a
        # parameter, so the patch has to land on the source module — and after
        # _build_manager, which stubs the same name to a no-op.
        calls = []
        monkeypatch.setattr(
            "db.providers.update_provider_stats",
            lambda *a, **kw: calls.append(kw),
        )
        manager.search(_make_query())
        assert provider.search.called, "the provider was skipped before it ever searched"
        return calls

    def test_a_search_that_found_nothing_reports_had_results_false(self, app_ctx, monkeypatch):
        calls = self._run(monkeypatch, results=0)
        assert calls, "update_provider_stats was never called"
        assert calls[0]["success"] is True, "answering is still a success for reliability"
        assert calls[0]["had_results"] is False

    def test_a_search_that_found_something_reports_had_results_true(self, app_ctx, monkeypatch):
        calls = self._run(monkeypatch, results=2)
        assert calls
        assert calls[0]["had_results"] is True


class TestResultRateReflectsHits:
    def test_dead_provider_reads_zero_not_one(self, app_ctx):
        """The podnapisi shape: answers every time, finds nothing, ever."""
        from db.providers import get_all_provider_stats_enriched, record_search

        p = "i198_dead_host"
        _reset(p)
        try:
            for _ in range(10):
                record_search(p, success=True, response_time_ms=5.0, had_results=False)
            stats = get_all_provider_stats_enriched()[p]
            assert stats["result_rate"] == 0.0
            assert stats["total_searches"] == 10
        finally:
            _reset(p)

    def test_working_provider_reads_its_real_hit_rate(self, app_ctx):
        from db.providers import get_all_provider_stats_enriched, record_search

        p = "i198_working"
        _reset(p)
        try:
            for i in range(10):
                record_search(p, success=True, response_time_ms=5.0, had_results=(i < 4))
            stats = get_all_provider_stats_enriched()[p]
            assert stats["result_rate"] == 0.4
        finally:
            _reset(p)


class TestHealthVerdictUsesTheEvidence:
    """A provider that answers, never finds anything and never downloads is
    not healthy — however politely it answers.

    This is the visible half of #198. The reporter's cleanest case: both
    podnapisi providers reported healthy:true with a 100% success rate while
    their upstream domain had no DNS record at all.
    """

    def test_dead_provider_is_not_reported_healthy(self, app_ctx, monkeypatch):
        from providers.manager_status_mixin import _looks_dead

        assert _looks_dead(total_searches=1666, results=0, downloads=0) is True

    def test_a_provider_that_ever_delivered_is_left_alone(self, app_ctx):
        from providers.manager_status_mixin import _looks_dead

        assert _looks_dead(total_searches=1666, results=0, downloads=3) is False
        assert _looks_dead(total_searches=1666, results=12, downloads=0) is False

    def test_a_young_provider_is_not_accused(self, app_ctx):
        """Below the threshold "found nothing yet" is normal, not a verdict."""
        from providers.manager_status_mixin import _looks_dead

        assert _looks_dead(total_searches=5, results=0, downloads=0) is False


class TestCounterResetMigration:
    """The write-path fix is inert on an existing install without this.

    Every provider carries a historical successful_searches counted under the
    old meaning; result_rate keeps mixing two definitions, and _looks_dead
    never fires because results > 0 clears it immediately.
    """

    def test_counters_are_zeroed_and_the_baseline_is_kept(self, app_ctx):
        import sqlalchemy as sa

        from db.migrations.versions.i198_reset_provider_search_counters import (
            BASELINE_TABLE,
            reset_search_counters,
        )
        from db.providers import record_search

        p = "i198_migration"
        _reset(p)
        try:
            for _ in range(7):
                record_search(p, success=True, response_time_ms=1.0, had_results=True)
            row = db.session.get(ProviderStats, p)
            assert row.successful_searches == 7

            conn = db.session.connection()
            reset_search_counters(conn)

            db.session.expire_all()
            row = db.session.get(ProviderStats, p)
            assert row.total_searches == 0
            assert row.successful_searches == 0

            kept = conn.execute(
                sa.text(
                    f"SELECT successful_searches FROM {BASELINE_TABLE} WHERE provider_name = :p"
                ),
                {"p": p},
            ).scalar()
            assert kept == 7, "the pre-reset value must remain provable"
        finally:
            db.session.rollback()
            _reset(p)

    def test_current_state_columns_are_left_alone(self, app_ctx):
        """Clearing auto-disable state would re-enable providers that are
        switched off for a reason."""
        from db.migrations.versions.i198_reset_provider_search_counters import (
            reset_search_counters,
        )
        from db.providers import record_search

        p = "i198_migration_state"
        _reset(p)
        try:
            for _ in range(4):
                record_search(p, success=False, response_time_ms=1.0)
            before = db.session.get(ProviderStats, p)
            failures, last_failure = before.consecutive_failures, before.last_failure_at

            reset_search_counters(db.session.connection())
            db.session.expire_all()

            after = db.session.get(ProviderStats, p)
            assert after.consecutive_failures == failures
            assert after.last_failure_at == last_failure
        finally:
            db.session.rollback()
            _reset(p)
