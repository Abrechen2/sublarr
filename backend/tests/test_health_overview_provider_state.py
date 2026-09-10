"""The health page must not keep a third definition of "provider is fine".

Forgejo #17: on one install `/api/v1/health` reported "degraded (23/29
active)", `/api/v1/providers` listed 6 unhealthy, and the health page showed
"PROVIDERS DEGRADED 0" next to "No provider activity recorded yet". All three
numbers were correct — they answered different questions under nearly the
same name.

The health overview computed degraded itself: breaker not closed, or
auto-disabled, or at least 10 searches with under 5% hits. It therefore
missed a provider failing call after call (consecutive failures), which the
classifier behind /api/v1/providers has flagged since 1.14.0. And a provider
that has never been asked anything came out identical to a healthy one, so
"nothing has run yet" was indistinguishable from "everything is fine".

So: one classifier for both surfaces, and activity reported separately from
health.
"""

from datetime import UTC, datetime


def _add_provider_stats(app, name, **columns):
    from db.models.providers import ProviderStats
    from extensions import db

    with app.app_context():
        db.session.add(ProviderStats(provider_name=name, updated_at=datetime.now(UTC), **columns))
        db.session.commit()


def _providers(client):
    resp = client.get("/api/v1/health/library")
    assert resp.status_code == 200
    body = resp.get_json()
    return {p["provider"]: p for p in body["providers"]}, body["totals"]


def test_a_provider_failing_call_after_call_counts_as_degraded(client):
    """The gap the old rule left: failures without an open breaker.

    Nine searches, none successful, nine consecutive failures — under the old
    rule that is neither breaker-open nor auto-disabled nor "10+ searches", so
    it read as healthy on the very page meant to surface it.
    """
    _add_provider_stats(
        client.application,
        "failingprov",
        total_searches=9,
        successful_searches=0,
        consecutive_failures=9,
    )
    providers, _ = _providers(client)
    assert providers["failingprov"]["degraded"] is True
    assert providers["failingprov"]["status_reason"] == "consecutive_failures"


def test_a_provider_nobody_has_asked_is_not_called_degraded(client):
    """Never asked is not the same as broken — but it must be visible."""
    _add_provider_stats(client.application, "freshprov", total_searches=0, successful_searches=0)
    providers, totals = _providers(client)

    assert providers["freshprov"]["degraded"] is False
    assert providers["freshprov"]["status_reason"] == "no_activity"
    assert totals["providers_no_activity"] >= 1


def test_the_established_verdicts_still_hold(client):
    """The rules that already worked keep working."""
    app = client.application
    _add_provider_stats(app, "goodprov", total_searches=100, successful_searches=60)
    _add_provider_stats(app, "deadprov", total_searches=50, successful_searches=1)
    _add_provider_stats(app, "offprov", total_searches=5, successful_searches=5, auto_disabled=1)

    providers, _ = _providers(client)
    assert providers["goodprov"]["degraded"] is False
    assert providers["deadprov"]["degraded"] is True
    assert providers["deadprov"]["status_reason"] == "low_hit_rate"
    assert providers["offprov"]["degraded"] is True
    assert providers["offprov"]["status_reason"] == "auto_disabled"


def test_totals_separate_health_from_activity(client):
    """The two numbers the report saw side by side must be distinguishable."""
    app = client.application
    _add_provider_stats(app, "busy_ok", total_searches=80, successful_searches=40)
    _add_provider_stats(app, "never_asked", total_searches=0, successful_searches=0)
    _add_provider_stats(
        app, "broken", total_searches=4, successful_searches=0, consecutive_failures=5
    )

    _, totals = _providers(client)
    assert totals["providers_degraded"] == 1
    assert totals["providers_no_activity"] == 1
