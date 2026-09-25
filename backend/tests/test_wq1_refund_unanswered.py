"""wq1_refund_unanswered gives back search attempts nobody answered.

Two writers charged ``search_count`` without a provider being asked (both
closed in the same release, see the migration docstring):
- a search in which every provider was skipped as rate-limited, over budget or
  auto-disabled was booked ``no_result``;
- ``_check_max_search_attempts`` booked another ``no_result`` for every
  slow-mode item that came due, without searching.

Prod 2026-09-25: 3 229 of 3 601 slow-mode items had an unanswered last search,
105 of the 107 at ``search_count=4`` had been bumped by the gate. Tested through
``create_app`` on an untracked database, the path that never runs Alembic.
"""

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

_LONG_AGO = datetime(2026, 9, 1, tzinfo=UTC)
_LATER = datetime.now(UTC) + timedelta(days=20)


def _log(*providers, cache_hit=False):
    return json.dumps(
        {
            "version": 1,
            "started_at": _LONG_AGO.isoformat(),
            "searches": [
                {"step": "target_ass_direct", "cache_hit": cache_hit, "providers": list(providers)}
            ],
            "final": {"status": "not_found"},
        }
    )


_UNANSWERED = _log(
    {"name": "opensubtitles", "status": "skipped", "reason": "rate_limited"},
    {"name": "subdl", "status": "skipped", "reason": "budget_exhausted"},
    {"name": "napisy24", "status": "skipped", "reason": "language_unsupported"},
)
_ANSWERED = _log(
    {"name": "opensubtitles", "status": "skipped", "reason": "rate_limited"},
    {"name": "subdl", "status": "ok", "hits": 0, "elapsed_ms": 80},
)
_ONLY_PERMANENT = _log({"name": "napisy24", "status": "skipped", "reason": "language_unsupported"})


def _start():
    from app import create_app

    return create_app(testing=True)


def _seed(path, *, count, kind="no_result_slow", log=None, retry_after=_LATER):
    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    row = WantedItem(
        item_type="episode",
        file_path=path,
        title="t",
        existing_sub="",
        missing_languages='["de"]',
        embedded_languages="[]",
        target_language="de",
        subtitle_type="full",
        status="wanted",
        search_count=count,
        failure_kind=kind,
        retry_after=retry_after,
        last_decision_log_json=log,
        added_at=now,
        updated_at=now,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _row(item_id):
    from db.wanted import get_wanted_item

    return get_wanted_item(item_id)


def _due_within_a_week(row):
    retry = datetime.fromisoformat(row["retry_after"])
    if retry.tzinfo is None:
        retry = retry.replace(tzinfo=UTC)
    return retry <= datetime.now(UTC) + timedelta(days=7, minutes=1)


def test_startup_refunds_unanswered_and_gate_charged_attempts(temp_db):
    app = _start()
    with app.app_context():
        from extensions import db

        db.session.execute(text("DROP TABLE IF EXISTS untracked_data_repairs"))
        db.session.commit()
        unanswered = _seed("/m/a.mkv", count=3, log=_UNANSWERED)
        gate_bumped = _seed("/m/b.mkv", count=4, log=_ANSWERED)
        both = _seed("/m/c.mkv", count=5, log=_UNANSWERED)
        genuine = _seed("/m/d.mkv", count=3, log=_ANSWERED)
        no_log = _seed("/m/e.mkv", count=3, log=None)
        permanent = _seed("/m/f.mkv", count=3, log=_ONLY_PERMANENT)
        cache = _seed(
            "/m/g.mkv",
            count=3,
            log=_log(
                {"name": "opensubtitles", "status": "skipped", "reason": "rate_limited"},
                cache_hit=True,
            ),
        )
        early = _seed("/m/h.mkv", count=1, kind="no_result", log=_UNANSWERED)

    app = _start()
    with app.app_context():
        row = _row(unanswered)
        assert (row["search_count"], row["failure_kind"]) == (2, "no_result")
        assert _due_within_a_week(row)

        row = _row(gate_bumped)
        assert (row["search_count"], row["failure_kind"]) == (3, "no_result_slow")
        assert _due_within_a_week(row), "it was skipped at its due date — search it soon"

        row = _row(both)
        assert (row["search_count"], row["failure_kind"]) == (2, "no_result")

        row = _row(early)
        assert (row["search_count"], row["failure_kind"]) == (0, "no_result")

        for untouched in (genuine, no_log, permanent, cache):
            row = _row(untouched)
            assert (row["search_count"], row["failure_kind"]) == (3, "no_result_slow")
            assert not _due_within_a_week(row), "a genuine slow-mode window is kept"


def test_repair_is_registered_for_untracked_databases():
    import db.untracked_data_repairs as repairs

    assert "wq1_refund_unanswered" in [name for name, _ in repairs.REPAIRS]


def test_a_decision_log_that_is_not_an_object_is_left_alone():
    from db.migrations.versions.wq1_refund_unanswered_searches import was_unanswered

    assert was_unanswered("null") is False
    assert was_unanswered("[1, 2]") is False
