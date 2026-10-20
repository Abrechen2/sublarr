"""A media server path mapping can hold several pairs.

A server that mounts each library under its own root, such as Plex with
``/media/tv`` as ``/data/tv`` and ``/media/movies`` as ``/data/films``, cannot
be described by one ``from:to`` pair. With one pair, every subtitle for the
unmapped library missed the partial scan and fell back to a full scan of
that library. Pairs are separated by ``;`` and the longest matching
``from_path`` is applied.
"""

from unittest.mock import MagicMock, patch

import pytest

from mediaserver.plex import PlexServer

TWO_ROOTS = "/media/tv:/data/tv;/media/movies:/data/films"


def _mapper(path_mapping):
    return PlexServer(url="http://plex", token="t", path_mapping=path_mapping)


@pytest.mark.parametrize(
    "mapping, path, expected",
    [
        # One pair keeps its old behaviour.
        ("/media:/data", "/media/tv/Show/ep.mkv", "/data/tv/Show/ep.mkv"),
        ("/media:/data", "/other/ep.mkv", "/other/ep.mkv"),
        ("", "/media/tv/Show/ep.mkv", "/media/tv/Show/ep.mkv"),
        # Each pair maps its own root.
        (TWO_ROOTS, "/media/tv/Show/ep.mkv", "/data/tv/Show/ep.mkv"),
        (TWO_ROOTS, "/media/movies/Film (2020)/Film.mkv", "/data/films/Film (2020)/Film.mkv"),
        (TWO_ROOTS, "/media/music/song.flac", "/media/music/song.flac"),
        # Spaces around pairs and a trailing separator are ignored.
        (
            " /media/tv:/data/tv ; /media/movies:/data/films ;",
            "/media/movies/F/F.mkv",
            "/data/films/F/F.mkv",
        ),
    ],
)
def test_maps_each_path_with_its_own_pair(mapping, path, expected):
    assert _mapper(mapping).apply_path_mapping(path) == expected


@pytest.mark.parametrize(
    "mapping",
    ["/media:/data;/media/anime:/anime", "/media/anime:/anime;/media:/data"],
)
def test_the_longest_matching_pair_wins_in_any_order(mapping):
    mapper = _mapper(mapping)
    assert mapper.apply_path_mapping("/media/anime/Show/ep.mkv") == "/anime/Show/ep.mkv"
    assert mapper.apply_path_mapping("/media/tv/Show/ep.mkv") == "/data/tv/Show/ep.mkv"


def _section(kind, title, *locations):
    return MagicMock(type=kind, title=title, locations=list(locations))


def test_a_second_library_root_gets_a_partial_scan_not_a_full_one():
    movies = _section("movie", "Movies", "/data/films")
    tv = _section("show", "TV Shows", "/data/tv")
    server = MagicMock()
    server.library.sections.return_value = [movies, tv]
    backend = _mapper(TWO_ROOTS)
    with patch.object(backend, "_get_server", return_value=server):
        result = backend.refresh_item("/media/movies/Film (2020)/Film.mkv", "movie")

    assert result.success
    movies.update.assert_called_once_with(path="/data/films/Film (2020)")
    tv.update.assert_not_called()


@pytest.mark.parametrize(
    "mapping, path, expected",
    [
        # A from_path is a folder: "/media/movies" is not a prefix of "/media/movies-4k".
        (TWO_ROOTS, "/media/movies-4k/F/F.mkv", "/media/movies-4k/F/F.mkv"),
        (
            "/media/movies:/data/films;/media:/data",
            "/media/movies-4k/F.mkv",
            "/data/movies-4k/F.mkv",
        ),
        # The folder itself, a trailing slash on from_path, and Windows separators.
        ("/media/tv:/data/tv", "/media/tv", "/data/tv"),
        ("/media/tv/:/data/tv/", "/media/tv/Show/ep.mkv", "/data/tv/Show/ep.mkv"),
        # A trailing slash on one side only still joins at the separator.
        ("/media/tv/:/data/tv", "/media/tv/Show/ep.mkv", "/data/tv/Show/ep.mkv"),
        ("/media/tv:/data/tv/", "/media/tv/Show/ep.mkv", "/data/tv/Show/ep.mkv"),
        ("/:/data", "/media/ep.mkv", "/data/media/ep.mkv"),
        ("D\\Media:/data", "D\\Media\\Show\\ep.mkv", "/data\\Show\\ep.mkv"),
    ],
)
def test_a_from_path_only_matches_whole_folders(mapping, path, expected):
    assert _mapper(mapping).apply_path_mapping(path) == expected
