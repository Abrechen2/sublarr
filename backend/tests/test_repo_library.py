"""Tests for db.repositories.library.LibraryRepository.

Covers: download history with filtering/sorting/pagination/search,
download stats aggregation, upgrade history recording and retrieval,
upgrade stats, download record deletion.
"""

from datetime import UTC, datetime

import pytest

from db.models.providers import SubtitleDownload
from db.repositories.library import LibraryRepository
from extensions import db


@pytest.fixture
def repo(app_ctx):
    """Create a LibraryRepository instance within app context."""
    return LibraryRepository()


def _insert_download(
    provider="opensubtitles",
    subtitle_id="sub_1",
    language="de",
    fmt="ass",
    file_path="/media/test.mkv",
    score=80,
):
    """Helper to insert a SubtitleDownload row directly."""
    entry = SubtitleDownload(
        provider_name=provider,
        subtitle_id=subtitle_id,
        language=language,
        format=fmt,
        file_path=file_path,
        score=score,
        downloaded_at=datetime.now(UTC),
    )
    db.session.add(entry)
    db.session.commit()
    return entry


# ---------------------------------------------------------------------------
# Download History
# ---------------------------------------------------------------------------


class TestDownloadHistory:
    def test_get_download_history_empty(self, repo):
        """Empty history returns no data."""
        result = repo.get_download_history()
        assert result["data"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 1

    def test_get_download_history_pagination(self, repo):
        """Download history supports pagination."""
        for i in range(15):
            _insert_download(subtitle_id=f"sub_{i}", file_path=f"/media/f{i}.mkv")

        result = repo.get_download_history(page=1, per_page=10)
        assert len(result["data"]) == 10
        assert result["total"] == 15
        assert result["total_pages"] == 2
        assert result["page"] == 1

    def test_get_download_history_second_page(self, repo):
        """Second page returns remaining entries."""
        for i in range(15):
            _insert_download(subtitle_id=f"sub_{i}", file_path=f"/media/f{i}.mkv")

        result = repo.get_download_history(page=2, per_page=10)
        assert len(result["data"]) == 5

    def test_get_download_history_filter_by_provider(self, repo):
        """Filter by provider returns only matching downloads."""
        _insert_download(provider="opensubtitles", subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(provider="addic7ed", subtitle_id="s2", file_path="/media/b.mkv")

        result = repo.get_download_history(provider="opensubtitles")
        assert result["total"] == 1
        assert result["data"][0]["provider_name"] == "opensubtitles"

    def test_get_download_history_filter_by_language(self, repo):
        """Filter by language returns only matching downloads."""
        _insert_download(language="de", subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(language="en", subtitle_id="s2", file_path="/media/b.mkv")

        result = repo.get_download_history(language="de")
        assert result["total"] == 1
        assert result["data"][0]["language"] == "de"

    def test_get_download_history_filter_by_format(self, repo):
        """Filter by format returns only matching downloads."""
        _insert_download(fmt="ass", subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(fmt="srt", subtitle_id="s2", file_path="/media/b.mkv")

        result = repo.get_download_history(format="ass")
        assert result["total"] == 1
        assert result["data"][0]["format"] == "ass"

    def test_get_download_history_filter_by_score_range(self, repo):
        """Filter by score_min and score_max returns matching downloads."""
        _insert_download(score=50, subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(score=80, subtitle_id="s2", file_path="/media/b.mkv")
        _insert_download(score=95, subtitle_id="s3", file_path="/media/c.mkv")

        result = repo.get_download_history(score_min=60, score_max=90)
        assert result["total"] == 1
        assert result["data"][0]["score"] == 80

    def test_get_download_history_text_search(self, repo):
        """Search matches file_path and provider_name substrings."""
        _insert_download(
            file_path="/media/naruto/ep01.mkv", subtitle_id="s1", provider="opensubtitles"
        )
        _insert_download(file_path="/media/bleach/ep01.mkv", subtitle_id="s2", provider="addic7ed")

        result = repo.get_download_history(search="naruto")
        assert result["total"] == 1

    def test_get_download_history_sort_by_score_asc(self, repo):
        """Sorting by score ascending works."""
        _insert_download(score=90, subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(score=50, subtitle_id="s2", file_path="/media/b.mkv")

        result = repo.get_download_history(sort_by="score", sort_dir="asc")
        assert result["data"][0]["score"] == 50
        assert result["data"][1]["score"] == 90

    def test_get_download_history_sort_by_score_desc(self, repo):
        """Sorting by score descending works."""
        _insert_download(score=50, subtitle_id="s1", file_path="/media/a.mkv")
        _insert_download(score=90, subtitle_id="s2", file_path="/media/b.mkv")

        result = repo.get_download_history(sort_by="score", sort_dir="desc")
        assert result["data"][0]["score"] == 90
        assert result["data"][1]["score"] == 50

    def test_get_download_history_invalid_sort_field(self, repo):
        """Invalid sort field falls back to downloaded_at."""
        _insert_download(subtitle_id="s1", file_path="/media/a.mkv")

        # Should not raise, falls back to default
        result = repo.get_download_history(sort_by="nonexistent")
        assert result["total"] == 1


# ---------------------------------------------------------------------------
# Download Stats
# ---------------------------------------------------------------------------


class TestDownloadStats:
    def test_get_download_stats_empty(self, repo):
        """Stats with no downloads returns zeroes."""
        stats = repo.get_download_stats()
        assert stats["total_downloads"] == 0
        assert stats["by_provider"] == {}
        assert stats["by_format"] == {}
        assert stats["by_language"] == {}
        assert stats["last_24h"] == 0
        assert stats["last_7d"] == 0

    def test_get_download_stats_aggregated(self, repo):
        """Stats correctly aggregate by provider, format, and language."""
        _insert_download(
            provider="opensubs",
            fmt="ass",
            language="de",
            subtitle_id="s1",
            file_path="/media/a.mkv",
        )
        _insert_download(
            provider="opensubs",
            fmt="srt",
            language="en",
            subtitle_id="s2",
            file_path="/media/b.mkv",
        )
        _insert_download(
            provider="addic7ed",
            fmt="ass",
            language="de",
            subtitle_id="s3",
            file_path="/media/c.mkv",
        )

        stats = repo.get_download_stats()
        assert stats["total_downloads"] == 3
        assert stats["by_provider"]["opensubs"] == 2
        assert stats["by_provider"]["addic7ed"] == 1
        assert stats["by_format"]["ass"] == 2
        assert stats["by_format"]["srt"] == 1
        assert stats["by_language"]["de"] == 2
        assert stats["by_language"]["en"] == 1
        assert stats["last_24h"] == 3
        assert stats["last_7d"] == 3


# ---------------------------------------------------------------------------
# Upgrade History
# ---------------------------------------------------------------------------


class TestUpgradeHistory:
    def test_record_and_get_upgrade(self, repo):
        """Recording an upgrade stores it and it can be retrieved."""
        repo.record_upgrade(
            file_path="/media/test.mkv",
            old_format="srt",
            old_score=60,
            new_format="ass",
            new_score=90,
            provider_name="opensubtitles",
            upgrade_reason="Better format available",
        )

        history = repo.get_upgrade_history(limit=10)
        assert len(history) == 1
        entry = history[0]
        assert entry["file_path"] == "/media/test.mkv"
        assert entry["old_format"] == "srt"
        assert entry["old_score"] == 60
        assert entry["new_format"] == "ass"
        assert entry["new_score"] == 90
        assert entry["provider_name"] == "opensubtitles"
        assert entry["upgrade_reason"] == "Better format available"

    def test_get_upgrade_history_ordered_desc(self, repo):
        """Upgrade history is ordered by upgraded_at descending."""
        repo.record_upgrade("/media/a.mkv", "srt", 50, "ass", 80)
        repo.record_upgrade("/media/b.mkv", "srt", 60, "ass", 90)

        history = repo.get_upgrade_history()
        assert history[0]["file_path"] == "/media/b.mkv"  # most recent

    def test_get_upgrade_history_limit(self, repo):
        """Upgrade history respects limit parameter."""
        for i in range(10):
            repo.record_upgrade(f"/media/f{i}.mkv", "srt", 50, "ass", 80)

        history = repo.get_upgrade_history(limit=3)
        assert len(history) == 3

    def test_get_upgrade_history_empty(self, repo):
        """Empty upgrade history returns empty list."""
        assert repo.get_upgrade_history() == []


# ---------------------------------------------------------------------------
# Upgrade Stats
# ---------------------------------------------------------------------------


class TestUpgradeStats:
    def test_get_upgrade_stats_empty(self, repo):
        """Stats with no upgrades returns zeroes."""
        stats = repo.get_upgrade_stats()
        assert stats["total"] == 0
        assert stats["srt_to_ass"] == 0

    def test_get_upgrade_stats_counts(self, repo):
        """Stats correctly count total and srt_to_ass upgrades."""
        repo.record_upgrade("/media/a.mkv", "srt", 50, "ass", 80)
        repo.record_upgrade("/media/b.mkv", "srt", 60, "ass", 90)
        repo.record_upgrade("/media/c.mkv", "ass", 70, "ass", 95)  # not srt->ass

        stats = repo.get_upgrade_stats()
        assert stats["total"] == 3
        assert stats["srt_to_ass"] == 2


# ---------------------------------------------------------------------------
# Delete Download Record
# ---------------------------------------------------------------------------


class TestDeleteDownloadRecord:
    def test_delete_download_record(self, repo):
        """Deleting a download record removes it by file_path."""
        _insert_download(file_path="/media/delete_me.mkv", subtitle_id="del1")

        repo.delete_download_record("/media/delete_me.mkv")

        result = repo.get_download_history()
        assert result["total"] == 0

    def test_delete_download_record_nonexistent(self, repo):
        """Deleting a non-existent download record does not raise."""
        repo.delete_download_record("/media/nonexistent.mkv")
