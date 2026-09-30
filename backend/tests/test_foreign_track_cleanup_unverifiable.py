"""A remux that fails its own verification is not retried for five days.

Prod 2026-09-29/30: Magia Record S01E07 failed ``Duration mismatch:
original=1438.2s remuxed=1420.0s — file untouched`` at 08:05, 09:54, 10:18,
12:26 and 18:28, each attempt a full remux of the episode, and was headed for
ten on the backoff ladder. The same input gives the same mismatch every time;
the sweep already books a verification failure terminal
(``ERROR_VERIFY`` — "the case a human should look at"). A busy media gate or
a concurrent modification is different: those can pass on the next attempt.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from remux import RemuxError, RemuxVerificationError


def _queue_cleanup(video, series_id=42):
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository

    repo = SubtitleAutomationQueueRepository()
    repo.enqueue(
        wanted_item_id=series_id,
        file_path=str(video),
        target_language="de",
        task_type=SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP,
    )
    return repo


def _drain_once(remux_error):
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value={}),
        patch("services.embedded_extractor.compute_keep_langs", return_value=set()),
        patch("services.foreign_track_cleanup.foreign_track_cleanup_decision", return_value=True),
        patch("services.foreign_track_cleanup.keep_tags_for", return_value=({"de"}, {"de"})),
        patch("services.foreign_track_cleanup.cleanup_keep_languages", return_value={"de"}),
        patch(
            "services.foreign_tracks.policy.resolve_policy",
            return_value=SimpleNamespace(sidecar_policy="keep"),
        ),
        patch("remux.remove_foreign_subtitle_streams", side_effect=remux_error),
    ):
        SubtitleAutomationRunner().process_one()


class TestTheVerdictOfTheCheck:
    def test_a_duration_mismatch_is_a_verification_error(self, tmp_path):
        from remux import _verify

        probes = iter(
            [
                {"streams": [{"codec_type": "video", "duration": "1438.2"}], "format": {}},
                {"streams": [{"codec_type": "video", "duration": "1420.0"}], "format": {}},
            ]
        )
        with (
            patch("remux._probe", side_effect=lambda _p: next(probes)),
            pytest.raises(RemuxVerificationError, match="Duration mismatch"),
        ):
            _verify("a.mkv", "b.mkv")

    def test_it_is_still_a_remux_error_for_existing_handlers(self):
        assert issubclass(RemuxVerificationError, RemuxError)


class TestTheQueueBooksItTerminal:
    def test_a_failed_verification_is_not_put_on_the_ladder(self, app_ctx, tmp_path):
        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"v")
        repo = _queue_cleanup(video)

        _drain_once(RemuxVerificationError("Duration mismatch: original=1438.2s remuxed=1420.0s"))

        row = repo.list_for_item(42)[0]
        assert row["state"] == "failed"
        assert row["next_retry_at"] is None
        assert "failed verification" in (row["last_error"] or "")

    def test_a_busy_media_gate_is_still_retried(self, app_ctx, tmp_path):
        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"v")
        repo = _queue_cleanup(video)

        _drain_once(RemuxError("media IO gate busy: mkvmerge remux waited 3600s"))

        row = repo.list_for_item(42)[0]
        assert row["state"] == "failed"
        assert row["next_retry_at"] is not None


class TestTheSweepReadsTheSameVerdict:
    def test_a_duration_mismatch_parks_the_row_as_a_verify_failure(self, app_ctx, tmp_path):
        """The sweep matched on "verif" in the message, which a duration
        mismatch does not contain — so it was booked a plain remux error and
        retried."""
        from db.models import foreign_tracks as ft
        from db.repositories.foreign_track_scan import ForeignTrackScanRepository
        from services.foreign_tracks import sweep as sw

        repo = ForeignTrackScanRepository()
        path = str(tmp_path / "ep.mkv")
        repo.upsert_seen(path, 10, 1.0, generation=1)
        repo.mark_probed(path, ["spa"])
        mismatch = RemuxVerificationError("Duration mismatch: original=1438.2s remuxed=1420.0s")
        with (
            patch.object(sw, "iter_video_files", lambda *a, **k: iter([])),
            patch.object(sw, "_strip_file", side_effect=mismatch),
            patch(
                "config.get_settings",
                lambda: SimpleNamespace(
                    cleanup_foreign_tracks_keep_languages=["de"],
                    cleanup_foreign_tracks_keep_und=True,
                ),
            ),
        ):
            sw.run_slice(str(tmp_path), {"keep_languages": ["de"]}, budget_s=60, repo=repo)

        row = repo._get(path)
        assert row.error_class == ft.ERROR_VERIFY
        assert row.state == ft.STATE_FAILED
