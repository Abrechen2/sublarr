"""Unit tests for SubliminalProviderAdapter."""

import pytest

import providers._vendor  # noqa: F401 — trigger sys.path shim at test-collection time

from providers.base import SubtitleProvider


def test_adapter_is_a_sublarr_provider():
    """SubliminalProviderAdapter must be a subclass of Sublarr's SubtitleProvider."""
    from providers.subliminal_adapter import SubliminalProviderAdapter

    assert issubclass(SubliminalProviderAdapter, SubtitleProvider)


def test_adapter_constructor_accepts_provider_class():
    """Constructor takes a Subliminal Provider class + Sublarr config kwargs."""
    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="test",
        password="test",
    )
    assert adapter.name == "opensubtitles_subliminal"
    assert adapter._subliminal_provider_cls is OpenSubtitlesProvider


def test_convert_episode_query_to_subliminal_episode():
    """A Sublarr VideoQuery for an episode becomes a subliminal.video.Episode."""
    from providers.base import VideoQuery
    from providers.subliminal_adapter import _to_subliminal_video
    from subliminal.video import Episode

    q = VideoQuery(
        file_path="/media/Show/S01E05.mkv",
        series_title="My Show",
        season=1,
        episode=5,
        release_group="GROUP",
        source="BluRay",
        resolution="1080p",
        video_codec="x264",
        year=2020,
    )
    v = _to_subliminal_video(q)
    assert isinstance(v, Episode)
    assert v.series == "My Show"
    assert v.season == 1
    assert v.episode == 5
    assert v.release_group == "GROUP"
    assert v.source == "BluRay"
    assert v.resolution == "1080p"


def test_convert_movie_query_to_subliminal_movie():
    """A Sublarr VideoQuery for a movie becomes a subliminal.video.Movie."""
    from providers.base import VideoQuery
    from providers.subliminal_adapter import _to_subliminal_video
    from subliminal.video import Movie

    q = VideoQuery(
        file_path="/media/Frozen.2013.mkv",
        title="Frozen",
        year=2013,
        release_group="DON",
        source="BluRay",
        resolution="720p",
    )
    v = _to_subliminal_video(q)
    assert isinstance(v, Movie)
    assert v.title == "Frozen"
    assert v.year == 2013
    assert v.release_group == "DON"
