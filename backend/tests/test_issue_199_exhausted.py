"""#199 — an item that has given up must be distinguishable from one still trying.

Exhausted items keep status "wanted" and sit under the same badge as items
being actively retried. On the reporting install 869 of 1,299 wanted items
(67%) had exhausted their attempts, and the queue looked like a healthy
backlog rather than a stalled one. The scheduler reads the same way: a
wanted_search that completes in 222ms and reports ok is indistinguishable
from one that had nothing to do.

The predicate here is the SAME one the search filter uses. Defining
"exhausted" separately from the code that decides eligibility is how the two
drift, and then the number on the dashboard stops describing the behaviour.
"""

from services.wanted_search_filters import is_exhausted


class TestIsExhausted:
    def test_below_the_cap_is_still_trying(self):
        assert (
            is_exhausted(search_count=2, failure_kind=None, retry_after=None, max_attempts=3)
            is False
        )

    def test_at_the_cap_without_a_marker_has_given_up(self):
        assert (
            is_exhausted(search_count=3, failure_kind=None, retry_after=None, max_attempts=3)
            is True
        )

    def test_over_the_cap_counts_too(self):
        assert (
            is_exhausted(search_count=9, failure_kind=None, retry_after=None, max_attempts=3)
            is True
        )

    def test_slow_mode_with_a_window_is_not_exhausted(self):
        """The intentional bypass: at the cap, but marked for periodic
        retries roughly once a month. Those items have not given up."""
        assert (
            is_exhausted(
                search_count=3,
                failure_kind="no_result_slow",
                retry_after="2026-09-20T00:00:00+00:00",
                max_attempts=3,
            )
            is False
        )

    def test_the_marker_alone_does_not_save_it(self):
        """Without a retry window the cap stands — this is the legacy-frozen
        shape the 2026-05-06 migration had to go back and rescue."""
        assert (
            is_exhausted(
                search_count=3, failure_kind="no_result_slow", retry_after=None, max_attempts=3
            )
            is True
        )

    def test_a_window_without_the_marker_does_not_save_it_either(self):
        assert (
            is_exhausted(
                search_count=3,
                failure_kind=None,
                retry_after="2026-09-20T00:00:00+00:00",
                max_attempts=3,
            )
            is True
        )


class TestTheFilterUsesTheSameRule:
    """If the dashboard count and the search filter disagree, the number is
    decoration. These pin them to one another."""

    def _settings(self, max_attempts=3):
        class S:
            wanted_max_search_attempts = max_attempts
            wanted_adaptive_backoff_enabled = True

        return S()

    def _item(self, **kw):
        base = {
            "id": 1,
            "search_count": 0,
            "failure_kind": None,
            "retry_after": None,
            "last_search_at": None,
        }
        base.update(kw)
        return base

    def test_every_ineligible_capped_item_reads_as_exhausted(self):
        from services.wanted_search_filters import _filter_eligible

        settings = self._settings()
        items = [
            self._item(id=1, search_count=0),
            self._item(id=2, search_count=3),
            self._item(
                id=3,
                search_count=3,
                failure_kind="no_result_slow",
                retry_after="2020-01-01T00:00:00+00:00",
            ),
            self._item(id=4, search_count=5, failure_kind="no_result_slow"),
        ]
        eligible_ids = {i["id"] for i in _filter_eligible(items, settings)}

        for item in items:
            exhausted = is_exhausted(
                search_count=item["search_count"],
                failure_kind=item["failure_kind"],
                retry_after=item["retry_after"],
                max_attempts=3,
            )
            if exhausted:
                assert item["id"] not in eligible_ids, (
                    f"item {item['id']} reads as exhausted but the filter would still search it"
                )


class TestSummaryReportsTheCount:
    """The number has to reach the surface, and it has to agree with the
    filter — a count that disagrees with the behaviour is worse than none."""

    def test_summary_exposes_exhausted(self, app_ctx):
        from db.wanted import get_wanted_summary

        summary = get_wanted_summary()
        assert "exhausted" in summary
        assert isinstance(summary["exhausted"], int)
        assert summary["exhausted"] >= 0

    def test_exhausted_never_exceeds_the_wanted_total(self, app_ctx):
        from db.wanted import get_wanted_summary

        summary = get_wanted_summary()
        wanted = summary["by_status"].get("wanted", 0)
        assert summary["exhausted"] <= wanted

    def test_the_count_is_actually_computed(self, app_ctx):
        """Seeded, because an empty database makes any counting query look
        correct — including one that filters on the wrong column."""
        from datetime import UTC, datetime, timedelta

        from db.models.core import WantedItem
        from db.wanted import get_wanted_summary
        from extensions import db

        now = datetime.now(UTC)
        soon = now + timedelta(days=20)
        seeded = [
            # still trying
            WantedItem(
                item_type="episode",
                added_at=now,
                updated_at=now,
                title="a",
                file_path="/a.mkv",
                status="wanted",
                search_count=1,
            ),
            # given up: at the cap, no marker
            WantedItem(
                item_type="episode",
                added_at=now,
                updated_at=now,
                title="b",
                file_path="/b.mkv",
                status="wanted",
                search_count=3,
            ),
            # given up: marker but no window (the legacy-frozen shape)
            WantedItem(
                item_type="episode",
                added_at=now,
                updated_at=now,
                title="c",
                file_path="/c.mkv",
                status="wanted",
                search_count=4,
                failure_kind="no_result_slow",
            ),
            # still trying: slow-mode with a window
            WantedItem(
                item_type="episode",
                added_at=now,
                updated_at=now,
                title="d",
                file_path="/d.mkv",
                status="wanted",
                search_count=3,
                failure_kind="no_result_slow",
                retry_after=soon,
            ),
            # not wanted at all — must not be counted
            WantedItem(
                item_type="episode",
                added_at=now,
                updated_at=now,
                title="e",
                file_path="/e.mkv",
                status="extracted",
                search_count=9,
            ),
        ]
        before = get_wanted_summary()["exhausted"]
        db.session.add_all(seeded)
        db.session.commit()
        try:
            assert get_wanted_summary()["exhausted"] == before + 2
        finally:
            for row in seeded:
                db.session.delete(row)
            db.session.commit()
