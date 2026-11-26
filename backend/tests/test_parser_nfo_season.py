"""Season and episode from NFO files and season folders (GitHub #257).

parse_media_file read only the filename, so "Season 9/Show - 05.mkv" came out
without a season and was listed as E05, even when an episode NFO named the
season and episode. Order now: episode NFO, season.nfo, season folder name,
then guessit's own result.
"""

from pathlib import Path

import pytest

from standalone.parser import _cached_guess, parse_media_file


@pytest.fixture(autouse=True)
def _clear_guess_cache():
    _cached_guess.cache_clear()
    yield
    _cached_guess.cache_clear()


def _video(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"")
    return path


def _episode_nfo(video: Path, season: int, episode: int) -> None:
    video.with_suffix(".nfo").write_text(
        "<?xml version='1.0' encoding='UTF-8'?>"
        f"<episodedetails><title>X</title><season>{season}</season>"
        f"<episode>{episode}</episode></episodedetails>",
        encoding="utf-8",
    )


def test_episode_nfo_gives_season_and_episode(tmp_path):
    video = _video(tmp_path / "Alien Earth" / "Season 1", "Alien Earth - 01.mkv")
    _episode_nfo(video, 1, 1)

    parsed = parse_media_file(str(video))

    assert (parsed["season"], parsed["episode"]) == (1, 1)


def test_episode_nfo_wins_over_the_filename(tmp_path):
    video = _video(tmp_path / "Show" / "Season 2", "Show.S01E03.mkv")
    _episode_nfo(video, 2, 7)

    parsed = parse_media_file(str(video))

    assert (parsed["season"], parsed["episode"]) == (2, 7)
    assert parsed["episodes"] == [7]


@pytest.mark.parametrize(
    ("folder", "season"),
    [("Season 9", 9), ("Season 09", 9), ("Staffel 3", 3), ("S04", 4), ("Specials", 0)],
)
def test_season_folder_fills_a_missing_season(tmp_path, folder, season):
    video = _video(tmp_path / "Show" / folder, "Show - 05.mkv")

    parsed = parse_media_file(str(video))

    assert (parsed["season"], parsed["episode"]) == (season, 5)


def test_season_nfo_fills_a_missing_season(tmp_path):
    folder = tmp_path / "Show" / "Disc A"
    video = _video(folder, "Show - 05.mkv")
    (folder / "season.nfo").write_text(
        "<season><seasonnumber>6</seasonnumber></season>", encoding="utf-8"
    )

    assert parse_media_file(str(video))["season"] == 6


def test_season_from_the_filename_is_kept_without_nfo(tmp_path):
    video = _video(tmp_path / "Show" / "Season 9", "Show.S02E05.mkv")

    assert parse_media_file(str(video))["season"] == 2


def test_malformed_episode_nfo_falls_back_to_the_folder(tmp_path):
    video = _video(tmp_path / "Show" / "Season 3", "Show - 05.mkv")
    video.with_suffix(".nfo").write_text("<episodedetails><season>", encoding="utf-8")

    parsed = parse_media_file(str(video))

    assert (parsed["season"], parsed["episode"]) == (3, 5)


def test_unrelated_folder_name_does_not_invent_a_season(tmp_path):
    video = _video(tmp_path / "Show", "Show - 05.mkv")

    assert parse_media_file(str(video))["season"] is None


def test_anime_keeps_its_absolute_episode_with_a_season_folder(tmp_path):
    video = _video(tmp_path / "Anime" / "Season 1", "[SubsPlease] Anime - 153.mkv")

    parsed = parse_media_file(str(video))

    assert parsed["absolute_episode"] == 153
    assert parsed["season"] == 1
