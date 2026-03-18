"""Regression tests for wanted_search reliability fixes.

Tests defensive guards for provider errors, file system operations,
and translation pipeline failures.
"""

import os
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest

from error_handler import SublarrError
from providers.base import SubtitleFormat, SubtitleResult
from wanted_search import process_wanted_item, search_wanted_item


@pytest.fixture
def mock_wanted_item():
    """Create a mock wanted item for testing."""
    return {
        "id": 1,
        "item_type": "episode",
        "file_path": "/test/path/video.mkv",
        "target_language": "de",
        "sonarr_series_id": 123,
        "sonarr_episode_id": 456,
        "search_count": 0,
        "subtitle_type": "full",
        "current_score": 0,
        "upgrade_candidate": False,
    }


@pytest.fixture
def temp_file():
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f:
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)


class TestProviderErrorHandling:
    """Test that provider errors don't crash the entire workflow."""

    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    @patch("wanted_search.update_wanted_search")
    @patch("wanted_search.build_query_from_wanted")
    def test_provider_search_failure_continues(
        self,
        mock_build_query,
        mock_update_search,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        app_ctx,
        mock_wanted_item,
        temp_file,
    ):
        """Test that provider search failures don't abort the entire process."""
        mock_wanted_item["file_path"] = temp_file
        mock_get_item.return_value = mock_wanted_item

        # build_query_from_wanted needs a VideoQuery-like object with a .languages attr
        mock_build_query.return_value = MagicMock()

        # Mock provider manager to raise exception on search
        mock_manager = Mock()
        mock_manager.search.side_effect = Exception("Provider API error")
        mock_get_manager.return_value = mock_manager

        # Should not raise, but return results (empty if all searches fail)
        result = search_wanted_item(1)

        assert "wanted_id" in result
        assert result["wanted_id"] == 1
        # Should have empty results but not crash
        assert "target_results" in result
        assert "source_results" in result

    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    @patch("wanted_search.update_wanted_search")
    @patch("wanted_search.build_query_from_wanted")
    def test_save_subtitle_failure_continues(
        self,
        mock_build_query,
        mock_update_search,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        mock_wanted_item,
        temp_file,
    ):
        """Test that file save failures don't crash the process."""
        mock_wanted_item["file_path"] = temp_file
        mock_get_item.return_value = mock_wanted_item

        # Mock provider to return result but fail on save
        mock_result = Mock(spec=SubtitleResult)
        mock_result.content = b"test content"
        mock_result.provider_name = "test_provider"
        mock_result.format = SubtitleFormat.ASS
        mock_result.score = 100
        mock_result.language = "de"

        mock_manager = Mock()
        mock_manager.search_and_download_best.return_value = mock_result
        mock_manager.save_subtitle.side_effect = OSError("Disk full")
        mock_get_manager.return_value = mock_manager

        # Should not raise, but continue to next step
        result = process_wanted_item(1)

        # Should have tried to save and failed, but continued
        assert mock_manager.save_subtitle.called
        # Process should continue (not crash)
        assert "status" in result


class TestFileSystemGuards:
    """Test defensive guards for file system operations."""

    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    def test_disk_space_check_in_save(
        self,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        app_ctx,
        mock_wanted_item,
        temp_file,
    ):
        """Test that save_subtitle checks disk space."""
        from providers import ProviderManager
        from providers.base import SubtitleFormat, SubtitleResult

        mock_wanted_item["file_path"] = temp_file
        mock_get_item.return_value = mock_wanted_item

        # Create a real ProviderManager instance
        manager = ProviderManager()

        # Create a test result
        result = SubtitleResult(
            provider_name="test",
            subtitle_id="123",
            language="de",
            format=SubtitleFormat.ASS,
            filename="test.ass",
            release_info="",
            score=100,
            content=b"test content",
        )

        # Mock disk_usage to return low space
        with patch("shutil.disk_usage") as mock_disk:
            mock_disk.return_value.free = 50 * 1024 * 1024  # 50MB (below 100MB threshold)

            # Should raise RuntimeError for insufficient disk space
            with pytest.raises(RuntimeError, match="Insufficient disk space"):
                manager.save_subtitle(result, temp_file.replace(".mkv", ".de.ass"))


class TestTranslationPipelineResilience:
    """Test that translation pipeline failures are handled gracefully."""

    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    @patch("translator._translate_external_ass")
    def test_translation_failure_cleans_up_temp_file(
        self,
        mock_translate,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        app_ctx,
        mock_wanted_item,
        temp_file,
    ):
        """Test that translation failures clean up temporary files."""
        mock_wanted_item["file_path"] = temp_file
        mock_get_item.return_value = mock_wanted_item

        # Mock provider to return source ASS
        mock_result = Mock(spec=SubtitleResult)
        mock_result.content = b"test content"
        mock_result.provider_name = "test_provider"
        mock_result.format = SubtitleFormat.ASS
        mock_result.score = 100
        mock_result.language = "en"

        mock_manager = Mock()
        mock_manager.search_and_download_best.return_value = mock_result
        mock_get_manager.return_value = mock_manager

        # Mock translation to fail
        mock_translate.side_effect = Exception("Translation failed")

        # Create temp file path
        base = os.path.splitext(temp_file)[0]
        temp_source_path = f"{base}.en.ass"

        # Process should handle translation failure
        result = process_wanted_item(1)

        # Temp file should be cleaned up (or at least attempted)
        # Note: In real code, cleanup happens in finally block
        assert "status" in result
        assert not os.path.exists(temp_source_path), (
            "Temp file should have been cleaned up after failure"
        )


class TestAutoTranslateGuard:
    """Test that wanted_auto_translate=False prevents any translation from running."""

    def _make_settings(self, auto_translate: bool):
        s = MagicMock()
        s.wanted_auto_translate = auto_translate
        s.wanted_max_search_attempts = 3
        s.target_language = "de"
        s.source_language = "en"
        s.source_language_name = "English"
        s.target_language_name = "German"
        s.upgrade_prefer_ass = True
        s.upgrade_min_score_delta = 50
        s.upgrade_window_days = 7
        s.wanted_skip_srt_on_no_ass = True
        return s

    @patch("wanted_search.get_settings")
    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    @patch("wanted_search.update_wanted_search")
    @patch("wanted_search.build_query_from_wanted")
    def test_no_translation_when_auto_translate_disabled(
        self,
        mock_build_query,
        mock_update_search,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        mock_get_settings,
        temp_file,
    ):
        """When wanted_auto_translate=False, translate_file must never be called."""
        mock_wanted_item = {
            "id": 1,
            "item_type": "episode",
            "file_path": temp_file,
            "target_language": "de",
            "sonarr_series_id": 1,
            "sonarr_episode_id": 1,
            "search_count": 0,
            "subtitle_type": "full",
            "current_score": 0,
            "upgrade_candidate": False,
        }
        mock_get_item.return_value = mock_wanted_item
        mock_get_settings.return_value = self._make_settings(auto_translate=False)

        # No provider returns anything — all searches return None
        mock_manager = MagicMock()
        mock_manager.search_and_download_best.return_value = None
        mock_get_manager.return_value = mock_manager
        mock_build_query.return_value = MagicMock()

        with patch("translator.translate_file") as mock_translate_file:
            result = process_wanted_item(1)

        mock_translate_file.assert_not_called()
        assert result["status"] == "not_found"
        # Item must stay "wanted" so it can be retried later
        mock_update_status.assert_called_with(1, "wanted")

    @patch("wanted_search.get_settings")
    @patch("wanted_search.get_wanted_item")
    @patch("wanted_search.get_provider_manager")
    @patch("wanted_search.update_wanted_status")
    @patch("wanted_search.update_wanted_search")
    @patch("wanted_search.build_query_from_wanted")
    def test_direct_download_still_works_when_auto_translate_disabled(
        self,
        mock_build_query,
        mock_update_search,
        mock_update_status,
        mock_get_manager,
        mock_get_item,
        mock_get_settings,
        temp_file,
    ):
        """Step 1 (direct target ASS) must still work even when auto_translate=False."""
        mock_wanted_item = {
            "id": 1,
            "item_type": "episode",
            "file_path": temp_file,
            "target_language": "de",
            "sonarr_series_id": 1,
            "sonarr_episode_id": 1,
            "search_count": 0,
            "subtitle_type": "full",
            "current_score": 0,
            "upgrade_candidate": False,
        }
        mock_get_item.return_value = mock_wanted_item
        mock_get_settings.return_value = self._make_settings(auto_translate=False)

        # Provider returns a direct DE ASS match
        mock_result = MagicMock(spec=SubtitleResult)
        mock_result.content = b"test content"
        mock_result.provider_name = "opensubtitles"
        mock_result.format = SubtitleFormat.ASS
        mock_result.score = 100
        mock_result.subtitle_id = "abc"

        mock_manager = MagicMock()
        mock_manager.search_and_download_best.return_value = mock_result
        mock_manager.save_subtitle.return_value = temp_file.replace(".mkv", ".de.ass")
        mock_get_manager.return_value = mock_manager

        with (
            patch(
                "translator.get_output_path_for_lang",
                return_value=temp_file.replace(".mkv", ".de.ass"),
            ),
            patch("wanted_search.record_subtitle_download"),
            patch("translator.translate_file") as mock_translate_file,
        ):
            result = process_wanted_item(1)

        mock_translate_file.assert_not_called()
        assert result["status"] == "found"
        assert result["provider"] == "opensubtitles"
