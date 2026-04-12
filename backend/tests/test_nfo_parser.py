"""Tests for standalone/nfo_parser.py — NFO sidecar file parsing."""

import os
import xml.etree.ElementTree as ET

import pytest

# ---------------------------------------------------------------------------
# Helper: write NFO files
# ---------------------------------------------------------------------------


def _write_nfo(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# _find_file
# ---------------------------------------------------------------------------


def test_find_file_returns_first_match(tmp_path):
    from standalone.nfo_parser import _find_file

    (tmp_path / "poster.jpg").write_bytes(b"\xff\xd8")
    result = _find_file(str(tmp_path), ("poster.jpg", "poster.png"))
    assert result is not None
    assert result.endswith("poster.jpg")


def test_find_file_returns_none_when_no_match(tmp_path):
    from standalone.nfo_parser import _find_file

    result = _find_file(str(tmp_path), ("poster.jpg",))
    assert result is None


# ---------------------------------------------------------------------------
# _text / _int_or_none helpers
# ---------------------------------------------------------------------------


def test_text_extracts_value():
    from standalone.nfo_parser import _text

    root = ET.fromstring("<root><title> My Show </title></root>")
    assert _text(root, "title") == "My Show"


def test_text_missing_tag_returns_default():
    from standalone.nfo_parser import _text

    root = ET.fromstring("<root></root>")
    assert _text(root, "title", "fallback") == "fallback"


def test_text_empty_tag_returns_default():
    from standalone.nfo_parser import _text

    root = ET.fromstring("<root><title></title></root>")
    assert _text(root, "title", "fallback") == "fallback"


def test_int_or_none_valid():
    from standalone.nfo_parser import _int_or_none

    assert _int_or_none("42") == 42


def test_int_or_none_invalid():
    from standalone.nfo_parser import _int_or_none

    assert _int_or_none("abc") is None


def test_int_or_none_none():
    from standalone.nfo_parser import _int_or_none

    assert _int_or_none(None) is None


# ---------------------------------------------------------------------------
# _parse_genres / _is_anime_from_genres
# ---------------------------------------------------------------------------


def test_parse_genres():
    from standalone.nfo_parser import _parse_genres

    root = ET.fromstring("<root><genre>Action</genre><genre>Anime</genre></root>")
    genres = _parse_genres(root)
    assert genres == ["Action", "Anime"]


def test_parse_genres_empty():
    from standalone.nfo_parser import _parse_genres

    root = ET.fromstring("<root></root>")
    assert _parse_genres(root) == []


def test_is_anime_from_genres_true():
    from standalone.nfo_parser import _is_anime_from_genres

    assert _is_anime_from_genres(["Action", "Anime"]) is True


def test_is_anime_from_genres_false():
    from standalone.nfo_parser import _is_anime_from_genres

    assert _is_anime_from_genres(["Action", "Drama"]) is False


def test_is_anime_from_genres_case_insensitive():
    from standalone.nfo_parser import _is_anime_from_genres

    assert _is_anime_from_genres(["ANIME"]) is True


# ---------------------------------------------------------------------------
# _parse_unique_ids
# ---------------------------------------------------------------------------


def test_parse_unique_ids():
    from standalone.nfo_parser import _parse_unique_ids

    root = ET.fromstring(
        '<root><uniqueid type="tvdb">12345</uniqueid><uniqueid type="imdb">tt999</uniqueid></root>'
    )
    ids = _parse_unique_ids(root)
    assert ids["tvdb"] == "12345"
    assert ids["imdb"] == "tt999"


def test_parse_unique_ids_empty():
    from standalone.nfo_parser import _parse_unique_ids

    root = ET.fromstring("<root></root>")
    assert _parse_unique_ids(root) == {}


# ---------------------------------------------------------------------------
# parse_series_nfo
# ---------------------------------------------------------------------------


def test_parse_series_nfo_basic(tmp_path):
    from standalone.nfo_parser import parse_series_nfo

    nfo_content = """<?xml version="1.0" encoding="UTF-8"?>
<tvshow>
    <title>My Anime</title>
    <year>2024</year>
    <tvdbid>12345</tvdbid>
    <tmdbid>67890</tmdbid>
    <genre>Anime</genre>
    <status>Continuing</status>
</tvshow>"""
    _write_nfo(str(tmp_path / "tvshow.nfo"), nfo_content)

    result = parse_series_nfo(str(tmp_path))
    assert result is not None
    assert result["title"] == "My Anime"
    assert result["year"] == 2024
    assert result["tvdb_id"] == 12345
    assert result["tmdb_id"] == 67890
    assert result["is_anime"] is True
    assert result["metadata_source"] == "nfo"


def test_parse_series_nfo_from_parent(tmp_path):
    """NFO in parent folder found when scanning Season subfolder."""
    from standalone.nfo_parser import parse_series_nfo

    nfo_content = "<tvshow><title>Parent Show</title><year>2023</year></tvshow>"
    _write_nfo(str(tmp_path / "tvshow.nfo"), nfo_content)

    season_dir = tmp_path / "Season 01"
    season_dir.mkdir()

    result = parse_series_nfo(str(season_dir))
    assert result is not None
    assert result["title"] == "Parent Show"


def test_parse_series_nfo_not_found(tmp_path):
    """Returns None when no tvshow.nfo exists."""
    from standalone.nfo_parser import parse_series_nfo

    result = parse_series_nfo(str(tmp_path))
    assert result is None


def test_parse_series_nfo_malformed_xml(tmp_path):
    """Returns None for malformed XML."""
    from standalone.nfo_parser import parse_series_nfo

    _write_nfo(str(tmp_path / "tvshow.nfo"), "<broken><unclosed>")
    result = parse_series_nfo(str(tmp_path))
    assert result is None


def test_parse_series_nfo_with_uniqueids(tmp_path):
    """Unique IDs are extracted as fallback."""
    from standalone.nfo_parser import parse_series_nfo

    nfo_content = """<?xml version="1.0"?>
<tvshow>
    <title>ID Show</title>
    <uniqueid type="tvdb">111</uniqueid>
    <uniqueid type="imdb">tt222</uniqueid>
    <uniqueid type="anidb">333</uniqueid>
</tvshow>"""
    _write_nfo(str(tmp_path / "tvshow.nfo"), nfo_content)

    result = parse_series_nfo(str(tmp_path))
    assert result["tvdb_id"] == 111
    assert result["imdb_id"] == "tt222"
    # anidb_id presence means is_anime
    assert result["is_anime"] is True


def test_parse_series_nfo_with_poster(tmp_path):
    """Local poster is found alongside NFO."""
    from standalone.nfo_parser import parse_series_nfo

    _write_nfo(str(tmp_path / "tvshow.nfo"), "<tvshow><title>Poster Show</title></tvshow>")
    (tmp_path / "poster.jpg").write_bytes(b"\xff\xd8\xff")

    result = parse_series_nfo(str(tmp_path))
    assert result["local_poster"] is not None
    assert result["local_poster"].endswith("poster.jpg")


def test_parse_series_nfo_non_tvshow_root(tmp_path):
    """Handles NFO with non-standard root element wrapping tvshow."""
    from standalone.nfo_parser import parse_series_nfo

    nfo_content = "<metadata><tvshow><title>Wrapped</title><year>2025</year></tvshow></metadata>"
    _write_nfo(str(tmp_path / "tvshow.nfo"), nfo_content)

    result = parse_series_nfo(str(tmp_path))
    assert result is not None
    assert result["title"] == "Wrapped"


def test_parse_series_nfo_premiered_year(tmp_path):
    """Year extracted from <premiered> tag when <year> is missing."""
    from standalone.nfo_parser import parse_series_nfo

    nfo_content = "<tvshow><title>Premiere Show</title><premiered>2023-04-01</premiered></tvshow>"
    _write_nfo(str(tmp_path / "tvshow.nfo"), nfo_content)

    result = parse_series_nfo(str(tmp_path))
    assert result["year"] == 2023


# ---------------------------------------------------------------------------
# parse_movie_nfo
# ---------------------------------------------------------------------------


def test_parse_movie_nfo_basic(tmp_path):
    from standalone.nfo_parser import parse_movie_nfo

    nfo_content = """<?xml version="1.0"?>
<movie>
    <title>My Movie</title>
    <year>2025</year>
    <tmdbid>99999</tmdbid>
    <imdb_id>tt88888</imdb_id>
</movie>"""
    _write_nfo(str(tmp_path / "movie.nfo"), nfo_content)

    result = parse_movie_nfo(str(tmp_path))
    assert result is not None
    assert result["title"] == "My Movie"
    assert result["year"] == 2025
    assert result["tmdb_id"] == 99999
    assert result["imdb_id"] == "tt88888"
    assert result["metadata_source"] == "nfo"


def test_parse_movie_nfo_not_found(tmp_path):
    """Returns None when no movie.nfo exists."""
    from standalone.nfo_parser import parse_movie_nfo

    assert parse_movie_nfo(str(tmp_path)) is None


def test_parse_movie_nfo_malformed(tmp_path):
    """Returns None for malformed XML."""
    from standalone.nfo_parser import parse_movie_nfo

    _write_nfo(str(tmp_path / "movie.nfo"), "not xml at all <<<")
    assert parse_movie_nfo(str(tmp_path)) is None


def test_parse_movie_nfo_with_uniqueids(tmp_path):
    """Movie unique IDs are parsed."""
    from standalone.nfo_parser import parse_movie_nfo

    nfo_content = """<movie>
    <title>UID Movie</title>
    <uniqueid type="tmdb">555</uniqueid>
    <uniqueid type="imdb">tt666</uniqueid>
</movie>"""
    _write_nfo(str(tmp_path / "movie.nfo"), nfo_content)

    result = parse_movie_nfo(str(tmp_path))
    assert result["tmdb_id"] == 555
    assert result["imdb_id"] == "tt666"


def test_parse_movie_nfo_with_poster(tmp_path):
    """Local poster found for movie."""
    from standalone.nfo_parser import parse_movie_nfo

    _write_nfo(str(tmp_path / "movie.nfo"), "<movie><title>Poster Movie</title></movie>")
    (tmp_path / "poster.png").write_bytes(b"\x89PNG")

    result = parse_movie_nfo(str(tmp_path))
    assert result["local_poster"] is not None
    assert result["local_poster"].endswith("poster.png")


def test_parse_movie_nfo_non_movie_root(tmp_path):
    """Handles NFO with wrapper element."""
    from standalone.nfo_parser import parse_movie_nfo

    _write_nfo(
        str(tmp_path / "movie.nfo"),
        "<metadata><movie><title>Wrapped Movie</title></movie></metadata>",
    )
    result = parse_movie_nfo(str(tmp_path))
    assert result is not None
    assert result["title"] == "Wrapped Movie"


# ---------------------------------------------------------------------------
# find_local_poster
# ---------------------------------------------------------------------------


def test_find_local_poster_in_folder(tmp_path):
    from standalone.nfo_parser import find_local_poster

    (tmp_path / "poster.jpg").write_bytes(b"\xff")
    result = find_local_poster(str(tmp_path))
    assert result is not None
    assert result.endswith("poster.jpg")


def test_find_local_poster_in_parent(tmp_path):
    from standalone.nfo_parser import find_local_poster

    (tmp_path / "poster.jpg").write_bytes(b"\xff")
    child = tmp_path / "Season 01"
    child.mkdir()

    result = find_local_poster(str(child))
    assert result is not None


def test_find_local_poster_not_found(tmp_path):
    from standalone.nfo_parser import find_local_poster

    assert find_local_poster(str(tmp_path)) is None


def test_find_local_poster_prefers_poster_jpg(tmp_path):
    """poster.jpg is checked before folder.jpg."""
    from standalone.nfo_parser import find_local_poster

    (tmp_path / "folder.jpg").write_bytes(b"\xff")
    (tmp_path / "poster.jpg").write_bytes(b"\xff")
    result = find_local_poster(str(tmp_path))
    assert result.endswith("poster.jpg")
