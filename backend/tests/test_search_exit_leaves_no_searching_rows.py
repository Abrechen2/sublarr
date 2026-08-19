"""No exit of ``process_wanted_item`` may leave a row in ``status='searching'``.

Prod 2026-08-19: 7,878 wanted rows sat in ``searching`` with
``search_count=0`` and no ``failure_kind`` — invisible forever, because the
scheduled selector only picks ``status='wanted'``. Roughly 1,600 rows were
stranded per 4-hour tick since 1.12.1-rc.9 went live.

The mass path: with the subtitle-automation queue enabled the scheduled
search passes ``allow_translate_fallback=False`` (commit 45c9bba6), and the
deferred Step-5 exit returned ``not_found`` without resetting the status or
recording a search outcome — and nothing ever enqueued the item either. The
narrow path: ``_stopped_result`` promised "the item keeps its state and the
next run picks it up unchanged", but the state at that point is already
``searching``, which no run ever picks up. Exceptions mid-steps stranded the
row the same way.

Fix shape: the deferred exit does the same bookkeeping as the
``auto_translate``-off exit (back to ``wanted`` + ``no_result`` outcome), and
``process_wanted_item`` carries a safety net that restores the pre-flip
status on any exit that would otherwise leak ``searching``.
"""

import threading
from unittest.mock import MagicMock

import pytest

from db.wanted import get_wanted_item, update_wanted_status, upsert_wanted_item
from services.scheduler import cancellation


def _make_wanted_item(tmp_path, target_language="de"):
    mkv = tmp_path / "ep.mkv"
    mkv.touch()
    row_id, _ = upsert_wanted_item(
        item_type="episode",
        file_path=str(mkv),
        target_language=target_language,
    )
    return row_id, mkv


def _no_provider_hits(monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.search.return_value = []
    mock_mgr.search_and_download_best.return_value = None
    monkeypatch.setattr("wanted_search.process.get_provider_manager", lambda: mock_mgr)
    return mock_mgr


@pytest.fixture
def _stopped():
    """A stop request bound to this thread for the duration of the test."""
    event = threading.Event()
    event.set()
    token = cancellation.activate(event)
    yield
    cancellation.deactivate(token)


class TestDeferredFallbackExit:
    def test_deferred_fallback_returns_the_item_to_rotation(self, app_ctx, monkeypatch, tmp_path):
        """The automation handoff is a no-result exit and must be charged as one:
        status back to ``wanted`` plus failure_kind/retry_after/search_count, so
        the item re-enters rotation with a backoff instead of vanishing."""
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        _no_provider_hits(monkeypatch)

        out = process_wanted_item(item_id, allow_translate_fallback=False)

        assert out.get("status") == "not_found"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "the row must not stay in 'searching'"
        assert item["failure_kind"] == "no_result"
        assert item["retry_after"] is not None, "a no-result exit earns a backoff"
        assert item["search_count"] == 1


class TestStoppedExit:
    def test_a_stopped_item_goes_back_to_wanted_uncharged(
        self, app_ctx, monkeypatch, tmp_path, _stopped
    ):
        """A cancelled item keeps its pre-flip status AND stays uncharged —
        no search_count bump, no failure_kind, no backoff it never earned."""
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        _no_provider_hits(monkeypatch)

        out = process_wanted_item(item_id)

        assert out.get("status") == "stopped"
        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "the row must not stay in 'searching'"
        assert not item.get("failure_kind")
        assert item.get("retry_after") is None
        assert (item.get("search_count") or 0) == 0

    def test_a_stopped_provisional_item_stays_provisional(
        self, app_ctx, monkeypatch, tmp_path, _stopped
    ):
        """mt_reseek runs provisional MT rows through the same pipeline; the
        restore must return them to 'provisional', not force them to 'wanted'."""
        from wanted_search import process_wanted_item

        item_id, _ = _make_wanted_item(tmp_path)
        update_wanted_status(item_id, "provisional")
        _no_provider_hits(monkeypatch)

        process_wanted_item(item_id, bypass_existing_target_check=True)

        item = get_wanted_item(item_id)
        assert item["status"] == "provisional"


class TestExceptionExit:
    def test_an_exception_mid_search_does_not_strand_the_row(self, app_ctx, monkeypatch, tmp_path):
        """The runner logs the error and moves on — but the row itself must
        come back to 'wanted' instead of leaking 'searching'."""
        from wanted_search import process as proc

        item_id, _ = _make_wanted_item(tmp_path)
        _no_provider_hits(monkeypatch)

        monkeypatch.setattr(
            proc,
            "_run_search_steps",
            MagicMock(side_effect=RuntimeError("provider blew up")),
        )

        with pytest.raises(RuntimeError):
            proc.process_wanted_item(item_id)

        item = get_wanted_item(item_id)
        assert item["status"] == "wanted", "the row must not stay in 'searching'"


class TestBootReclaim:
    """Rows stranded by an affected version (or a SIGKILL mid-search, where no
    finally can run) are healed once at scheduler bootstrap — at that moment no
    search can be running, so every 'searching' row is an orphan."""

    def test_bootstrap_reclaim_returns_stranded_rows_to_wanted(self, app_ctx, tmp_path):
        from db.repositories.wanted import WantedRepository

        item_id, _ = _make_wanted_item(tmp_path)
        update_wanted_status(item_id, "searching")

        reclaimed = WantedRepository().reclaim_stranded_searching()

        assert reclaimed == 1
        assert get_wanted_item(item_id)["status"] == "wanted"

    def test_bootstrap_reclaim_leaves_settled_rows_alone(self, app_ctx, tmp_path):
        from db.repositories.wanted import WantedRepository

        item_id, _ = _make_wanted_item(tmp_path)
        update_wanted_status(item_id, "failed", error="boom")

        reclaimed = WantedRepository().reclaim_stranded_searching()

        assert reclaimed == 0
        assert get_wanted_item(item_id)["status"] == "failed"

    def test_bootstrap_reclaim_preserves_the_backoff_state(self, app_ctx, tmp_path):
        """Reclaim restores visibility; it must not grant a free retry."""
        from db.repositories.wanted import WantedRepository
        from services.wanted_search_runner import record_search_outcome

        item_id, _ = _make_wanted_item(tmp_path)
        record_search_outcome(item_id, kind="no_result")
        update_wanted_status(item_id, "searching")

        WantedRepository().reclaim_stranded_searching()

        item = get_wanted_item(item_id)
        assert item["status"] == "wanted"
        assert item["failure_kind"] == "no_result"
        assert item["retry_after"] is not None
        assert item["search_count"] == 1
