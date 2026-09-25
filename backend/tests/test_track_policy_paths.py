"""Task 6: post-download, batch-probe and executor paths apply the track policy.

Covers ``maybe_run_foreign_track_cleanup`` resolving the series/movie policy
itself (batch_probe and the automation runner both call the hook unchanged)
and, under policy B (``drop_if_real_sidecar``), looking up the real sidecar
languages before handing them to ``remux.remove_foreign_subtitle_streams``.

Fix round 1 adds the movie half of that story: a movie download's foreign
track cleanup row had nowhere to carry its Radarr movie id, so the drain
could resolve a series override but never a movie one — the exact same
function, two different verdicts depending on which arr the item came from.
"""

from unittest.mock import patch

from services.foreign_tracks.select import TrackPolicy


def test_the_hook_passes_the_series_policy_and_real_sidecars(app_ctx, monkeypatch):
    from config import get_settings
    from services import foreign_track_cleanup as ftc

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", True)
    policy = TrackPolicy(mode="one_per_language", sidecar_policy="drop_if_real_sidecar")
    with (
        patch("services.foreign_tracks.policy.resolve_policy", return_value=policy) as resolve,
        patch("services.foreign_tracks.sidecars.real_sidecar_languages", return_value={"de"}),
        patch("remux.remove_foreign_subtitle_streams", return_value="/bak") as strip,
    ):
        ftc.maybe_run_foreign_track_cleanup(
            {"sonarr_series_id": 5, "target_language": "de"}, "/m/x.mkv", {"de"}
        )
    resolve.assert_called_once_with(series_id=5, movie_id=None)
    assert strip.call_args.kwargs["policy"] == policy
    assert strip.call_args.kwargs["real_sidecar_langs"] == {"de"}


def test_sidecars_are_not_looked_up_under_policy_a(app_ctx, monkeypatch):
    from config import get_settings
    from services import foreign_track_cleanup as ftc

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", True)
    with (
        patch("services.foreign_tracks.policy.resolve_policy", return_value=TrackPolicy()),
        patch("services.foreign_tracks.sidecars.real_sidecar_languages") as lookup,
        patch("remux.remove_foreign_subtitle_streams", return_value=None),
    ):
        ftc.maybe_run_foreign_track_cleanup({"target_language": "de"}, "/m/x.mkv", {"de"})
    assert not lookup.called


def test_radarr_movie_id_column_exists_on_an_untracked_database(temp_db):
    """Same shape as test_track_policy_settings.py's column-existence check:
    an untracked DB (no alembic_version) must get the column from
    app._patch_pre_alembic_columns, not only from the migration."""
    from sqlalchemy import inspect

    from app import create_app
    from extensions import db

    app = create_app(testing=True)
    with app.app_context():
        insp = inspect(db.engine)
        cols = {c["name"] for c in insp.get_columns("subtitle_automation_queue")}
        assert "radarr_movie_id" in cols


def test_the_drain_resolves_the_movie_override(app_ctx, tmp_path, monkeypatch):
    """The drain must reach resolve_policy(movie_id=...) for a movie row —
    not only resolve_policy(series_id=...) for a series row."""
    from config import get_settings
    from db.models.core import SubtitleAutomationQueueEntry
    from db.repositories.subtitle_automation_queue import SubtitleAutomationQueueRepository
    from services.subtitle_automation_runner import SubtitleAutomationRunner

    monkeypatch.setattr(get_settings(), "cleanup_foreign_tracks_default", True)
    video = tmp_path / "Movie.mkv"
    video.write_bytes(b"v")
    SubtitleAutomationQueueRepository().enqueue(
        wanted_item_id=0,
        file_path=str(video),
        target_language="en",
        task_type=SubtitleAutomationQueueEntry.TASK_FOREIGN_TRACK_CLEANUP,
        radarr_movie_id=77,
    )

    with (
        patch("services.embedded_extractor.resolve_profile_for_item", return_value={}),
        patch("services.embedded_extractor.compute_keep_langs", return_value=set()),
        patch(
            "services.foreign_tracks.policy.resolve_policy", return_value=TrackPolicy()
        ) as resolve,
        patch("remux.remove_foreign_subtitle_streams", return_value=None),
    ):
        assert SubtitleAutomationRunner().process_one() is True

    resolve.assert_called_once_with(series_id=None, movie_id=77)
