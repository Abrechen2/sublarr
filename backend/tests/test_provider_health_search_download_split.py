"""A provider whose searches work while its downloads are dead (#185).

The failure this makes visible: OpenSubtitles' download token expires after 24
hours while search keeps working on the API key alone. For three days on a real
install, searches succeeded, every download 401'd, and nothing anywhere showed
a problem — `provider_stats.successful_downloads` sat at 0 while the success
rate stayed green, because both paths stamped the same `last_success_at`.

Separate timestamps are what make "last search 4 minutes ago, last download
three days ago" a sentence the operator can read.
"""

from datetime import UTC, datetime, timedelta

import pytest

from db.models.providers import ProviderStats
from db.repositories.providers import ProviderRepository
from extensions import db


@pytest.fixture
def repo(app_ctx):
    return ProviderRepository()


def _stats(name: str) -> ProviderStats:
    return db.session.get(ProviderStats, name)


def test_a_search_does_not_look_like_a_download(repo):
    repo.record_search("opensubtitles", success=True, response_time_ms=120)

    row = _stats("opensubtitles")
    assert row.last_search_at is not None
    assert row.last_download_at is None, (
        "a successful search must not imply the download path works — that "
        "conflation is what hid a three-day outage"
    )


def test_a_download_stamps_its_own_time(repo):
    repo.record_search("opensubtitles", success=True)
    repo.record_download("opensubtitles", score=90)

    row = _stats("opensubtitles")
    assert row.last_search_at is not None
    assert row.last_download_at is not None


def test_a_download_by_a_provider_with_no_prior_search_is_recorded(repo):
    """`record_download` also creates the row when it is the first call."""
    repo.record_download("gestdown", score=50)

    row = _stats("gestdown")
    assert row.last_download_at is not None
    assert row.last_search_at is None


def test_health_reports_both_timestamps(app_ctx, repo):
    """The endpoint is the whole point — the columns alone help nobody."""
    from routes.providers.search import provider_health

    repo.record_search("opensubtitles", success=True)
    repo.record_download("opensubtitles", score=90)
    repo.record_search("podnapisi", success=True)

    with app_ctx.test_request_context():
        payload = provider_health().get_json()

    by_name = {p["name"]: p for p in payload["providers"]}
    assert by_name["opensubtitles"]["last_search_at"]
    assert by_name["opensubtitles"]["last_download_at"]
    assert by_name["podnapisi"]["last_search_at"]
    assert by_name["podnapisi"]["last_download_at"] is None, (
        "searches fine, downloads never — the signature that must be visible"
    )


def test_an_old_download_next_to_a_fresh_search_is_still_reported(repo):
    """The real shape of the outage: both fields set, days apart."""
    now = datetime.now(UTC)
    repo.record_search("opensubtitles", success=True)
    repo.record_download("opensubtitles", score=90)

    row = _stats("opensubtitles")
    row.last_download_at = now - timedelta(days=3)
    db.session.commit()

    row = _stats("opensubtitles")
    assert (row.last_search_at - row.last_download_at) > timedelta(days=2)
