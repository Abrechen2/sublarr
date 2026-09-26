"""Track variant policy resolution: global settings + series/movie overrides."""

from services.foreign_tracks.policy import policy_for_path, policy_from_settings, resolve_policy
from services.foreign_tracks.select import TrackPolicy


def test_global_settings_become_a_policy(app_ctx, monkeypatch):
    from config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "cleanup_track_variant_mode", "one_per_language")
    monkeypatch.setattr(s, "cleanup_sidecar_policy", "drop_if_real_sidecar")
    assert policy_from_settings(s) == TrackPolicy(
        mode="one_per_language", sidecar_policy="drop_if_real_sidecar"
    )


def test_series_override_is_resolved(app_ctx):
    from datetime import UTC, datetime

    from db.models.core import SeriesSettings
    from extensions import db

    db.session.add(
        SeriesSettings(sonarr_series_id=9, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.commit()
    assert resolve_policy(series_id=9).keep_sdh is True
    assert resolve_policy(series_id=10).keep_sdh is False


def test_longest_folder_prefix_wins():
    a = TrackPolicy(mode="one_per_language")
    b = TrackPolicy(keep_sdh=True)
    overrides = [("/media/Anime", a), ("/media/Anime/Show", b)]
    assert policy_for_path("/media/Anime/Show/S01/e1.mkv", overrides, TrackPolicy()) == b
    assert policy_for_path("/media/Anime/Other/e1.mkv", overrides, TrackPolicy()) == a
    assert policy_for_path("/media/Movies/x.mkv", overrides, TrackPolicy()) == TrackPolicy()


def test_a_sibling_folder_with_a_shared_prefix_does_not_match():
    a = TrackPolicy(mode="one_per_language")
    assert (
        policy_for_path("/media/Anime Two/x.mkv", [("/media/Anime", a)], TrackPolicy())
        == TrackPolicy()
    )


def test_resolution_failure_is_reported_as_none_not_the_global_policy(app_ctx, monkeypatch):
    """A broken override chain must never fall back to the global policy —
    that may strip more than the override asked for (final review I5)."""
    from datetime import UTC, datetime

    from db.models.core import SeriesSettings
    from extensions import db

    db.session.add(
        SeriesSettings(sonarr_series_id=11, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError("inheritance resolver exploded")

    import services.inheritance_resolver as inheritance_resolver

    monkeypatch.setattr(inheritance_resolver, "resolve_for_series", _boom)

    assert resolve_policy(series_id=11) is None


def test_override_paths_returns_no_pairs_and_complete_when_nothing_is_overridden(app_ctx):
    from services.foreign_tracks.policy import override_paths

    result = override_paths()
    assert result.pairs == []
    assert result.excluded == []
    assert result.complete is True


def test_override_paths_skips_a_failing_id_and_keeps_the_others(app_ctx, monkeypatch):
    """One Sonarr lookup failure must log a warning, mark the whole
    resolution incomplete (a caller must not trust it for stripping), and
    still not abort the sweep for the remaining overridden series."""
    from datetime import UTC, datetime

    import sonarr_client
    from db.models.core import SeriesSettings
    from extensions import db
    from services.foreign_tracks.policy import override_paths

    db.session.add(
        SeriesSettings(sonarr_series_id=21, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.add(
        SeriesSettings(sonarr_series_id=22, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.commit()

    class _FakeClient:
        def lookup_series(self, series_id):
            if series_id == 21:
                raise RuntimeError("Sonarr is down")
            return 200, {"path": "/media/Anime/Show22"}

    monkeypatch.setattr(sonarr_client, "get_sonarr_client", lambda *a, **k: _FakeClient())

    result = override_paths()
    paths = [p for p, _ in result.pairs]
    assert any(p.endswith("Show22") for p in paths)
    assert len(result.pairs) == 1
    assert result.complete is False
    assert result.failed == ("series 21",)


def test_override_paths_is_incomplete_when_the_client_is_not_configured(app_ctx, monkeypatch):
    """`get_sonarr_client()` returns None (falsy) when Sonarr isn't
    configured — this must be treated the same as a raising lookup, not
    silently skipped."""
    from datetime import UTC, datetime

    import sonarr_client
    from db.models.core import SeriesSettings
    from extensions import db
    from services.foreign_tracks.policy import override_paths

    db.session.add(
        SeriesSettings(sonarr_series_id=31, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.commit()

    monkeypatch.setattr(sonarr_client, "get_sonarr_client", lambda *a, **k: None)

    result = override_paths()
    assert result.pairs == []
    assert result.complete is False


def test_override_paths_is_incomplete_when_no_path_comes_back_unconfirmed(app_ctx, monkeypatch):
    """A client that returns no path while its arr cannot confirm it is
    reachable (no/failed health check) is as unusable as one that raises —
    the arr clients return None on connection errors. A confirmed-missing
    title is covered in test_track_policy_resolution_errors.py (final
    review I4)."""
    from datetime import UTC, datetime

    import radarr_client
    from db.models.core import MovieSettings
    from extensions import db
    from services.foreign_tracks.policy import override_paths

    db.session.add(
        MovieSettings(radarr_movie_id=41, cleanup_keep_sdh=True, updated_at=datetime.now(UTC))
    )
    db.session.commit()

    class _FakeClient:
        def lookup_movie(self, movie_id):
            return 200, {}  # an answer without a "path" key

    monkeypatch.setattr(radarr_client, "get_radarr_client", lambda *a, **k: _FakeClient())

    result = override_paths()
    assert result.pairs == []
    assert result.complete is False
