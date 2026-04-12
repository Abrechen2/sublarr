"""Tests for services/wanted_item_scanner.py — per-item scanning logic."""

import os
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# _check_language_for_item
# ---------------------------------------------------------------------------


def test_check_language_returns_none_when_existing_ass():
    """Already have an ASS file -- no action needed."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    with patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="ass"):
        result = _check_language_for_item("/media/ep.mkv", "de", None, settings)
    assert result is None


def test_check_language_returns_none_srt_no_upgrade():
    """SRT exists but upgrades disabled -- skip."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    with patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="srt"):
        result = _check_language_for_item("/media/ep.mkv", "de", None, settings)
    assert result is None


def test_check_language_returns_none_target_audio():
    """Target language audio detected -- skip."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    probe = {"streams": []}
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.has_target_language_audio", return_value=True),
    ):
        result = _check_language_for_item("/media/ep.mkv", "de", probe, settings)
    assert result is None


def test_check_language_embedded_ass_detected():
    """Embedded ASS stream sets existing_sub to 'embedded_ass'."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    probe = {"streams": []}
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.has_target_language_audio", return_value=False),
        patch("services.wanted_item_scanner.has_target_language_stream", return_value="ass"),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=["en"]),
    ):
        result = _check_language_for_item("/media/ep.mkv", "de", probe, settings)
    assert result is not None
    assert result["existing_sub"] == "embedded_ass"
    assert result["embedded_languages"] == ["en"]


def test_check_language_embedded_srt_detected():
    """Embedded SRT stream sets existing_sub to 'embedded_srt'."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    probe = {"streams": []}
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.has_target_language_audio", return_value=False),
        patch("services.wanted_item_scanner.has_target_language_stream", return_value="srt"),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
    ):
        result = _check_language_for_item("/media/ep.mkv", "de", probe, settings)
    assert result is not None
    assert result["existing_sub"] == "embedded_srt"


def test_check_language_upgrade_candidate():
    """SRT with upgrade enabled and file exists -> upgrade_candidate=True."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=True)
    with (
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value="srt"),
        patch(
            "services.wanted_item_scanner.get_output_path_for_lang", return_value="/media/ep.de.srt"
        ),
        patch("os.path.exists", return_value=True),
        patch("services.wanted_item_scanner.score_existing_subtitle", return_value=("srt", 65)),
        patch("services.wanted_item_scanner.get_all_subtitle_streams", return_value=[]),
    ):
        result = _check_language_for_item("/media/ep.mkv", "de", None, settings)
    assert result is not None
    assert result["upgrade_candidate"] is True
    assert result["current_score"] == 65


def test_check_language_no_existing_returns_empty_sub():
    """No existing subtitle at all -> existing_sub=''."""
    from services.wanted_item_scanner import _check_language_for_item

    settings = MagicMock(upgrade_enabled=False)
    with patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None):
        result = _check_language_for_item("/media/ep.mkv", "de", None, settings)
    assert result is not None
    assert result["existing_sub"] == ""
    assert result["upgrade_candidate"] is False
    assert result["current_score"] == 0


# ---------------------------------------------------------------------------
# batch_probe
# ---------------------------------------------------------------------------


def test_batch_probe_returns_results():
    from services.wanted_item_scanner import batch_probe

    fake_data = {"streams": []}
    with (
        patch(
            "services.wanted_item_scanner.get_settings",
            return_value=MagicMock(scan_metadata_max_workers=2),
        ),
        patch("services.wanted_item_scanner.get_media_streams", return_value=fake_data),
    ):
        results = batch_probe(["/a.mkv", "/b.mkv"])
    assert len(results) == 2
    assert results["/a.mkv"] == fake_data


def test_batch_probe_handles_errors():
    from services.wanted_item_scanner import batch_probe

    with (
        patch(
            "services.wanted_item_scanner.get_settings",
            return_value=MagicMock(scan_metadata_max_workers=1),
        ),
        patch(
            "services.wanted_item_scanner.get_media_streams", side_effect=RuntimeError("probe fail")
        ),
    ):
        results = batch_probe(["/bad.mkv"])
    assert results["/bad.mkv"] is None


# ---------------------------------------------------------------------------
# scan_radarr_movie
# ---------------------------------------------------------------------------


def test_scan_radarr_movie_no_file():
    """Movie without hasFile returns zeros."""
    from services.wanted_item_scanner import scan_radarr_movie

    radarr = MagicMock()
    settings = MagicMock()
    movie = {"hasFile": False, "id": 1, "title": "Test"}
    added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    assert added == 0
    assert updated == 0
    assert len(paths) == 0


def test_scan_radarr_movie_no_path():
    """Movie with hasFile but no file_path returns zeros."""
    from services.wanted_item_scanner import scan_radarr_movie

    radarr = MagicMock()
    radarr.get_movie_file.return_value = None
    settings = MagicMock()
    movie = {"hasFile": True, "id": 1, "title": "Test", "movieFile": None, "movieFileId": 0}
    added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    assert added == 0


def test_scan_radarr_movie_path_does_not_exist():
    """Movie file path that doesn't exist on disk returns zeros."""
    from services.wanted_item_scanner import scan_radarr_movie

    radarr = MagicMock()
    settings = MagicMock()
    movie = {
        "hasFile": True,
        "id": 1,
        "title": "Test",
        "movieFile": {"path": "/nonexistent/movie.mkv"},
    }
    with patch("services.wanted_item_scanner.map_path", return_value="/nonexistent/movie.mkv"):
        added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    assert added == 0


def test_scan_radarr_movie_adds_wanted_item(tmp_path):
    """Full happy path: movie file exists and is added as wanted."""
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    radarr = MagicMock()
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )
    movie = {
        "hasFile": True,
        "id": 42,
        "title": "My Movie",
        "movieFile": {"path": mapped},
    }

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    assert added == 1
    assert updated == 0
    assert mapped in paths


def test_scan_radarr_movie_forced_subtitle(tmp_path):
    """Forced subtitle preference 'separate' creates additional wanted item."""
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    radarr = MagicMock()
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )
    movie = {
        "hasFile": True,
        "id": 42,
        "title": "My Movie",
        "movieFile": {"path": mapped},
    }

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "separate",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    # One normal + one forced
    assert added == 2


def test_scan_radarr_movie_updates_existing(tmp_path):
    """When upsert returns was_updated=True, increments updated counter."""
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    radarr = MagicMock()
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )
    movie = {
        "hasFile": True,
        "id": 42,
        "title": "My Movie",
        "movieFile": {"path": mapped},
    }

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, True)),
    ):
        added, updated, paths = scan_radarr_movie(radarr, movie, settings)
    assert added == 0
    assert updated == 1


def test_scan_radarr_movie_auto_extract_called(tmp_path):
    """When embedded sub found and auto_extract_fn provided, it is called."""
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    radarr = MagicMock()
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )
    movie = {
        "hasFile": True,
        "id": 42,
        "title": "My Movie",
        "movieFile": {"path": mapped},
    }

    extract_fn = MagicMock()

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch(
            "services.wanted_item_scanner._check_language_for_item",
            return_value={
                "existing_sub": "embedded_ass",
                "embedded_languages": ["en"],
                "upgrade_candidate": False,
                "current_score": 0,
            },
        ),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(99, False)),
    ):
        scan_radarr_movie(radarr, movie, settings, auto_extract_fn=extract_fn)
    extract_fn.assert_called_once_with(99, mapped)


def test_scan_radarr_movie_fallback_movie_file_lookup(tmp_path):
    """Movie uses movieFileId fallback when movieFile is None."""
    from services.wanted_item_scanner import scan_radarr_movie

    video = tmp_path / "movie.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    radarr = MagicMock()
    radarr.get_movie_file.return_value = {"path": mapped}
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )
    movie = {
        "hasFile": True,
        "id": 42,
        "title": "Fallback Movie",
        "movieFile": None,
        "movieFileId": 7,
    }

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_movie_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, _, _ = scan_radarr_movie(radarr, movie, settings)
    assert added == 1
    radarr.get_movie_file.assert_called_once_with(7)


# ---------------------------------------------------------------------------
# scan_sonarr_series
# ---------------------------------------------------------------------------


def test_scan_sonarr_series_no_episodes():
    """No episodes returns zeros."""
    from services.wanted_item_scanner import scan_sonarr_series

    sonarr = MagicMock()
    sonarr.get_series_by_id.return_value = {"title": "Series"}
    sonarr.get_episodes.return_value = []
    settings = MagicMock()
    added, updated, paths = scan_sonarr_series(sonarr, 1, settings)
    assert added == 0 and updated == 0 and len(paths) == 0


def test_scan_sonarr_series_episode_no_file():
    """Episodes without hasFile are skipped."""
    from services.wanted_item_scanner import scan_sonarr_series

    sonarr = MagicMock()
    sonarr.get_episodes.return_value = [{"hasFile": False, "id": 1}]
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
    )
    with patch(
        "services.wanted_item_scanner.get_series_profile",
        return_value={
            "target_languages": ["de"],
            "target_language_names": ["German"],
            "forced_preference": "disabled",
        },
    ):
        added, updated, paths = scan_sonarr_series(sonarr, 1, settings, series_info={"title": "S"})
    assert added == 0


def test_scan_sonarr_series_adds_wanted_item(tmp_path):
    """Happy path: episode with file is added as wanted."""
    from services.wanted_item_scanner import scan_sonarr_series

    video = tmp_path / "ep01.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    sonarr = MagicMock()
    sonarr.get_episodes.return_value = [
        {
            "hasFile": True,
            "id": 10,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "episodeFile": {"path": mapped},
        }
    ]
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_series_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, updated, paths = scan_sonarr_series(
            sonarr, 1, settings, series_info={"title": "Test Series"}
        )
    assert added == 1
    assert mapped in paths


def test_scan_sonarr_series_multi_language(tmp_path):
    """Multiple target languages generate multiple wanted items."""
    from services.wanted_item_scanner import scan_sonarr_series

    video = tmp_path / "ep01.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    sonarr = MagicMock()
    sonarr.get_episodes.return_value = [
        {
            "hasFile": True,
            "id": 10,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "episodeFile": {"path": mapped},
        }
    ]
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_series_profile",
            return_value={
                "target_languages": ["de", "fr"],
                "target_language_names": ["German", "French"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, updated, paths = scan_sonarr_series(
            sonarr, 1, settings, series_info={"title": "Test Series"}
        )
    assert added == 2


def test_scan_sonarr_series_uses_fallback_path(tmp_path):
    """When episodeFile is None, uses sonarr.get_episode_file_path fallback."""
    from services.wanted_item_scanner import scan_sonarr_series

    video = tmp_path / "ep01.mkv"
    video.write_bytes(b"\x00" * 100)
    mapped = str(video)

    sonarr = MagicMock()
    sonarr.get_episodes.return_value = [
        {
            "hasFile": True,
            "id": 10,
            "seasonNumber": 1,
            "episodeNumber": 1,
            "episodeFile": None,
        }
    ]
    sonarr.get_episode_file_path.return_value = mapped
    settings = MagicMock(
        target_language="de",
        target_language_name="German",
        use_embedded_subs=False,
        upgrade_enabled=False,
    )

    with (
        patch("services.wanted_item_scanner.map_path", return_value=mapped),
        patch(
            "services.wanted_item_scanner.get_series_profile",
            return_value={
                "target_languages": ["de"],
                "target_language_names": ["German"],
                "forced_preference": "disabled",
            },
        ),
        patch("services.wanted_item_scanner.detect_existing_target_for_lang", return_value=None),
        patch("services.wanted_item_scanner.upsert_wanted_item", return_value=(1, False)),
    ):
        added, _, _ = scan_sonarr_series(sonarr, 1, settings, series_info={"title": "Series"})
    assert added == 1
    sonarr.get_episode_file_path.assert_called_once_with(10)
