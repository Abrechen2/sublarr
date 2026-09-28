"""One lost database connection must cost one item, not the whole run.

SQLAlchemy leaves a session that failed mid-flush in "rolled back due to a
previous exception during flush", and every further statement on it raises the
same error until someone calls ``rollback()``. The session is per thread and
outlives a single item, so without that call the first failure is inherited by
every item after it.

Prod 2026-09-27 22:30 measured the shape. Unraid's appdata backup restarted
Postgres under a running tick, and the one lost connection became 98 identical

    Wanted N: Process failed: This Session's transaction has been rolled back
    due to a previous exception during flush. ... Can't reconnect until invalid
    transaction is rolled back.

— one per remaining item. None of the bookkeeping in the error handler landed
either, because those three calls use the same poisoned session.

The rollback therefore has to come first in the handler, before the handler's
own writes. That ordering is what this file pins down; asserting only "rollback
was called" would pass on a version that calls it last and still books nothing.
"""

from unittest.mock import patch

import pytest


@pytest.fixture
def ctx(tmp_path):
    video = tmp_path / "Serie" / "S01E01.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")
    return {
        "item": {"id": 1},
        "item_id": 1,
        "item_lang": "de",
        "auto_translate": True,
        "file_path": str(video),
    }


def _run_with_failing_first_write(ctx, calls):
    """Drive _fallback_translate_file into its handler the way prod did.

    The first write after the job row is created raises — that is a dropped
    connection mid-flush — and everything the handler then does is recorded in
    call order.
    """
    from wanted_search import process

    state = {"first": True}

    def _update_job(*_a, **_k):
        calls.append("update_job")
        if state["first"]:
            state["first"] = False
            raise RuntimeError(
                "This Session's transaction has been rolled back due to a previous "
                "exception during flush"
            )

    class _Session:
        def rollback(self):
            calls.append("rollback")

    class _Db:
        session = _Session()

    with (
        patch.object(process, "_target_subtitle_on_disk", return_value=None),
        patch.object(process, "_build_arr_context", return_value={}),
        patch.object(process, "create_job", return_value={"id": 7}),
        patch.object(process, "update_job", _update_job),
        patch.object(process, "record_stat", lambda **_k: calls.append("record_stat")),
        patch.dict("sys.modules", {"extensions": type("m", (), {"db": _Db()})}),
        patch(
            "services.wanted_search_runner.record_search_outcome",
            lambda *_a, **_k: calls.append("record_search_outcome"),
        ),
    ):
        return process._fallback_translate_file(ctx)


class TestTheHandlerRecoversTheSession:
    def test_it_rolls_back(self, ctx):
        calls: list[str] = []
        _run_with_failing_first_write(ctx, calls)
        assert "rollback" in calls, (
            f"a poisoned session was handed to the next item unchanged — handler did: {calls}"
        )

    def test_it_rolls_back_before_its_own_bookkeeping(self, ctx):
        """Rolling back last would still leave update_job/record_stat failing."""
        calls: list[str] = []
        _run_with_failing_first_write(ctx, calls)

        rollback_at = calls.index("rollback")
        writes_after = [c for c in calls[rollback_at + 1 :] if c != "rollback"]
        assert writes_after, f"nothing was booked after the rollback: {calls}"

    def test_the_item_still_reports_failed(self, ctx):
        """Recovering the session may not turn a failure into a success."""
        calls: list[str] = []
        result = _run_with_failing_first_write(ctx, calls)
        assert result["status"] == "failed"
        assert result["wanted_id"] == 1
