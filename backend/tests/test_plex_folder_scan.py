"""Plex refreshes the folder that got the new subtitle, not every library (#219).

The old lookup searched each section with ``Media__Part__file__startswith``.
plexapi rejects any filter name containing ``__`` before it reaches Plex
(``BadRequest: Invalid filter field``), the error was logged at DEBUG, and
every subtitle fell back to a full scan of every section — movies included
for an episode. One reporter counted 491 full scans and 0 item refreshes.

Plex has a partial scan for exactly this: ``section.update(path=folder)``.
The section is the one whose root folder contains the file, so no search is
needed at all.
"""

from unittest.mock import MagicMock, patch

import pytest

from mediaserver.plex import PlexServer


def _section(kind, title, *locations):
    section = MagicMock(type=kind, title=title, locations=list(locations))
    return section


@pytest.fixture
def plex():
    movies = _section("movie", "Movies", "/data/media/movies")
    tv = _section("show", "TV Shows", "/data/media/tv")
    anime = _section("show", "Anime", "/data/media/anime", "/data/media/anime-archive")
    server = MagicMock()
    server.library.sections.return_value = [movies, tv, anime]
    return server, movies, tv, anime


def _backend(server, **config):
    backend = PlexServer(url="http://plex", token="t", **config)
    patcher = patch.object(backend, "_get_server", return_value=server)
    patcher.start()
    return backend, patcher


def test_scans_only_the_folder_of_the_file(plex):
    server, movies, tv, anime = plex
    backend, patcher = _backend(server)
    try:
        result = backend.refresh_item("/data/media/tv/Show/Season 1/ep.mkv", "episode")
    finally:
        patcher.stop()

    assert result.success
    tv.update.assert_called_once_with(path="/data/media/tv/Show/Season 1")
    movies.update.assert_not_called()
    anime.update.assert_not_called()


def test_matches_any_root_folder_of_a_section(plex):
    server, movies, tv, anime = plex
    backend, patcher = _backend(server)
    try:
        result = backend.refresh_item("/data/media/anime-archive/Show/ep.mkv", "episode")
    finally:
        patcher.stop()

    assert result.success
    anime.update.assert_called_once_with(path="/data/media/anime-archive/Show")
    tv.update.assert_not_called()


def test_a_sibling_folder_with_a_shared_prefix_is_not_a_match(plex):
    """``/data/media/tv2`` is not inside ``/data/media/tv``."""
    server, movies, tv, anime = plex
    backend, patcher = _backend(server)
    try:
        result = backend.refresh_item(
            "/data/media/tv2/Show/ep.mkv", "episode", library_fallback=False
        )
    finally:
        patcher.stop()

    assert result.needs_library_refresh
    tv.update.assert_not_called()


def test_path_mapping_is_applied_before_matching(plex):
    server, movies, tv, anime = plex
    backend, patcher = _backend(server, path_mapping="/media:/data/media")
    try:
        result = backend.refresh_item("/media/movies/Film (2020)/Film.mkv", "movie")
    finally:
        patcher.stop()

    assert result.success
    movies.update.assert_called_once_with(path="/data/media/movies/Film (2020)")


def test_a_miss_without_fallback_scans_nothing(plex):
    server, movies, tv, anime = plex
    backend, patcher = _backend(server)
    try:
        result = backend.refresh_item("/elsewhere/ep.mkv", "episode", library_fallback=False)
    finally:
        patcher.stop()

    assert not result.success
    assert result.needs_library_refresh
    for section in (movies, tv, anime):
        section.update.assert_not_called()


def test_the_fallback_scans_only_sections_of_the_matching_type(plex):
    server, movies, tv, anime = plex
    backend, patcher = _backend(server)
    try:
        result = backend.refresh_item("/elsewhere/ep.mkv", "episode")
    finally:
        patcher.stop()

    assert result.success
    tv.update.assert_called_once_with()
    anime.update.assert_called_once_with()
    movies.update.assert_not_called()


def test_a_failing_partial_scan_is_reported_not_swallowed(plex, caplog):
    server, movies, tv, anime = plex
    tv.update.side_effect = RuntimeError("Plex said no")
    backend, patcher = _backend(server)
    try:
        with caplog.at_level("WARNING", logger="mediaserver.plex"):
            result = backend.refresh_item("/data/media/tv/Show/ep.mkv", "episode")
    finally:
        patcher.stop()

    assert not result.success
    assert "Plex said no" in result.message
    assert any("Plex said no" in r.getMessage() for r in caplog.records)
