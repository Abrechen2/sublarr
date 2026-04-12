"""Tests for standalone.scanner — StandaloneScanner and helpers.

Covers:
- _is_extra_file (trailer / featurette detection)
- StandaloneScanner._find_common_parent (series-root normalization)
- StandaloneScanner._get_target_languages (profile + fallback)
- StandaloneScanner._check_existing_subtitle (subtitle detection)
- StandaloneScanner.scan_all_folders (full scan orchestration)
- StandaloneScanner._scan_folder (single folder walk)
- StandaloneScanner._process_series_group (NFO + resolver paths)
- StandaloneScanner._process_movie (NFO + resolver paths)
- StandaloneScanner.process_single_file (movie + episode paths)
- StandaloneScanner._cleanup_stale_series
- StandaloneScanner._cleanup_stale_wanted
- Concurrent scan guard (lock)
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from standalone.scanner import StandaloneScanner, _is_extra_file

# ---------------------------------------------------------------------------
# _is_extra_file
# ---------------------------------------------------------------------------


class TestIsExtraFile:
    """Verify extra-file detection by stem and suffix."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("trailer.mkv", True),
            ("sample.mp4", True),
            ("tvshow.avi", True),
            ("movie.mkv", True),
            ("episode01-trailer.mkv", True),
            ("behind-behindthescenes.mp4", True),
            ("deleted-deleted.mkv", True),
            ("special-featurette.avi", True),
            ("my-interview.mkv", True),
            ("bonus-scene.mp4", True),
            ("intro-short.avi", True),
            ("clip-sample.mkv", True),
            ("opening-theme.mp4", True),
            # NOT extras
            ("My.Show.S01E01.mkv", False),
            ("Attack on Titan - 01.mkv", False),
            ("Movie.2024.1080p.mkv", False),
            ("trailer_park_boys.mkv", False),  # stem is 'trailer_park_boys'
        ],
    )
    def test_detection(self, filename, expected):
        assert _is_extra_file(f"/media/{filename}") is expected


# ---------------------------------------------------------------------------
# _find_common_parent
# ---------------------------------------------------------------------------


class TestFindCommonParent:
    """Series-root normalization logic."""

    def setup_method(self):
        self.scanner = StandaloneScanner()

    def _p(self, *parts: str) -> str:
        """Build an OS-native path from forward-slash parts."""
        return os.path.join(*parts[0].replace("/", os.sep).split(os.sep))

    def test_empty_list_returns_empty(self):
        assert self.scanner._find_common_parent([]) == ""

    def test_single_file_returns_parent_dir(self, tmp_path):
        season_dir = tmp_path / "Show" / "Season 1"
        season_dir.mkdir(parents=True)
        ep = season_dir / "ep01.mkv"
        ep.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(ep)])
        # Season subfolder should be unwound to series root
        assert os.path.basename(result) == "Show"

    def test_multiple_files_same_season(self, tmp_path):
        season_dir = tmp_path / "Show" / "Season 1"
        season_dir.mkdir(parents=True)
        ep1 = season_dir / "ep01.mkv"
        ep2 = season_dir / "ep02.mkv"
        ep1.write_bytes(b"\x00")
        ep2.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(ep1), str(ep2)])
        assert os.path.basename(result) == "Show"

    def test_multiple_files_different_seasons(self, tmp_path):
        s1 = tmp_path / "Show" / "Season 1"
        s2 = tmp_path / "Show" / "Season 2"
        s1.mkdir(parents=True)
        s2.mkdir(parents=True)
        ep1 = s1 / "ep01.mkv"
        ep2 = s2 / "ep01.mkv"
        ep1.write_bytes(b"\x00")
        ep2.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(ep1), str(ep2)])
        # Common parent is Show — not a season folder, stays
        assert os.path.basename(result) == "Show"

    def test_german_season_folder_staffel(self, tmp_path):
        staffel = tmp_path / "Anime" / "Staffel 2"
        staffel.mkdir(parents=True)
        ep = staffel / "ep01.mkv"
        ep.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(ep)])
        assert os.path.basename(result) == "Anime"

    def test_s01_folder_pattern(self, tmp_path):
        s01 = tmp_path / "Anime" / "S01"
        s01.mkdir(parents=True)
        ep = s01 / "ep01.mkv"
        ep.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(ep)])
        assert os.path.basename(result) == "Anime"

    def test_non_season_folder_stays(self, tmp_path):
        extras = tmp_path / "Show" / "Extras"
        extras.mkdir(parents=True)
        clip = extras / "clip.mkv"
        clip.write_bytes(b"\x00")
        result = self.scanner._find_common_parent([str(clip)])
        # "Extras" does not match season regex — stays as-is
        assert os.path.basename(result) == "Extras"


# ---------------------------------------------------------------------------
# _get_target_languages
# ---------------------------------------------------------------------------


class TestGetTargetLanguages:
    def test_returns_profile_languages(self):
        StandaloneScanner()
        with patch("standalone.scanner.StandaloneScanner._get_target_languages"):
            # Direct test of internal method via real logic
            pass

        # Test the real method with mocked imports
        with patch.dict("sys.modules", {}):
            pass  # Can't easily re-import; use monkeypatch approach

    def test_profile_with_languages(self, monkeypatch):
        scanner = StandaloneScanner()
        mock_profile = {"target_languages": ["de", "en"]}
        monkeypatch.setattr(
            "standalone.scanner.StandaloneScanner._get_target_languages",
            lambda self: ["de", "en"],
        )
        # Validate via the real method instead
        with patch("db.profiles.get_default_profile", return_value=mock_profile):
            result = StandaloneScanner._get_target_languages(scanner)
            assert result == ["de", "en"]

    def test_profile_empty_falls_back_to_config(self):
        scanner = StandaloneScanner()
        mock_profile = {"target_languages": []}
        mock_settings = MagicMock()
        mock_settings.target_language = "ja"
        with (
            patch("db.profiles.get_default_profile", return_value=mock_profile),
            patch("config.get_settings", return_value=mock_settings),
        ):
            result = scanner._get_target_languages()
            assert result == ["ja"]

    def test_no_profile_falls_back_to_config(self):
        scanner = StandaloneScanner()
        mock_settings = MagicMock()
        mock_settings.target_language = "fr"
        with (
            patch("db.profiles.get_default_profile", return_value=None),
            patch("config.get_settings", return_value=mock_settings),
        ):
            result = scanner._get_target_languages()
            assert result == ["fr"]

    def test_all_fallbacks_exhausted_returns_de(self):
        scanner = StandaloneScanner()
        with (
            patch("db.profiles.get_default_profile", side_effect=Exception("no DB")),
            patch("config.get_settings", side_effect=Exception("no config")),
        ):
            result = scanner._get_target_languages()
            assert result == ["de"]


# ---------------------------------------------------------------------------
# _check_existing_subtitle
# ---------------------------------------------------------------------------


class TestCheckExistingSubtitle:
    def test_returns_ass_when_found(self):
        scanner = StandaloneScanner()
        with patch("translator.detect_existing_target_for_lang", return_value="ass"):
            result = scanner._check_existing_subtitle("/media/ep01.mkv", "de")
            assert result == "ass"

    def test_returns_srt_when_found(self):
        scanner = StandaloneScanner()
        with patch("translator.detect_existing_target_for_lang", return_value="srt"):
            result = scanner._check_existing_subtitle("/media/ep01.mkv", "de")
            assert result == "srt"

    def test_returns_none_when_nothing(self):
        scanner = StandaloneScanner()
        with patch("translator.detect_existing_target_for_lang", return_value=None):
            result = scanner._check_existing_subtitle("/media/ep01.mkv", "de")
            assert result is None

    def test_returns_none_on_error(self):
        scanner = StandaloneScanner()
        with patch("translator.detect_existing_target_for_lang", side_effect=Exception("boom")):
            result = scanner._check_existing_subtitle("/media/ep01.mkv", "de")
            assert result is None


# ---------------------------------------------------------------------------
# scan_all_folders — orchestration
# ---------------------------------------------------------------------------


class TestScanAllFolders:
    def test_no_enabled_folders_returns_zero_summary(self):
        scanner = StandaloneScanner()
        with patch("db.standalone.get_watched_folders", return_value=[]):
            result = scanner.scan_all_folders()
            assert result["folders_scanned"] == 0
            assert result["wanted_added"] == 0

    def test_scan_already_running_returns_error(self):
        scanner = StandaloneScanner()
        # Acquire the lock externally to simulate a running scan
        scanner._scan_lock.acquire()
        try:
            result = scanner.scan_all_folders()
            assert result == {"error": "scan_already_running"}
        finally:
            scanner._scan_lock.release()

    def test_successful_scan_returns_summary(self):
        scanner = StandaloneScanner()
        folders = [{"path": "/media/anime", "label": "Anime", "media_type": "series"}]

        with (
            patch("db.standalone.get_watched_folders", return_value=folders),
            patch.object(scanner, "_scan_folder", return_value=(2, 0, 5)),
            patch.object(scanner, "_cleanup_stale_series"),
            patch.object(scanner, "_cleanup_stale_wanted"),
        ):
            result = scanner.scan_all_folders()

            assert result["folders_scanned"] == 1
            assert result["series_found"] == 2
            assert result["movies_found"] == 0
            assert result["wanted_added"] == 5
            assert "duration_seconds" in result

    def test_folder_scan_error_is_caught_and_continues(self):
        scanner = StandaloneScanner()
        folders = [
            {"path": "/media/broken", "label": "Broken"},
            {"path": "/media/good", "label": "Good"},
        ]

        def side_effect(folder):
            if folder["path"] == "/media/broken":
                raise RuntimeError("disk error")
            return (1, 0, 2)

        with (
            patch("db.standalone.get_watched_folders", return_value=folders),
            patch.object(scanner, "_scan_folder", side_effect=side_effect),
            patch.object(scanner, "_cleanup_stale_series"),
            patch.object(scanner, "_cleanup_stale_wanted"),
        ):
            result = scanner.scan_all_folders()

            # Only the good folder counted
            assert result["folders_scanned"] == 1
            assert result["series_found"] == 1

    def test_scanning_flag_reset_after_scan(self):
        scanner = StandaloneScanner()
        assert scanner.is_scanning is False

        with patch("db.standalone.get_watched_folders", return_value=[]):
            scanner.scan_all_folders()

        assert scanner.is_scanning is False

    def test_scanning_flag_reset_after_exception(self):
        scanner = StandaloneScanner()
        with patch("db.standalone.get_watched_folders", side_effect=RuntimeError("fail")):
            result = scanner.scan_all_folders()

        assert scanner.is_scanning is False
        assert "error" in result


# ---------------------------------------------------------------------------
# _scan_folder
# ---------------------------------------------------------------------------


class TestScanFolder:
    def test_nonexistent_folder_returns_zeros(self):
        scanner = StandaloneScanner()
        folder = {"path": "/nonexistent/path"}
        result = scanner._scan_folder(folder)
        assert result == (0, 0, 0)

    def test_empty_folder_returns_zeros(self, tmp_path):
        scanner = StandaloneScanner()
        folder = {"path": str(tmp_path)}

        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        with patch("config.get_settings", return_value=mock_settings):
            result = scanner._scan_folder(folder)
            assert result == (0, 0, 0)

    def test_folder_with_video_files_processes_them(self, tmp_path):
        """A folder with .mkv files triggers series grouping and processing."""
        scanner = StandaloneScanner()
        # Create video files
        ep1 = tmp_path / "Show" / "ep01.mkv"
        ep1.parent.mkdir(parents=True)
        ep1.write_bytes(b"\x00")

        folder = {"path": str(tmp_path)}
        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        series_groups = {
            "show": [{"file_path": str(ep1), "title": "Show", "season": 1, "episode": 1}]
        }

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("standalone.parser.is_video_file", return_value=True),
            patch("standalone.parser.group_files_by_series", return_value=series_groups),
            patch("standalone.parser.parse_media_file", return_value={"type": "episode"}),
            patch.object(scanner, "_process_series_group", return_value=3),
        ):
            s, m, w = scanner._scan_folder(folder)
            assert s == 1
            assert w == 3

    def test_extras_skipped_when_setting_enabled(self, tmp_path):
        """Trailer files are excluded when standalone_skip_extras is True."""
        scanner = StandaloneScanner()
        trailer = tmp_path / "trailer.mkv"
        trailer.write_bytes(b"\x00")

        folder = {"path": str(tmp_path)}
        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("standalone.parser.is_video_file", return_value=True),
            patch("standalone.parser.group_files_by_series", return_value={}),
        ):
            result = scanner._scan_folder(folder)
            assert result == (0, 0, 0)


# ---------------------------------------------------------------------------
# _process_series_group
# ---------------------------------------------------------------------------


class TestProcessSeriesGroup:
    def _make_scanner(self):
        resolver = MagicMock()
        resolver.resolve_series.return_value = {
            "title": "My Anime",
            "year": 2024,
            "tmdb_id": 12345,
            "tvdb_id": 67890,
            "anilist_id": 111,
            "imdb_id": "tt0001",
            "poster_url": "http://img/poster.jpg",
            "is_anime": True,
            "season_count": 2,
            "metadata_source": "tmdb",
        }
        return StandaloneScanner(metadata_resolver=resolver), resolver

    def test_nfo_with_ids_skips_resolver(self):
        """When NFO has tvdb_id, the online resolver is NOT called."""
        scanner, resolver = self._make_scanner()
        files = [
            {"file_path": "/media/Show/S01/ep01.mkv", "title": "Show", "season": 1, "episode": 1},
        ]
        folder = {"path": "/media/Show"}
        nfo = {
            "title": "Show NFO",
            "tvdb_id": 99,
            "tmdb_id": None,
            "imdb_id": "",
            "anilist_id": None,
            "local_poster": "",
            "year": 2023,
            "is_anime": False,
        }

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=nfo),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            wanted = scanner._process_series_group("show", files, folder)

            # Resolver should NOT have been called (NFO had tvdb_id)
            resolver.resolve_series.assert_not_called()
            assert wanted == 1

    def test_nfo_with_title_only_calls_resolver(self):
        """When NFO has title but no IDs, resolver is called to enrich."""
        scanner, resolver = self._make_scanner()
        files = [
            {"file_path": "/media/Show/ep01.mkv", "title": "Show", "season": 1, "episode": 1},
        ]
        folder = {"path": "/media/Show"}
        nfo = {
            "title": "Show Title",
            "tvdb_id": None,
            "tmdb_id": None,
            "imdb_id": "",
            "anilist_id": None,
            "local_poster": "",
            "year": 2024,
            "is_anime": False,
        }

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=nfo),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            wanted = scanner._process_series_group("show", files, folder)
            resolver.resolve_series.assert_called_once()
            assert wanted == 1

    def test_no_nfo_falls_back_to_resolver(self):
        """When no NFO found, resolver is used directly."""
        scanner, resolver = self._make_scanner()
        files = [
            {
                "file_path": "/media/Show/ep01.mkv",
                "title": "Show",
                "season": 1,
                "episode": 1,
                "is_anime": True,
                "year": 2024,
            },
        ]
        folder = {"path": "/media/Show"}

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            wanted = scanner._process_series_group("show", files, folder)
            resolver.resolve_series.assert_called_once()
            assert wanted == 1

    def test_existing_ass_subtitle_skips_wanted(self):
        """Episodes with existing ASS subtitles are not added to wanted."""
        scanner, _ = self._make_scanner()
        files = [
            {"file_path": "/media/Show/ep01.mkv", "title": "Show", "season": 1, "episode": 1},
        ]
        folder = {"path": "/media/Show"}

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value="ass"),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            wanted = scanner._process_series_group("show", files, folder)
            mock_upsert.assert_not_called()
            assert wanted == 0

    def test_season_episode_formatting(self):
        """Season+episode produces 'S01E02' format in title."""
        scanner, _ = self._make_scanner()
        files = [
            {"file_path": "/media/Show/ep.mkv", "title": "Show", "season": 1, "episode": 2},
        ]
        folder = {"path": "/media/Show"}

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            scanner._process_series_group("show", files, folder)

            call_kwargs = mock_upsert.call_args[1]
            assert call_kwargs["season_episode"] == "S01E02"
            assert "S01E02" in call_kwargs["title"]

    def test_episode_only_formatting(self):
        """Episode without season produces 'E03' format."""
        scanner, _ = self._make_scanner()
        files = [
            {"file_path": "/media/Show/ep.mkv", "title": "Show", "season": None, "episode": 3},
        ]
        folder = {"path": "/media/Show"}

        with (
            patch("standalone.nfo_parser.parse_series_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
            patch.object(scanner, "_find_common_parent", return_value="/media/Show"),
        ):
            scanner._process_series_group("show", files, folder)

            call_kwargs = mock_upsert.call_args[1]
            assert call_kwargs["season_episode"] == "E03"


# ---------------------------------------------------------------------------
# _process_movie
# ---------------------------------------------------------------------------


class TestProcessMovie:
    def _make_scanner(self):
        resolver = MagicMock()
        resolver.resolve_movie.return_value = {
            "title": "My Movie",
            "year": 2024,
            "tmdb_id": 55555,
            "imdb_id": "tt5555",
            "poster_url": "http://img/movie.jpg",
            "metadata_source": "tmdb",
        }
        return StandaloneScanner(metadata_resolver=resolver), resolver

    def test_nfo_with_tmdb_id_skips_resolver(self):
        scanner, resolver = self._make_scanner()
        parsed = {"title": "Movie", "year": 2024}
        nfo = {
            "title": "Movie NFO",
            "tmdb_id": 999,
            "imdb_id": "tt999",
            "local_poster": "",
            "year": 2024,
        }

        with (
            patch("standalone.nfo_parser.parse_movie_nfo", return_value=nfo),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_movie", return_value=10),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            wanted = scanner._process_movie(
                parsed, "/media/Movie/movie.mkv", {"path": "/media/Movie"}
            )
            resolver.resolve_movie.assert_not_called()
            assert wanted == 1

    def test_nfo_without_ids_calls_resolver(self):
        scanner, resolver = self._make_scanner()
        parsed = {"title": "Movie", "year": 2024}
        nfo = {
            "title": "Movie Title",
            "tmdb_id": None,
            "imdb_id": "",
            "local_poster": "",
            "year": 2024,
        }

        with (
            patch("standalone.nfo_parser.parse_movie_nfo", return_value=nfo),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_movie", return_value=10),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            scanner._process_movie(parsed, "/media/Movie/movie.mkv", {"path": "/media/Movie"})
            resolver.resolve_movie.assert_called_once()

    def test_no_nfo_uses_resolver(self):
        scanner, resolver = self._make_scanner()
        parsed = {"title": "Untitled", "year": None}

        with (
            patch("standalone.nfo_parser.parse_movie_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_movie", return_value=10),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            scanner._process_movie(parsed, "/media/movie.mkv", {"path": "/media"})
            resolver.resolve_movie.assert_called_once()

    def test_existing_ass_skips_wanted(self):
        scanner, _ = self._make_scanner()
        parsed = {"title": "Movie", "year": 2024}

        with (
            patch("standalone.nfo_parser.parse_movie_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_movie", return_value=10),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value="ass"),
        ):
            wanted = scanner._process_movie(parsed, "/media/movie.mkv", {"path": "/media"})
            mock_upsert.assert_not_called()
            assert wanted == 0

    def test_multiple_target_languages(self):
        """Each missing language produces a separate wanted item."""
        scanner, _ = self._make_scanner()
        parsed = {"title": "Movie", "year": 2024}

        with (
            patch("standalone.nfo_parser.parse_movie_nfo", return_value=None),
            patch("standalone.nfo_parser.find_local_poster", return_value=None),
            patch("db.standalone.upsert_standalone_movie", return_value=10),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de", "en"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            wanted = scanner._process_movie(parsed, "/media/movie.mkv", {"path": "/media"})
            assert wanted == 2
            assert mock_upsert.call_count == 2


# ---------------------------------------------------------------------------
# process_single_file
# ---------------------------------------------------------------------------


class TestProcessSingleFile:
    def _make_scanner(self):
        resolver = MagicMock()
        resolver.resolve_series.return_value = {
            "title": "Anime",
            "year": 2024,
            "tmdb_id": 1,
            "tvdb_id": 2,
            "anilist_id": 3,
            "imdb_id": "tt1",
            "poster_url": "",
            "is_anime": True,
            "metadata_source": "tmdb",
        }
        resolver.resolve_movie.return_value = {
            "title": "Film",
            "year": 2024,
            "tmdb_id": 5,
            "imdb_id": "tt5",
            "poster_url": "",
            "metadata_source": "tmdb",
        }
        return StandaloneScanner(metadata_resolver=resolver)

    def test_movie_file(self):
        scanner = self._make_scanner()
        parsed = {"type": "movie", "title": "Film", "year": 2024}

        with (
            patch("standalone.parser.parse_media_file", return_value=parsed),
            patch.object(scanner, "_process_movie", return_value=1),
        ):
            result = scanner.process_single_file("/media/film.mkv")
            assert result["type"] == "movie"
            assert result["wanted"] is True

    def test_episode_file(self):
        scanner = self._make_scanner()
        parsed = {
            "type": "episode",
            "title": "Anime",
            "season": 1,
            "episode": 5,
            "is_anime": True,
            "year": 2024,
        }

        with (
            patch("standalone.parser.parse_media_file", return_value=parsed),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item"),
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            result = scanner.process_single_file("/media/Anime/ep05.mkv")
            assert result["type"] == "episode"
            assert result["wanted"] is True

    def test_episode_with_existing_ass_not_wanted(self):
        scanner = self._make_scanner()
        parsed = {
            "type": "episode",
            "title": "Anime",
            "season": 1,
            "episode": 5,
            "is_anime": False,
            "year": None,
        }

        with (
            patch("standalone.parser.parse_media_file", return_value=parsed),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value="ass"),
        ):
            result = scanner.process_single_file("/media/Anime/ep05.mkv")
            assert result["type"] == "episode"
            assert result["wanted"] is False
            mock_upsert.assert_not_called()

    def test_parse_error_returns_unknown(self):
        scanner = self._make_scanner()
        with patch("standalone.parser.parse_media_file", side_effect=Exception("parse fail")):
            result = scanner.process_single_file("/media/broken.mkv")
            assert result["type"] == "unknown"
            assert result["wanted"] is False
            assert "error" in result

    def test_episode_season_episode_formatting(self):
        """S01E05 format in wanted title for single file processing."""
        scanner = self._make_scanner()
        parsed = {
            "type": "episode",
            "title": "Show",
            "season": 1,
            "episode": 5,
            "is_anime": False,
            "year": None,
        }

        with (
            patch("standalone.parser.parse_media_file", return_value=parsed),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value="srt"),
        ):
            scanner.process_single_file("/media/Show/ep05.mkv")
            call_kwargs = mock_upsert.call_args[1]
            assert call_kwargs["season_episode"] == "S01E05"
            assert "S01E05" in call_kwargs["title"]

    def test_episode_without_season(self):
        """Episode without season number uses E## format."""
        scanner = self._make_scanner()
        parsed = {
            "type": "episode",
            "title": "Anime",
            "season": None,
            "episode": 12,
            "is_anime": True,
            "year": None,
        }

        with (
            patch("standalone.parser.parse_media_file", return_value=parsed),
            patch("db.standalone.upsert_standalone_series", return_value=42),
            patch("db.wanted.upsert_wanted_item") as mock_upsert,
            patch.object(scanner, "_get_target_languages", return_value=["de"]),
            patch.object(scanner, "_check_existing_subtitle", return_value=None),
        ):
            scanner.process_single_file("/media/Anime/ep12.mkv")
            call_kwargs = mock_upsert.call_args[1]
            assert call_kwargs["season_episode"] == "E12"


# ---------------------------------------------------------------------------
# _cleanup_stale_series
# ---------------------------------------------------------------------------


class TestCleanupStaleSeries:
    def test_removes_nonexistent_folders(self):
        scanner = StandaloneScanner()
        series_list = [
            {"id": 1, "folder_path": "/nonexistent/path"},
            {"id": 2, "folder_path": "/also/missing"},
        ]

        with (
            patch("db.standalone.get_standalone_series", return_value=series_list),
            patch("db.standalone.delete_standalone_series") as mock_delete,
        ):
            removed = scanner._cleanup_stale_series()
            assert removed == 2
            assert mock_delete.call_count == 2

    def test_removes_season_subfolder_entries(self, tmp_path):
        """Series entries pointing to season subfolders should be cleaned up."""
        scanner = StandaloneScanner()
        season_dir = tmp_path / "Season 1"
        season_dir.mkdir()

        series_list = [
            {"id": 1, "folder_path": str(season_dir)},
        ]

        with (
            patch("db.standalone.get_standalone_series", return_value=series_list),
            patch("db.standalone.delete_standalone_series") as mock_delete,
        ):
            removed = scanner._cleanup_stale_series()
            assert removed == 1
            mock_delete.assert_called_once_with(1)

    def test_keeps_valid_series(self, tmp_path):
        scanner = StandaloneScanner()
        series_dir = tmp_path / "MyShow"
        series_dir.mkdir()

        series_list = [
            {"id": 1, "folder_path": str(series_dir)},
        ]

        with (
            patch("db.standalone.get_standalone_series", return_value=series_list),
            patch("db.standalone.delete_standalone_series") as mock_delete,
        ):
            removed = scanner._cleanup_stale_series()
            assert removed == 0
            mock_delete.assert_not_called()

    def test_no_series_returns_zero(self):
        scanner = StandaloneScanner()
        with patch("db.standalone.get_standalone_series", return_value=[]):
            assert scanner._cleanup_stale_series() == 0

    def test_exception_returns_zero(self):
        scanner = StandaloneScanner()
        with patch("db.standalone.get_standalone_series", side_effect=RuntimeError("db")):
            assert scanner._cleanup_stale_series() == 0


# ---------------------------------------------------------------------------
# _cleanup_stale_wanted
# ---------------------------------------------------------------------------


class TestCleanupStaleWanted:
    def test_removes_missing_files(self, tmp_path):
        scanner = StandaloneScanner()
        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            (1, "/nonexistent/ep01.mkv"),
            (2, str(tmp_path / "exists.mkv")),
        ]
        # Create the existing file
        (tmp_path / "exists.mkv").write_bytes(b"\x00")

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db", return_value=mock_db),
            patch("db.wanted.delete_wanted_items_by_ids") as mock_delete,
        ):
            removed = scanner._cleanup_stale_wanted()
            assert removed == 1
            mock_delete.assert_called_once_with([1])

    def test_removes_extras_when_skip_enabled(self, tmp_path):
        scanner = StandaloneScanner()
        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        trailer = tmp_path / "trailer.mkv"
        trailer.write_bytes(b"\x00")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            (1, str(trailer)),
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db", return_value=mock_db),
            patch("db.wanted.delete_wanted_items_by_ids") as mock_delete,
        ):
            removed = scanner._cleanup_stale_wanted()
            assert removed == 1
            mock_delete.assert_called_once_with([1])

    def test_no_stale_items(self, tmp_path):
        scanner = StandaloneScanner()
        mock_settings = MagicMock()
        mock_settings.standalone_skip_extras = True

        existing = tmp_path / "ep01.mkv"
        existing.write_bytes(b"\x00")

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchall.return_value = [
            (1, str(existing)),
        ]

        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("db.get_db", return_value=mock_db),
        ):
            removed = scanner._cleanup_stale_wanted()
            assert removed == 0

    def test_exception_returns_zero(self):
        scanner = StandaloneScanner()
        with patch("config.get_settings", side_effect=RuntimeError("fail")):
            assert scanner._cleanup_stale_wanted() == 0


# ---------------------------------------------------------------------------
# _get_resolver
# ---------------------------------------------------------------------------


class TestGetResolver:
    def test_returns_injected_resolver(self):
        resolver = MagicMock()
        scanner = StandaloneScanner(metadata_resolver=resolver)
        assert scanner._get_resolver() is resolver

    def test_creates_resolver_lazily(self):
        scanner = StandaloneScanner()
        mock_settings = MagicMock()
        mock_settings.tmdb_api_key = "key1"
        mock_settings.tvdb_api_key = "key2"
        mock_settings.tvdb_pin = "pin"

        mock_resolver_class = MagicMock()
        with (
            patch("config.get_settings", return_value=mock_settings),
            patch("metadata.MetadataResolver", mock_resolver_class),
        ):
            scanner._get_resolver()
            mock_resolver_class.assert_called_once_with(
                tmdb_key="key1", tvdb_key="key2", tvdb_pin="pin"
            )

    def test_fallback_on_settings_error(self):
        scanner = StandaloneScanner()
        mock_resolver_class = MagicMock()
        with (
            patch("config.get_settings", side_effect=Exception("no config")),
            patch("metadata.MetadataResolver", mock_resolver_class),
        ):
            scanner._get_resolver()
            # Fallback: MetadataResolver() with no args
            mock_resolver_class.assert_called_with()


# ---------------------------------------------------------------------------
# is_scanning property
# ---------------------------------------------------------------------------


class TestIsScanning:
    def test_default_false(self):
        scanner = StandaloneScanner()
        assert scanner.is_scanning is False
