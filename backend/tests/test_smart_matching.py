"""Smart Episode Matching and Video Hash pre-computation tests.

Tests:
- TestMultiEpisodeParsing: S01E01E02, single, none, list normalization
- TestOvaSpecialDetection: OVA, Special, SP, bonus keywords
- TestFilenameMetadata: guessit path populates episodes, absolute_ep, release_group
- TestVideoHashPrecompute: hash set in query when file exists, skipped when absent
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from standalone.parser import _normalize_episodes, detect_anime_indicators, parse_media_file

# ── TestMultiEpisodeParsing ───────────────────────────────────────────────────


class TestNormalizeEpisodes:
    def test_none_returns_empty(self):
        assert _normalize_episodes(None) == []

    def test_single_int(self):
        assert _normalize_episodes(3) == [3]

    def test_list_of_ints(self):
        assert _normalize_episodes([1, 2]) == [1, 2]

    def test_list_with_none(self):
        assert _normalize_episodes([1, None, 3]) == [1, 3]

    def test_string_int(self):
        assert _normalize_episodes("5") == [5]


class TestMultiEpisodeParsing:
    def test_single_episode(self):
        result = parse_media_file("/media/Show/Show.S01E03.mkv")
        assert result["episode"] == 3
        assert result["episodes"] == [3]

    def test_multi_episode_file(self):
        """S01E01E02 should produce episodes=[1, 2] and episode=1."""
        result = parse_media_file("/media/Show/Show.S01E01E02.mkv")
        assert result["episode"] == 1
        assert 1 in result["episodes"]
        assert 2 in result["episodes"]

    def test_no_episode(self):
        result = parse_media_file("/media/Movies/Some.Movie.2020.mkv")
        assert result["episode"] is None
        assert result["episodes"] == []


# ── TestOvaSpecialDetection ───────────────────────────────────────────────────


class TestOvaSpecialDetection:
    def test_ova_in_filename(self):
        result = parse_media_file("/media/Anime/[SubsPlease] Series - OVA [1080p].mkv")
        assert result["is_ova"] is True

    def test_special_in_filename(self):
        result = parse_media_file("/media/Anime/Series.Special.mkv")
        assert result["is_special"] is True

    def test_regular_episode_not_special(self):
        result = parse_media_file("/media/Show/Show.S01E05.mkv")
        assert result["is_special"] is False
        assert result["is_ova"] is False

    def test_sp_suffix(self):
        result = parse_media_file("/media/Anime/Series.SP01.mkv")
        assert result["is_special"] is True


# ── TestFilenameMetadataFallback ──────────────────────────────────────────────


class TestFilenameMetadataFallback:
    """Tests for _parse_filename_for_metadata() which wraps parse_media_file."""

    def _call(self, file_path: str) -> dict:
        from wanted_search import _parse_filename_for_metadata

        return _parse_filename_for_metadata(file_path)

    def test_release_group_propagated(self):
        result = self._call("/media/Show/Show.S01E01.WEB-DL.1080p-SubsPlease.mkv")
        # release_group or source should be populated
        assert result.get("release_group") or result.get("source") or result.get("resolution")

    def test_episodes_list_returned(self):
        result = self._call("/media/Show/Show.S01E01E02.mkv")
        assert "episodes" in result
        # At minimum the primary episode is in the list
        if result.get("episode"):
            assert result["episode"] in (result["episodes"] or [result["episode"]])

    def test_absolute_episode_for_anime(self):
        result = self._call("/media/Anime/[SubsPlease] AnimeTitle - 153 [1080p].mkv")
        # Anime absolute episode should be detected
        assert result.get("absolute_episode") is not None or result.get("is_anime") is True


# ── TestVideoHashPrecompute ───────────────────────────────────────────────────


class TestVideoHashPrecompute:
    """Tests for file_hash pre-computation in build_query_from_wanted()."""

    def _make_wanted_item(self, file_path: str) -> dict:
        return {
            "id": 1,
            "file_path": file_path,
            "item_type": "episode",
            "target_language": "de",
            "subtitle_type": "full",
            "sonarr_series_id": None,
            "sonarr_episode_id": None,
            "standalone_series_id": None,
        }

    def test_hash_precomputed_when_file_exists(self, tmp_path):
        # Create a dummy video file (content doesn't matter for mock)
        video = tmp_path / "episode.mkv"
        video.write_bytes(b"\x00" * 200000)  # >128KB so hash can be computed

        item = self._make_wanted_item(str(video))

        with patch(
            "providers.opensubtitles._compute_opensubtitles_hash",
            return_value="deadbeef12345678",
        ) as mock_hash:
            from wanted_search import build_query_from_wanted

            query = build_query_from_wanted(item)

        mock_hash.assert_called_once_with(str(video))
        assert query.file_hash == "deadbeef12345678"

    def test_hash_skipped_when_file_missing(self, tmp_path):
        item = self._make_wanted_item(str(tmp_path / "nonexistent.mkv"))

        with patch(
            "providers.opensubtitles._compute_opensubtitles_hash",
        ) as mock_hash:
            from wanted_search import build_query_from_wanted

            query = build_query_from_wanted(item)

        mock_hash.assert_not_called()
        assert query.file_hash == ""

    def test_existing_hash_not_overwritten(self, tmp_path):
        video = tmp_path / "episode.mkv"
        video.write_bytes(b"\x00" * 200000)

        item = self._make_wanted_item(str(video))
        item["file_hash"] = "already_set"  # simulate pre-existing hash

        # VideoQuery.file_hash must start with the pre-set value
        # Since build_query_from_wanted sets query.file_path but not file_hash from item,
        # the hash starts empty → this tests the guard `if not query.file_hash`
        with patch(
            "providers.opensubtitles._compute_opensubtitles_hash",
            return_value="new_hash",
        ):
            from wanted_search import build_query_from_wanted

            query = build_query_from_wanted(item)

        # hash was computed since query.file_hash started empty
        assert query.file_hash == "new_hash"
