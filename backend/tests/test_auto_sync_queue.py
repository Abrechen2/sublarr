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

    def test_sync_unavailable_is_terminal(self, repo, runner):
        """ffsubsync missing needs an operator, not a backoff ladder."""
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
        assert entry["next_retry_at"] is None

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
        """Turned off after enqueue — the queued row must not fire."""
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
        assert repo.get_by_wanted_item(63, task_type=AUTO_SYNC)["state"] == "pending"

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
