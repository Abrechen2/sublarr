"""Alerting on a provider that has quietly stopped working (#186).

Sublarr already had circuit breakers and notification channels and no bridge
between them, so a provider could fail permanently — expired credentials, a
dead key, a gate misconfiguration — and the only symptom was a wanted queue
that stopped moving. On the install that prompted this, the primary provider
was dead for three days; the signature ("searches fine, downloads zero") was
sitting in provider_stats the whole time and nothing pushed it.

The hard part is not detecting it, it is not crying wolf. Most providers on a
healthy install legitimately never download — they lose the scoring race — so
"no downloads" alone is noise. The condition has to be a provider that was
searching successfully AND had downloads before.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.models.providers import ProviderStats
from extensions import db
from services.provider_degradation import check_provider_degradation

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _stats(name, **kwargs):
    defaults = dict(
        provider_name=name,
        total_searches=100,
        successful_searches=90,
        successful_downloads=40,
        failed_downloads=0,
        last_search_at=NOW - timedelta(minutes=5),
        last_download_at=NOW - timedelta(minutes=30),
        consecutive_failures=0,
        updated_at=NOW,
    )
    defaults.update(kwargs)
    row = ProviderStats(**defaults)
    db.session.add(row)
    db.session.commit()
    return row


@pytest.fixture(autouse=True)
def _forget_alerts():
    from services import provider_degradation

    provider_degradation._alerted.clear()
    yield
    provider_degradation._alerted.clear()


def test_a_working_provider_raises_nothing(app_ctx):
    _stats("gestdown")

    assert check_provider_degradation(now=NOW) == []


def test_searches_fine_downloads_dead_is_reported(app_ctx):
    """The signature of the three-day outage."""
    _stats("opensubtitles", last_download_at=NOW - timedelta(days=3))

    alerts = check_provider_degradation(now=NOW)

    assert [a["provider_name"] for a in alerts] == ["opensubtitles"]
    assert alerts[0]["condition"] == "downloads_stopped"


def test_a_provider_that_never_downloaded_is_not_accused(app_ctx):
    """Most providers lose the scoring race and never download at all.

    Alerting on them would bury the one provider that genuinely broke — the
    failure mode that makes an alerting feature worse than none.
    """
    _stats("podnapisi", successful_downloads=0, last_download_at=None)

    assert check_provider_degradation(now=NOW) == []


def test_a_provider_that_is_not_searching_either_is_not_a_download_problem(app_ctx):
    """Nothing is running through it at all — that is a different fault, and
    naming it a download failure sends the operator to the wrong place."""
    _stats(
        "subdl", last_search_at=NOW - timedelta(days=5), last_download_at=NOW - timedelta(days=5)
    )

    assert check_provider_degradation(now=NOW) == []


def test_an_auto_disabled_provider_is_reported(app_ctx):
    _stats("jimaku", auto_disabled=1, disabled_until=NOW + timedelta(hours=1))

    alerts = check_provider_degradation(now=NOW)

    assert [(a["provider_name"], a["condition"]) for a in alerts] == [("jimaku", "auto_disabled")]


def test_an_expired_auto_disable_is_healed_not_reported(app_ctx):
    """The raw flag can outlive its cooldown for months.

    ``is_auto_disabled`` clears an expired flag, but only search paths called
    it — a provider that never gets searched (filtered out earlier) kept its
    stale flag forever, and this check alerted on it daily. Prod exhibit:
    jimaku, auto_disabled with disabled_until 2026-04-15, still alerting on
    2026-08-27. The nightly check must use the expiry-aware read, which also
    turns it into the healer for exactly these unreachable rows.
    """
    row = _stats("jimaku", auto_disabled=1, disabled_until=NOW - timedelta(hours=1))

    alerts = check_provider_degradation(now=NOW)

    assert alerts == []
    db.session.refresh(row)
    assert row.auto_disabled == 0
    assert row.disabled_until is None


def test_the_same_condition_is_reported_once_a_day(app_ctx):
    """The point is the first ping, not a stream. An alert that repeats every
    tick trains people to filter the channel."""
    row = _stats("opensubtitles", last_download_at=NOW - timedelta(days=3))

    first = check_provider_degradation(now=NOW)
    again = check_provider_degradation(now=NOW + timedelta(hours=3))

    # A provider that is still being used keeps searching, so its search
    # timestamp moves with it. Leaving it frozen would fail the "is anything
    # even reaching this provider" guard and silence the alert for the wrong
    # reason — which is precisely what the first version of this test did.
    later = NOW + timedelta(days=1, hours=1)
    row.last_search_at = later - timedelta(minutes=5)
    db.session.commit()

    next_day = check_provider_degradation(now=later)

    assert len(first) == 1
    assert again == [], "the same condition must not re-alert within the day"
    assert len(next_day) == 1, "a condition that is still true must be re-raised the next day"


def test_two_conditions_on_one_provider_are_separate_alerts(app_ctx):
    """Suppressing one because the other fired would hide a real change."""
    _stats("jimaku", auto_disabled=1, last_download_at=NOW - timedelta(days=3))

    conditions = {a["condition"] for a in check_provider_degradation(now=NOW)}

    assert conditions == {"auto_disabled", "downloads_stopped"}


def test_nothing_is_pushed_unless_the_operator_asked(app_ctx, monkeypatch):
    """Detection always runs and always logs; only the push is opt-in."""
    from unittest.mock import patch

    _stats("opensubtitles", last_download_at=NOW - timedelta(days=3))

    with patch("events.emit_event") as emitted:
        alerts = check_provider_degradation(now=NOW)

    assert len(alerts) == 1, "the finding must still be made and returned"
    assert emitted.call_count == 0


def test_the_event_is_emitted_once_enabled(app_ctx, monkeypatch):
    from unittest.mock import patch

    from services import provider_degradation

    _stats("opensubtitles", last_download_at=NOW - timedelta(days=3))
    monkeypatch.setattr(provider_degradation, "_alerts_enabled", lambda: True)

    with patch("events.emit_event") as emitted:
        check_provider_degradation(now=NOW)

    assert emitted.call_count == 1
    assert emitted.call_args[0][0] == "provider_degraded"
    assert emitted.call_args[0][1]["condition"] == "downloads_stopped"
