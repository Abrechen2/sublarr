"""Auto-sync moves off the search path and onto the automation queue.

`wanted_search` used to run ffsubsync inline, in the middle of a per-item
chain. `services/video_sync.py` caps a single ffsubsync at 600s, so one
item could hold the sweep for ten minutes — against a cancel grace sized
for "6-143s" (`services/scheduler/__init__.py`). Three prod runs in a row
ended `timeout_abandoned` because of it (2026-08-15/16).

The fix is the shape that already worked twice on this queue: enqueue the
work and let the drain worker own it. These tests pin the three things
that make that safe — the video path is snapshotted (the wanted item is
often deleted moments later), deterministic failures do not cycle the
backoff ladder, and auto-sync drains on its own toggle rather than the
automation master switch.
"""

from unittest.mock import MagicMock, patch

import pytest

from db.models.core import SubtitleAutomationQueueEntry
from db.repositories.subtitle_automation_queue import (
    SubtitleAutomationQueueRepository,
)
from services.subtitle_automation_runner import SubtitleAutomationRunner

AUTO_SYNC = SubtitleAutomationQueueEntry.TASK_AUTO_SYNC


@pytest.fixture
def repo(app_ctx):
    return SubtitleAutomationQueueRepository()


@pytest.fixture
def runner(app_ctx):
    return SubtitleAutomationRunner()


def _make_settings(**overrides):
    s = MagicMock()
    s.auto_sync_after_download = overrides.get("auto_sync_after_download", True)
    s.auto_sync_engine = overrides.get("auto_sync_engine", "ffsubsync")
    return s


@pytest.fixture
def media(tmp_path):
    """A subtitle and a video that both exist — the on-disk guards need them."""
    sub = tmp_path / "show.de.srt"
    sub.write_text("1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8")
    vid = tmp_path / "show.mkv"
    vid.touch()
    return str(sub), str(vid)


# ===========================================================================
# _try_auto_sync — enqueue instead of run
# ===========================================================================


class TestTryAutoSyncEnqueues:
    def test_enqueues_instead_of_running_ffsubsync(self, app_ctx, repo, media):
        """The expensive part must not happen on the search thread."""
        sub, vid = media
        from wanted_search.post_processor import _try_auto_sync

        with patch("services.video_sync.sync_with_ffsubsync") as sync:
            _try_auto_sync(sub, vid, _make_settings(), item_id=41, target_language="de")

        sync.assert_not_called()
        entry = repo.get_by_wanted_item(41, task_type=AUTO_SYNC)
        assert entry is not None
        assert entry["state"] == "pending"

    def test_snapshots_both_paths(self, app_ctx, repo, media):
        """The video path is stored, not looked up later.

        Two of the four call sites in `wanted_search/process.py` call
        `delete_wanted_item(item_id)` on the next line — resolving the video
        from the wanted item at drain time would find nothing precisely in
        the success case.
        """
        sub, vid = media
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync(sub, vid, _make_settings(), item_id=42, target_language="de")

        entry = repo.get_by_wanted_item(42, task_type=AUTO_SYNC)
        assert entry["file_path"] == sub
        assert entry["video_path"] == vid
        assert entry["target_language"] == "de"

    def test_disabled_does_not_enqueue(self, app_ctx, repo, media):
        sub, vid = media
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync(
            sub,
            vid,
            _make_settings(auto_sync_after_download=False),
            item_id=43,
            target_language="de",
        )
        assert repo.get_by_wanted_item(43, task_type=AUTO_SYNC) is None

    def test_alass_engine_does_not_enqueue(self, app_ctx, repo, media):
        sub, vid = media
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync(
            sub,
            vid,
            _make_settings(auto_sync_engine="alass"),
            item_id=44,
            target_language="de",
        )
        assert repo.get_by_wanted_item(44, task_type=AUTO_SYNC) is None

    def test_missing_subtitle_does_not_enqueue(self, app_ctx, repo, tmp_path):
        vid = tmp_path / "v.mkv"
        vid.touch()
        from wanted_search.post_processor import _try_auto_sync

        _try_auto_sync(
            str(tmp_path / "gone.srt"),
            str(vid),
            _make_settings(),
            item_id=45,
            target_language="de",
        )
        assert repo.get_by_wanted_item(45, task_type=AUTO_SYNC) is None

    def test_enqueue_failure_never_propagates(self, app_ctx, media):
        """Auto-sync is best-effort — a queue error must not lose the download."""
        sub, vid = media
        from wanted_search.post_processor import _try_auto_sync

        with patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue",
            side_effect=RuntimeError("db down"),
        ):
            _try_auto_sync(sub, vid, _make_settings(), item_id=46, target_language="de")


# ===========================================================================
# Runner — draining an auto_sync row
# ===========================================================================


class TestRunnerAutoSync:
    def test_runs_ffsubsync_with_both_paths(self, repo, runner):
        repo.enqueue(
            wanted_item_id=51,
            file_path="/m/a.de.srt",
            video_path="/m/a.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch("services.video_sync.sync_with_ffsubsync") as sync:
            assert runner.process_one() is True

        sync.assert_called_once_with("/m/a.de.srt", "/m/a.mkv")
        assert repo.get_by_wanted_item(51, task_type=AUTO_SYNC)["state"] == "done"

    def test_sanity_threshold_is_terminal(self, repo, runner):
        """A rejected shift is deterministic — retrying yields the same shift."""
        from services.video_sync import SyncSanityThresholdError

        repo.enqueue(
            wanted_item_id=52,
            file_path="/m/b.de.srt",
            video_path="/m/b.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch(
            "services.video_sync.sync_with_ffsubsync",
            side_effect=SyncSanityThresholdError("shift 56720ms exceeds 45000ms"),
        ):
            assert runner.process_one() is True

        entry = repo.get_by_wanted_item(52, task_type=AUTO_SYNC)
        assert entry["state"] == "failed"
        assert entry["next_retry_at"] is None

    def test_sync_unavailable_is_retried(self, repo, runner):
        """ffsubsync missing needs an operator — and then a retry.

        This asserted the opposite until 2026-08-16. "Needs an operator" was
        read as "terminal", but the two do not follow: a terminal row is never
        claimed again, so every sync queued before someone installed ffsubsync
        would still be lost after they installed it. The backoff ladder caps
        at 24h, which is the right cadence for waiting on a human.
        """
        from services.video_sync import SyncUnavailableError

        repo.enqueue(
            wanted_item_id=53,
            file_path="/m/c.de.srt",
            video_path="/m/c.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch(
            "services.video_sync.sync_with_ffsubsync",
            side_effect=SyncUnavailableError("ffsubsync not installed"),
        ):
            assert runner.process_one() is True

        entry = repo.get_by_wanted_item(53, task_type=AUTO_SYNC)
        assert entry["state"] == "failed"
        assert entry["next_retry_at"] is not None

    def test_timeout_is_retried(self, repo, runner):
        """The 600s cap is a load symptom — that one is worth trying again."""
        repo.enqueue(
            wanted_item_id=54,
            file_path="/m/d.de.srt",
            video_path="/m/d.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch(
            "services.video_sync.sync_with_ffsubsync",
            side_effect=RuntimeError("ffsubsync timed out after 600s"),
        ):
            assert runner.process_one() is True

        entry = repo.get_by_wanted_item(54, task_type=AUTO_SYNC)
        assert entry["state"] == "failed"
        assert entry["next_retry_at"] is not None

    def test_missing_video_path_is_terminal(self, repo, runner):
        """A row written before this column existed cannot be synced."""
        repo.enqueue(
            wanted_item_id=55,
            file_path="/m/e.de.srt",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch("services.video_sync.sync_with_ffsubsync") as sync:
            assert runner.process_one() is True

        sync.assert_not_called()
        entry = repo.get_by_wanted_item(55, task_type=AUTO_SYNC)
        assert entry["state"] == "failed"
        assert entry["next_retry_at"] is None


# ===========================================================================
# Drain gating — two features, two toggles
# ===========================================================================


class TestDrainGating:
    def test_auto_sync_drains_with_automation_off(self, repo, runner):
        """`subtitle_automation_enabled` defaults to False.

        Gating auto-sync behind it would queue every sync on a default
        install and drain none of them — a silent regression against the
        inline behaviour this replaces.
        """
        repo.enqueue(
            wanted_item_id=61,
            file_path="/m/f.de.srt",
            video_path="/m/f.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with (
            patch(
                "services.subtitle_automation_runner._automation_enabled",
                return_value=False,
            ),
            patch(
                "services.subtitle_automation_runner._auto_sync_enabled",
                return_value=True,
            ),
            patch("services.video_sync.sync_with_ffsubsync"),
        ):
            assert runner.drain(max_items=5) == 1

        assert repo.get_by_wanted_item(61, task_type=AUTO_SYNC)["state"] == "done"

    def test_extraction_stays_behind_the_automation_toggle(self, repo, runner):
        repo.enqueue(wanted_item_id=62, file_path="/m/g.mkv", target_language="de")
        with (
            patch(
                "services.subtitle_automation_runner._automation_enabled",
                return_value=False,
            ),
            patch(
                "services.subtitle_automation_runner._auto_sync_enabled",
                return_value=True,
            ),
        ):
            assert runner.drain(max_items=5) == 0

        assert repo.get_by_wanted_item(62)["state"] == "pending"

    def test_auto_sync_skipped_when_its_own_toggle_is_off(self, repo, runner):
        """Turned off after enqueue — the queued row must not fire.

        It used to be left `pending`, which read as "about to happen" in the
        status counts for work nothing would ever claim and nothing would ever
        regenerate. It is discarded now; see `TestDiscardOfUnclaimableRows`.
        Not firing is still the assertion that matters here.
        """
        repo.enqueue(
            wanted_item_id=63,
            file_path="/m/h.de.srt",
            video_path="/m/h.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with (
            patch(
                "services.subtitle_automation_runner._automation_enabled",
                return_value=True,
            ),
            patch(
                "services.subtitle_automation_runner._auto_sync_enabled",
                return_value=False,
            ),
            patch("services.video_sync.sync_with_ffsubsync") as sync,
        ):
            runner.drain(max_items=5)

        sync.assert_not_called()
        assert repo.get_by_wanted_item(63, task_type=AUTO_SYNC) is None

    def test_both_off_drains_nothing(self, repo, runner):
        repo.enqueue(
            wanted_item_id=64,
            file_path="/m/i.de.srt",
            video_path="/m/i.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with (
            patch(
                "services.subtitle_automation_runner._automation_enabled",
                return_value=False,
            ),
            patch(
                "services.subtitle_automation_runner._auto_sync_enabled",
                return_value=False,
            ),
        ):
            assert runner.drain(max_items=5) == 0


# ===========================================================================
# claim_next task-type filter
# ===========================================================================


class TestClaimNextFilter:
    def test_filter_skips_other_task_types(self, repo):
        repo.enqueue(wanted_item_id=71, file_path="/m/j.mkv", target_language="de")
        repo.enqueue(
            wanted_item_id=71,
            file_path="/m/j.de.srt",
            video_path="/m/j.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        claim = repo.claim_next(task_types={AUTO_SYNC})
        assert claim is not None
        assert claim["task_type"] == AUTO_SYNC

    def test_no_filter_claims_anything(self, repo):
        repo.enqueue(wanted_item_id=72, file_path="/m/k.mkv", target_language="de")
        assert repo.claim_next() is not None

    def test_empty_result_when_nothing_matches(self, repo):
        repo.enqueue(wanted_item_id=73, file_path="/m/l.mkv", target_language="de")
        assert repo.claim_next(task_types={AUTO_SYNC}) is None


# ===========================================================================
# Review follow-ups (2026-08-16): the four defects a cold review found
# ===========================================================================


class TestIdentitySurvivesItemIdReuse:
    """`wanted_item_id` is not a durable identity for an auto-sync row.

    The row is written on the line before `delete_wanted_item(item_id)`, and
    SQLite hands the freed rowid to the next inserted item — 38 of 39 known
    installs run SQLite. The next item to inherit that id used to find the
    still-pending sync under its own key, get it back unchanged, and lose its
    own sync without a word in the log. `file_path` is what the work is
    actually about, so it is part of the key now.
    """

    def test_a_reused_item_id_gets_its_own_row(self, repo):
        first = repo.enqueue(
            wanted_item_id=500,
            file_path="/m/old.de.srt",
            video_path="/m/old.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        # Same id, different episode entirely — the rowid came back around.
        second = repo.enqueue(
            wanted_item_id=500,
            file_path="/m/new.de.srt",
            video_path="/m/new.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )

        assert second != first
        paths = {r["file_path"] for r in repo.list_for_item(500)}
        assert paths == {"/m/old.de.srt", "/m/new.de.srt"}

    def test_the_same_file_still_deduplicates(self, repo):
        first = repo.enqueue(
            wanted_item_id=501,
            file_path="/m/same.de.srt",
            video_path="/m/same.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        second = repo.enqueue(
            wanted_item_id=501,
            file_path="/m/same.de.srt",
            video_path="/m/same.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )

        assert second == first
        assert len(repo.list_for_item(501)) == 1


class TestMissingEngineIsRetryable:
    """ "ffsubsync is not installed" is an operator's job, not a verdict.

    It was classed terminal alongside the sanity-threshold rejection. But a
    terminal row is never claimed again, so every sync queued before someone
    installed ffsubsync would have stayed lost after they did.
    """

    def _claim_and_run(self, runner, repo, exc):
        with patch("services.video_sync.sync_with_ffsubsync", side_effect=exc):
            runner.process_one(task_types={AUTO_SYNC})
        return repo.claim_next(task_types={AUTO_SYNC}, now=None)

    def test_unavailable_engine_keeps_a_retry_date(self, app_ctx, repo, runner):
        from services.video_sync import SyncUnavailableError

        entry_id = repo.enqueue(
            wanted_item_id=510,
            file_path="/m/a.de.srt",
            video_path="/m/a.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch(
            "services.video_sync.sync_with_ffsubsync",
            side_effect=SyncUnavailableError("ffsubsync is not installed"),
        ):
            runner.process_one(task_types={AUTO_SYNC})

        row = repo.get_by_id(entry_id)
        assert row["state"] == "failed"
        assert row["next_retry_at"] is not None

    def test_a_rejected_shift_stays_terminal(self, app_ctx, repo, runner):
        from services.video_sync import SyncSanityThresholdError

        entry_id = repo.enqueue(
            wanted_item_id=511,
            file_path="/m/b.de.srt",
            video_path="/m/b.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with patch(
            "services.video_sync.sync_with_ffsubsync",
            side_effect=SyncSanityThresholdError("shift 90000ms exceeds threshold"),
        ):
            runner.process_one(task_types={AUTO_SYNC})

        row = repo.get_by_id(entry_id)
        assert row["state"] == "failed"
        assert row["next_retry_at"] is None


class TestDiscardOfUnclaimableRows:
    """Rows nobody will ever claim must not sit in the queue forever.

    Only auto-sync rows qualify. The scanner re-enqueues extractions and
    sidecar translations on its next pass, so those are merely paused — and
    deleting a backlog the user gets back anyway, over a toggle they may flip
    for an hour, would be the worse bug.
    """

    def test_auto_sync_rows_go_when_the_feature_is_off(self, app_ctx, repo, runner):
        repo.enqueue(
            wanted_item_id=520,
            file_path="/m/c.de.srt",
            video_path="/m/c.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        with (
            patch("services.subtitle_automation_runner._auto_sync_enabled", return_value=False),
            patch("services.subtitle_automation_runner._automation_enabled", return_value=True),
        ):
            runner.drain(max_items=5)

        assert repo.get_by_wanted_item(520, task_type=AUTO_SYNC) is None

    def test_other_task_types_are_left_alone(self, app_ctx, repo, runner):
        repo.enqueue(wanted_item_id=521, file_path="/m/d.mkv", target_language="de")
        with (
            patch("services.subtitle_automation_runner._auto_sync_enabled", return_value=False),
            patch("services.subtitle_automation_runner._automation_enabled", return_value=False),
        ):
            runner.drain(max_items=5)

        assert repo.get_by_wanted_item(521) is not None

    def test_an_unreadable_setting_deletes_nothing(self, app_ctx, repo, runner):
        """ "Off" and "could not tell" must not be the same answer.

        `_auto_sync_enabled` collapses any exception into a safe default, which
        cost nothing while the default only meant "do not claim". Once it also
        meant "delete", a transient config or database error would have
        permanently dropped queued work on the strength of a question nobody
        managed to ask.
        """
        repo.enqueue(
            wanted_item_id=523,
            file_path="/m/x.de.srt",
            video_path="/m/x.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        # Patched at the source: both toggle readers import `get_settings`
        # inside the function body, so the module attribute is what they see.
        with patch("config.get_settings", side_effect=RuntimeError("database is locked")):
            runner.drain(max_items=5)

        assert repo.get_by_wanted_item(523, task_type=AUTO_SYNC) is not None

    def test_a_running_row_is_never_discarded(self, app_ctx, repo, runner):
        entry_id = repo.enqueue(
            wanted_item_id=522,
            file_path="/m/e.de.srt",
            video_path="/m/e.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        repo.claim_next(task_types={AUTO_SYNC})  # → running, a worker owns it

        with (
            patch("services.subtitle_automation_runner._auto_sync_enabled", return_value=False),
            patch("services.subtitle_automation_runner._automation_enabled", return_value=True),
        ):
            runner.drain(max_items=5)

        assert repo.get_by_id(entry_id)["state"] == "running"


class TestAutoSyncClaimsFirst:
    """Shortest job first — a sync is capped at 600s, a translation runs ~16min.

    Auto-sync's whole value is that it happens close to the download. Without
    a priority it would queue behind whatever translations are already there.
    """

    def test_a_later_sync_beats_an_earlier_translation(self, repo):
        repo.enqueue(
            wanted_item_id=530,
            file_path="/m/f.en.srt",
            target_language="de",
            task_type=SubtitleAutomationQueueEntry.TASK_SIDECAR_TRANSLATE,
            source_language="en",
        )
        repo.enqueue(
            wanted_item_id=531,
            file_path="/m/g.de.srt",
            video_path="/m/g.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )

        claim = repo.claim_next()
        assert claim["task_type"] == AUTO_SYNC

    def test_syncs_among_themselves_stay_oldest_first(self, repo):
        first = repo.enqueue(
            wanted_item_id=540,
            file_path="/m/h.de.srt",
            video_path="/m/h.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )
        repo.enqueue(
            wanted_item_id=541,
            file_path="/m/i.de.srt",
            video_path="/m/i.mkv",
            target_language="de",
            task_type=AUTO_SYNC,
        )

        assert repo.claim_next()["id"] == first
