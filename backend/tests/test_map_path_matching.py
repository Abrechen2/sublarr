"""The *arr path mapping matches whole folders and prefers the longest pair.

Before 1.17.1 ``map_path`` took the first pair whose remote prefix was a plain
string prefix of the path: ``/data/movies=/mnt/movies`` also rewrote
``/data/movies-4k/...`` to ``/mnt/movies-4k/...``, a general pair listed first
shadowed a specific one, and a trailing slash on one side only glued the rest
of the path onto the folder name. The media server mapping already behaved
(1.17.0); this pins the same rules for Sonarr/Radarr paths.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config_utils import map_path


def _mapped(mapping: str, path: str) -> str:
    with patch("config.get_settings", return_value=SimpleNamespace(path_mapping=mapping)):
        return map_path(path)


@pytest.fixture(autouse=True)
def _posix(monkeypatch):
    monkeypatch.setattr("config_utils.os.name", "posix")


def test_a_single_pair_maps_as_before():
    assert _mapped("/data/tv=/mnt/tv", "/data/tv/Show/S01E01.mkv") == "/mnt/tv/Show/S01E01.mkv"


def test_a_pair_matches_whole_folders_only():
    assert (
        _mapped("/data/movies=/mnt/movies", "/data/movies-4k/Film/Film.mkv")
        == "/data/movies-4k/Film/Film.mkv"
    )


def test_the_longest_pair_wins_in_any_order():
    mapping = "/data=/mnt;/data/anime=/anime"
    assert _mapped(mapping, "/data/anime/Show/ep.mkv") == "/anime/Show/ep.mkv"
    assert _mapped(mapping, "/data/tv/Show/ep.mkv") == "/mnt/tv/Show/ep.mkv"


@pytest.mark.parametrize(
    "mapping", ["/data/tv/=/mnt/tv", "/data/tv=/mnt/tv/", "/data/tv/=/mnt/tv/"]
)
def test_a_trailing_slash_on_either_side_is_fine(mapping):
    assert _mapped(mapping, "/data/tv/Show/ep.mkv") == "/mnt/tv/Show/ep.mkv"


def test_the_folder_itself_maps():
    assert _mapped("/data/tv=/mnt/tv", "/data/tv") == "/mnt/tv"


def test_no_matching_pair_leaves_the_path():
    assert _mapped("/data/tv=/mnt/tv;broken;=/x", "/other/ep.mkv") == "/other/ep.mkv"


def test_windows_gets_backslashes(monkeypatch):
    monkeypatch.setattr("config_utils.os.name", "nt")
    assert _mapped("/data/tv=D:/tv", "/data/tv/Show/ep.mkv") == "D:\\tv\\Show\\ep.mkv"
