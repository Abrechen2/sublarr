"""The download-time cleanup never strips more than configured (parked 1.15.0
review items, fixed 2026-09-26):

- a movie's own ``cleanup_foreign_tracks`` switch is honoured (only the series
  switch was read);
- a failing settings lookup does not fall back to the global default — the
  cleanup is skipped instead;
- a failing language-profile lookup does not fall back to the default
  profile, whose narrower keep-set could strip the title's own languages.
"""

from datetime import UTC, datetime
from unittest.mock import patch


def _movie(movie_id, **fields):
    from db.models.core import MovieSettings
    from extensions import db

    db.session.add(MovieSettings(radarr_movie_id=movie_id, updated_at=datetime.now(UTC), **fields))
    db.session.commit()


def _global(value, monkeypatch):
    from config import get_settings

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", value)


def test_a_movie_switched_off_is_never_cleaned(app_ctx, monkeypatch):
    from services.foreign_track_cleanup import foreign_track_cleanup_applies

    _global(True, monkeypatch)
    _movie(501, cleanup_foreign_tracks=False)
    assert foreign_track_cleanup_applies({"radarr_movie_id": 501}) is False


def test_a_movie_switched_on_is_cleaned_despite_the_global_off(app_ctx, monkeypatch):
    from services.foreign_track_cleanup import foreign_track_cleanup_applies

    _global(False, monkeypatch)
    _movie(502, cleanup_foreign_tracks=True)
    assert foreign_track_cleanup_applies({"radarr_movie_id": 502}) is True


def test_a_movie_without_a_switch_inherits_the_global(app_ctx, monkeypatch):
    from services.foreign_track_cleanup import foreign_track_cleanup_applies

    _global(True, monkeypatch)
    assert foreign_track_cleanup_applies({"radarr_movie_id": 503}) is True


def test_a_failing_override_lookup_skips_instead_of_inheriting(app_ctx, monkeypatch):
    from extensions import db
    from services.foreign_track_cleanup import foreign_track_cleanup_applies

    _global(True, monkeypatch)
    with patch.object(db.session, "get", side_effect=RuntimeError("db down")):
        assert foreign_track_cleanup_applies({"sonarr_series_id": 7}) is False
        assert foreign_track_cleanup_applies({"radarr_movie_id": 7}) is False


def test_a_failing_profile_lookup_refuses_instead_of_using_the_default(app_ctx):
    from services.foreign_track_cleanup import cleanup_keep_languages

    with patch("db.profiles.get_series_profile", side_effect=RuntimeError("db down")):
        assert cleanup_keep_languages({"sonarr_series_id": 7, "target_language": "de"}) is None


# --- "unknown" is its own answer, retried later (night review I3) ---------------


def test_an_unreadable_switch_is_unknown_not_off(app_ctx, monkeypatch):
    from extensions import db
    from services.foreign_track_cleanup import foreign_track_cleanup_decision

    _global(False, monkeypatch)
    with patch.object(db.session, "get", side_effect=RuntimeError("db down")):
        assert foreign_track_cleanup_decision({"sonarr_series_id": 7}) is None
    _movie(504, cleanup_foreign_tracks=True)
    assert foreign_track_cleanup_decision({"radarr_movie_id": 504}) is True
    assert foreign_track_cleanup_decision({"radarr_movie_id": 505}) is False


def test_a_failed_switch_lookup_rolls_the_session_back(app_ctx):
    """On Postgres a failed statement aborts the transaction; without a
    rollback every later query in the request fails too."""
    from extensions import db
    from services.foreign_track_cleanup import foreign_track_cleanup_applies

    with (
        patch.object(db.session, "get", side_effect=RuntimeError("db down")),
        patch.object(db.session, "rollback") as rollback,
    ):
        foreign_track_cleanup_applies({"sonarr_series_id": 7})
    assert rollback.called


def test_the_drain_retries_when_the_switch_is_unreadable(app_ctx, tmp_path, monkeypatch):
    """CLEANUP_SKIPPED would book the queue row done and the cleanup would never
    run; FAILED puts it on the backoff ladder. Nothing is stripped meanwhile."""
    from extensions import db
    from services.foreign_track_cleanup import CLEANUP_FAILED, maybe_run_foreign_track_cleanup

    _global(True, monkeypatch)
    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    with (
        patch.object(db.session, "get", side_effect=RuntimeError("db down")),
        patch("remux.remove_foreign_subtitle_streams") as strip,
    ):
        outcome = maybe_run_foreign_track_cleanup(
            {"sonarr_series_id": 7, "target_language": "de"}, str(video), {"de"}
        )
    assert outcome == CLEANUP_FAILED
    strip.assert_not_called()


def test_the_download_queues_the_cleanup_when_the_switch_is_unreadable(
    app_ctx, tmp_path, monkeypatch
):
    """The download path must not drop the cleanup on a failed lookup: it
    queues it, and the drain decides once the switch is readable."""
    from config import reload_settings
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from providers.download_manager import save_subtitle
    from services import foreign_track_cleanup as ftc
    from tests.test_foreign_track_cleanup_deferred import _result

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    (tmp_path / "Show - S01E01.mkv").write_bytes(b"v")

    with patch.object(
        ftc, "_get_title_override", side_effect=ftc._OverrideUnavailableError("db down")
    ):
        save_subtitle(_result(), str(tmp_path / "Show - S01E01.de.srt"), series_id=42)

    rows = [
        r
        for r in SubtitleAutomationQueueRepository().list_for_item(42)
        if r["task_type"] == SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP
    ]
    assert len(rows) == 1


def test_the_download_does_not_queue_for_a_title_switched_off(app_ctx, tmp_path, monkeypatch):
    from config import reload_settings
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from providers.download_manager import save_subtitle
    from tests.test_foreign_track_cleanup_deferred import _result

    monkeypatch.setenv("SUBLARR_MEDIA_PATH", str(tmp_path))
    reload_settings()
    _global(True, monkeypatch)
    _movie(506, cleanup_foreign_tracks=False)
    (tmp_path / "Movie (2020).mkv").write_bytes(b"v")

    save_subtitle(_result(), str(tmp_path / "Movie (2020).de.srt"), movie_id=506)

    rows = [
        r
        for r in SubtitleAutomationQueueRepository().list_for_item(0)
        if r["task_type"] == SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP
    ]
    assert rows == []


def test_batch_probe_skips_the_cleanup_when_the_switch_is_unreadable(app_ctx, tmp_path, caplog):
    """The batch-probe path has no queue behind it: unknown means skip, with
    the warning — never inherit the global default."""
    import logging

    from services import foreign_track_cleanup as ftc

    video = tmp_path / "Ep.mkv"
    video.write_bytes(b"v")
    with (
        patch.object(
            ftc, "_get_title_override", side_effect=ftc._OverrideUnavailableError("db down")
        ),
        patch("remux.remove_foreign_subtitle_streams") as strip,
        caplog.at_level(logging.WARNING, logger="services.foreign_track_cleanup"),
    ):
        ftc.maybe_run_foreign_track_cleanup(
            {"sonarr_series_id": 7, "target_language": "de"}, str(video)
        )
    strip.assert_not_called()
    assert "unreadable" in caplog.text
