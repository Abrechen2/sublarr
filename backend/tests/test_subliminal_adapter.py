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


def test_convert_subliminal_subtitle_to_sublarr_result():
    """A subliminal Subtitle becomes a SubtitleResult with mapped fields."""
    from babelfish import Language
    from providers.subliminal_adapter import _to_sublarr_result

    class _FakeSubtitle:
        """Stand-in for a Subliminal Subtitle (duck-typed)."""

        provider_name = "opensubtitles"
        id = "12345"
        language = Language("eng")
        hearing_impaired = True
        foreign_only = False
        release_group = "GROUP"
        fps = 23.976
        page_link = "https://example.com/12345"

    sub = _FakeSubtitle()
    result = _to_sublarr_result(sub, registered_name="opensubtitles_subliminal")

    assert result.provider_name == "opensubtitles_subliminal"
    assert result.subtitle_id == "12345"
    assert result.language == "en"
    assert result.hearing_impaired is True
    assert result.release_info == "GROUP"
    assert result.fps == 23.976
    assert result.download_url == "https://example.com/12345"


def test_adapter_search_delegates_to_subliminal_and_converts_results():
    """adapter.search() invokes the wrapped provider and converts each Subtitle."""
    from unittest.mock import MagicMock
    from babelfish import Language
    from providers.base import VideoQuery
    from providers.subliminal_adapter import SubliminalProviderAdapter

    class _FakeSubtitle:
        provider_name = "opensubtitles"
        id = "sub1"
        language = Language("eng")
        hearing_impaired = False
        foreign_only = False
        release_group = "GRP"
        fps = None
        page_link = "url"
        filename = "f.srt"

    fake_impl = MagicMock()
    fake_impl.list_subtitles.return_value = [_FakeSubtitle(), _FakeSubtitle()]

    FakeProviderCls = MagicMock(return_value=fake_impl)

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=FakeProviderCls,
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    query = VideoQuery(
        file_path="/media/Show/S01E01.mkv",
        series_title="Show",
        season=1,
        episode=1,
        languages=["en"],
    )
    results = adapter.search(query)

    assert len(results) == 2
    assert all(r.provider_name == "opensubtitles_subliminal" for r in results)
    assert fake_impl.list_subtitles.called
    # First positional arg must be a subliminal.video.Video
    from subliminal.video import Video as _Video

    video_arg = fake_impl.list_subtitles.call_args.args[0]
    assert isinstance(video_arg, _Video)
    # Second positional arg must be a set of Language objects
    langs_arg = fake_impl.list_subtitles.call_args.args[1]
    assert Language("eng") in langs_arg


def test_adapter_search_empty_languages_returns_empty_list():
    """If the query requests no languages we return [] without calling Subliminal."""
    from unittest.mock import MagicMock
    from providers.base import VideoQuery
    from providers.subliminal_adapter import SubliminalProviderAdapter

    fake_impl = MagicMock()
    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=MagicMock(return_value=fake_impl),
        provider_name="opensubtitles_subliminal",
    )
    adapter.initialize()

    results = adapter.search(VideoQuery(file_path="/x.mkv", title="X", languages=[]))
    assert results == []
    fake_impl.list_subtitles.assert_not_called()
