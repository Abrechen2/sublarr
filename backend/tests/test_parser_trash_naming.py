"""Filenames from the TRaSH Guides naming schemes (Forgejo #83).

Many Sonarr/Radarr users rename with the TRaSH schemes
(docs/json/{sonarr,radarr}/naming in TRaSH-Guides/Guides). The release group
matters for subtitle scoring, so it must survive the bracket tokens.

Episode: {Series CleanTitleWithoutYear} {(Series Year)} - S{season:00}E{episode:00}
         - {Episode CleanTitle:90} {[Custom Formats]}{[Quality Full]}{[Mediainfo
         AudioCodec}{ Mediainfo AudioChannels]}{[MediaInfo VideoDynamicRangeType]}
         {[Mediainfo VideoCodec]}{-Release Group}
Anime:   ... - S{season:00}E{episode:00} - {absolute:000} - {Episode CleanTitle:90}
         ... {[MediaInfo AudioLanguages]}[{Mediainfo VideoCodec }{MediaInfo
         VideoBitDepth}bit]{-Release Group}
Movie:   {Movie CleanTitle} {(Release Year)} - {{Edition Tags}} {[MediaInfo 3D]}
         {[Custom Formats]}{[Quality Full]}...{-Release Group}
"""

import pytest

from standalone.parser import _cached_guess, parse_media_file


@pytest.fixture(autouse=True)
def _clear_guess_cache():
    _cached_guess.cache_clear()
    yield
    _cached_guess.cache_clear()


ANIME = (
    "/anime/Frieren (2023)/Season 01/Frieren (2023) - S01E05 - 005 - Phantoms of the Dead "
    "[Bluray-1080p][FLAC 2.0][JA][x265 10bit]-Vodes.mkv"
)
MOVIE = (
    "/movies/Dune Part Two (2024) {tmdb-693134}/Dune Part Two (2024) {edition-IMAX} "
    "[IMAX Enhanced][Remux-2160p][TrueHD Atmos 7.1][DV HDR10][HEVC]-FraMeSToR.mkv"
)


def test_anime_scheme_keeps_the_release_group():
    assert parse_media_file(ANIME)["release_group"] == "Vodes"


def test_anime_scheme_reads_the_absolute_episode():
    parsed = parse_media_file(ANIME)

    assert (parsed["season"], parsed["episode"]) == (1, 5)
    assert parsed["absolute_episode"] == 5


def test_movie_scheme_keeps_part_two_in_the_title():
    parsed = parse_media_file(MOVIE)

    assert parsed["type"] == "movie"
    assert parsed["title"] == "Dune Part Two"
    assert parsed["year"] == 2024
    assert parsed["release_group"] == "FraMeSToR"


def test_remux_counts_as_blu_ray_source():
    assert parse_media_file(MOVIE)["source"] == "Blu-ray"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/tv/The Office (2005) {tvdb-73244}/Season 02/The Office (2005) - S02E05 - "
            "Halloween [AMZN WEBDL-1080p Proper][EAC3 5.1][h264]-NTb.mkv",
            ("The Office", 2, 5, "NTb", "Web", "1080p"),
        ),
        (
            "/tv/Severance (2022)/Season 01/Severance (2022) - S01E01 - Good News About Hell "
            "[ATVP][WEBDL-2160p][EAC3 Atmos 5.1][DV HDR10][h265]-FLUX.mkv",
            ("Severance", 1, 1, "FLUX", "Web", "2160p"),
        ),
        (
            "/tv/Show (2020)/Season 01/Show (2020) - S01E02 - Title [HDTV-720p][x264 10bit]-GRP.mkv",
            ("Show", 1, 2, "GRP", "HDTV", "720p"),
        ),
    ],
)
def test_series_scheme(path, expected):
    p = parse_media_file(path)

    assert (
        p["title"],
        p["season"],
        p["episode"],
        p["release_group"],
        p["source"],
        p["resolution"],
    ) == expected


def test_movie_without_part_keeps_the_guessit_title():
    p = parse_media_file("/movies/Arrival (2016)/Arrival (2016) [Bluray-1080p][x264]-SPARKS.mkv")

    assert (p["title"], p["year"], p["release_group"]) == ("Arrival", 2016, "SPARKS")


def test_scene_name_without_trash_brackets_is_unchanged():
    p = parse_media_file("/tv/Show/Show.S01E02.1080p.WEB.h264-GROUP.mkv")

    assert (p["title"], p["season"], p["episode"], p["release_group"]) == ("Show", 1, 2, "GROUP")
    assert p["absolute_episode"] is None
