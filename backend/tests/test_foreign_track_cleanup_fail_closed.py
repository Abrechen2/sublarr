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
