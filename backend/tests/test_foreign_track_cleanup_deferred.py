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

    with patch("services.foreign_track_cleanup.maybe_run_foreign_track_cleanup") as inline:
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
