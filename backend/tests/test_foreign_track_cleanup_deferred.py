"""A provider download hands the foreign-track remux to the automation queue.

Prod 2026-09-24/25: ``save_subtitle`` ran the foreign-track cleanup inline, so
every subtitle a scheduled search saved could wait up to 3600 s for the media
I/O slot behind ffsubsync. Items took 2 227-5 642 s instead of 158 s and the
search was booked ``timeout`` / ``timeout_abandoned``. The remux now runs in the
automation drain, which owns long media work; the search only enqueues.
"""

from types import SimpleNamespace
from unittest.mock import patch

from providers.base import SubtitleFormat

_SRT = b"1\n00:00:01,000 --> 00:00:02,000\nHallo Welt\n\n2\n00:00:03,000 --> 00:00:04,000\nZweite Zeile\n"


def _result():
    return SimpleNamespace(
        content=_SRT,
        format=SubtitleFormat.SRT,
        language="de",
        provider_name="opensubtitles",
        subtitle_id="s1",
        score=300,
    )


def test_save_subtitle_enqueues_instead_of_remuxing(app_ctx, tmp_path, monkeypatch):
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from providers.download_manager import save_subtitle

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    from config import reload_settings

    reload_settings()
    video = tmp_path / "Show - S01E01.mkv"
    video.write_bytes(b"v")

    with (
        patch("services.foreign_track_cleanup.foreign_track_cleanup_applies", return_value=True),
        patch("services.foreign_track_cleanup.maybe_run_foreign_track_cleanup") as inline,
    ):
        save_subtitle(_result(), str(tmp_path / "Show - S01E01.de.srt"), series_id=42)

    assert not inline.called, "a search must not wait for the remux"
    rows = [
        r
        for r in SubtitleAutomationQueueRepository().list_for_item(42)
        if r["task_type"] == SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP
    ]
    assert len(rows) == 1
    assert rows[0]["file_path"] == str(video)
    assert rows[0]["wanted_item_id"] == 42
    assert rows[0]["target_language"] == "de"


def test_the_drain_runs_the_cleanup_with_the_profile_keep_set(app_ctx, tmp_path):
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    repo = SubtitleAutomationQueueRepository()
    repo.enqueue(
        wanted_item_id=42,
        file_path=str(video),
        target_language="de",
        task_type=SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP,
    )

    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value={}),
        patch("services.embedded_extractor.compute_keep_langs", return_value={"ja"}),
        patch("services.foreign_track_cleanup.maybe_run_foreign_track_cleanup") as run,
    ):
        assert SubtitleAutomationRunner().process_one() is True

    item, video_arg = run.call_args.args
    assert item == {"sonarr_series_id": 42, "target_language": "de"}
    assert video_arg == str(video)
    assert run.call_args.kwargs["target_languages"] == {"ja", "de"}


def test_a_movie_row_carries_no_series(app_ctx, tmp_path):
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    video = tmp_path / "Movie.mkv"
    video.write_bytes(b"v")
    SubtitleAutomationQueueRepository().enqueue(
        wanted_item_id=0,
        file_path=str(video),
        target_language="en",
        task_type=SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP,
    )
    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value={}),
        patch("services.embedded_extractor.compute_keep_langs", return_value=set()),
        patch("services.foreign_track_cleanup.maybe_run_foreign_track_cleanup") as run,
    ):
        SubtitleAutomationRunner().process_one()

    assert run.call_args.args[0]["sonarr_series_id"] is None


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


def _drain_once(outcome):
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value={}),
        patch("services.embedded_extractor.compute_keep_langs", return_value=set()),
        patch(
            "services.foreign_track_cleanup.maybe_run_foreign_track_cleanup", return_value=outcome
        ),
        patch("services.media_server_notify.notify_media_servers") as notify,
    ):
        SubtitleAutomationRunner().process_one()
    return notify


def test_a_stripped_video_is_announced_to_the_media_server(app_ctx, tmp_path):
    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    _queue_cleanup(video)

    notify = _drain_once("stripped")

    notify.assert_called_once_with(str(video), "episode")


def test_a_failed_remux_goes_to_the_backoff_ladder(app_ctx, tmp_path):
    """A busy media gate or a remux error used to be swallowed and the row
    marked done — the cleanup was simply lost."""
    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    repo = _queue_cleanup(video)

    notify = _drain_once("failed")

    row = repo.list_for_item(42)[0]
    assert row["state"] == "failed" and row["next_retry_at"] is not None
    assert not notify.called


def test_a_terminal_row_does_not_block_the_next_download(app_ctx, tmp_path):
    from db.models.core import SubtitleAutomationQueueEntry
    from extensions import db

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    repo = _queue_cleanup(video)
    row = db.session.query(SubtitleAutomationQueueEntry).one()
    row.state, row.next_retry_at, row.last_error = "failed", None, "video gone"
    db.session.commit()

    _queue_cleanup(video)

    assert repo.list_for_item(42)[0]["state"] == "pending"


def test_nothing_is_queued_when_cleanup_is_off(app_ctx, tmp_path, monkeypatch):
    from config import get_settings, reload_settings
    from providers.download_manager import save_subtitle

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", False, raising=False)
    (tmp_path / "Show - S01E01.mkv").write_bytes(b"v")

    save_subtitle(_result(), str(tmp_path / "Show - S01E01.de.srt"), series_id=42)

    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository

    assert SubtitleAutomationQueueRepository().list_for_item(42) == []


def test_a_failed_enqueue_leaves_the_session_usable(app_ctx, tmp_path, monkeypatch):
    from config import reload_settings
    from providers.download_manager import save_subtitle

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    (tmp_path / "Show - S01E01.mkv").write_bytes(b"v")

    with (
        patch("services.foreign_track_cleanup.foreign_track_cleanup_applies", return_value=True),
        patch(
            "db.repositories.subtitle_automation_queue.SubtitleAutomationQueueRepository.enqueue",
            side_effect=RuntimeError("unique constraint"),
        ),
        patch("extensions.db.session.rollback") as rollback,
    ):
        save_subtitle(_result(), str(tmp_path / "Show - S01E01.de.srt"), series_id=42)

    assert rollback.called


def test_a_terminal_extraction_row_stays_closed_on_re_enqueue(app_ctx):
    """The scanner re-enqueues extraction every scan; reopening would undo the cap."""
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from extensions import db

    repo = SubtitleAutomationQueueRepository()
    repo.enqueue(wanted_item_id=5, file_path="/m/x.mkv", target_language="de")
    row = db.session.query(SubtitleAutomationQueueEntry).one()
    row.state, row.next_retry_at = "failed", None
    db.session.commit()

    repo.enqueue(wanted_item_id=5, file_path="/m/x.mkv", target_language="de")

    assert repo.list_for_item(5)[0]["state"] == "failed"
