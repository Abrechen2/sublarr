"""Task 6: post-download, batch-probe and executor paths apply the track policy.

Covers ``maybe_run_foreign_track_cleanup`` resolving the series/movie policy
itself (batch_probe and the automation runner both call the hook unchanged)
and, under policy B (``drop_if_real_sidecar``), looking up the real sidecar
languages before handing them to ``remux.remove_foreign_subtitle_streams``.
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
