"""The wanted scan says so when Sonarr's files are not where Sublarr looks.

Discord install-help 2026-10-31: the wizard never saved the user's path
mapping, every Sonarr path pointed nowhere inside the container, and the scan
answered "+0 added" for nine series without a word about why — the episode
search found subtitles, but there was no wanted item to download them for.
"""

import logging
from unittest.mock import MagicMock, patch

from services.wanted_item_scanner import scan_radarr_movie, scan_sonarr_series

SETTINGS = MagicMock(target_language="de", target_language_name="German", use_embedded_subs=False)


def _sonarr(paths):
    client = MagicMock()
    client.get_episodes.return_value = [
        {"id": i, "hasFile": True, "episodeFile": {"path": p}} for i, p in enumerate(paths)
    ]
    return client


def _scan(client, caplog, exists):
    with (
        patch("services.wanted_item_scanner.get_series_profile", return_value={}),
        patch("services.wanted_item_scanner.os.path.exists", side_effect=exists),
        caplog.at_level(logging.WARNING, logger="services.wanted_item_scanner"),
    ):
        return scan_sonarr_series(client, 7, SETTINGS, series_info={"title": "Death Note"})


def test_a_series_whose_files_are_not_found_is_reported(caplog):
    client = _sonarr(
        ["/data/media/tv/Death Note/S01E01.mkv", "/data/media/tv/Death Note/S01E02.mkv"]
    )

    added, _, _ = _scan(client, caplog, exists=lambda p: False)

    assert added == 0
    [record] = [r for r in caplog.records if "Death Note" in r.getMessage()]
    assert "2 of 2" in record.getMessage()
    assert "/data/media/tv/Death Note/S01E01.mkv" in record.getMessage()
    assert "path mapping" in record.getMessage()


def test_a_series_whose_files_are_found_says_nothing(caplog):
    client = _sonarr(["/media/tv/Show/S01E01.mkv"])

    with patch("services.wanted_item_scanner._check_language_for_item", return_value=None):
        _scan(client, caplog, exists=lambda p: True)

    assert not [r for r in caplog.records if "path mapping" in r.getMessage()]


def test_a_movie_whose_file_is_not_found_is_reported(caplog):
    radarr = MagicMock()
    radarr.get_movie_by_id.return_value = {
        "title": "Akira",
        "movieFile": {"path": "/data/movies/Akira.mkv"},
    }
    radarr.get_movie_file_path.return_value = "/data/movies/Akira.mkv"
    movie = {
        "id": 3,
        "title": "Akira",
        "hasFile": True,
        "movieFile": {"path": "/data/movies/Akira.mkv"},
    }

    with (
        patch("services.wanted_item_scanner.os.path.exists", return_value=False),
        caplog.at_level(logging.WARNING, logger="services.wanted_item_scanner"),
    ):
        scan_radarr_movie(radarr, movie, SETTINGS)

    assert any(
        "Akira" in r.getMessage() and "path mapping" in r.getMessage() for r in caplog.records
    )
