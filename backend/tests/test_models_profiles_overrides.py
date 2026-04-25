"""ORM-level tests for the new override fields."""
from __future__ import annotations

from datetime import datetime, timezone

from db.models.core import SeriesSettings, MovieSettings


def test_series_settings_has_override_attrs():
    ss = SeriesSettings(
        sonarr_series_id=1,
        updated_at=datetime.now(timezone.utc),
    )
    assert hasattr(ss, "forced_preference_override")
    assert ss.forced_preference_override is None
    assert hasattr(ss, "hi_preference_override")
    assert hasattr(ss, "audio_exclude_languages_override")


def test_movie_settings_constructible():
    ms = MovieSettings(
        radarr_movie_id=42,
        updated_at=datetime.now(timezone.utc),
    )
    assert ms.radarr_movie_id == 42
    assert ms.cleanup_foreign_tracks is None
    assert ms.min_attempts_per_day == 0
    assert ms.forced_preference_override is None


def test_movie_settings_in_models_all():
    from db.models import core
    assert "MovieSettings" in core.__all__
