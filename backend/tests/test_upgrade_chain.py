"""Tests for upgrade chain tracking (upgraded_from_id in subtitle_downloads)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


def test_subtitle_download_has_upgraded_from_id():
    from db.models.providers import SubtitleDownload

    assert hasattr(SubtitleDownload, "upgraded_from_id")


def test_record_subtitle_download_accepts_upgraded_from_id():
    """record_subtitle_download stores upgraded_from_id when provided."""
    from db.repositories.providers import ProviderRepository

    mock_session = MagicMock()
    with patch("db.repositories.base.db") as mock_db:
        mock_db.session = mock_session

        repo = ProviderRepository.__new__(ProviderRepository)
        repo._local = __import__("threading").local()
        repo._now = lambda: datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        repo.record_subtitle_download(
            "opensubtitles",
            "sub123",
            "de",
            "ass",
            "/media/ep.mkv",
            200,
            source="provider",
            upgraded_from_id=42,
        )

    call_args = mock_session.add.call_args[0][0]
    assert call_args.upgraded_from_id == 42


def test_record_subtitle_download_upgraded_from_id_defaults_to_none():
    """upgraded_from_id defaults to None when not provided."""
    from db.repositories.providers import ProviderRepository

    mock_session = MagicMock()
    with patch("db.repositories.base.db") as mock_db:
        mock_db.session = mock_session

        repo = ProviderRepository.__new__(ProviderRepository)
        repo._local = __import__("threading").local()
        repo._now = lambda: datetime(2026, 3, 28, 12, 0, 0, tzinfo=UTC)

        repo.record_subtitle_download(
            "opensubtitles",
            "sub456",
            "de",
            "srt",
            "/media/ep2.mkv",
            150,
        )

    call_args = mock_session.add.call_args[0][0]
    assert call_args.upgraded_from_id is None


def test_get_latest_download_id_returns_none_when_no_records():
    from db.repositories.providers import ProviderRepository

    mock_session = MagicMock()
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with patch("db.repositories.base.db") as mock_db:
        mock_db.session = mock_session

        repo = ProviderRepository.__new__(ProviderRepository)
        repo._local = __import__("threading").local()

        result = repo.get_latest_download_id("/no/such/path.mkv")

    assert result is None


def test_episode_history_includes_upgraded_from_id():
    """get_episode_history entries must include upgraded_from_id field."""
    from datetime import UTC, datetime
    from unittest.mock import MagicMock, patch

    mock_session = MagicMock()
    # Simulate one SubtitleDownload row with upgraded_from_id=7
    mock_row = MagicMock()
    mock_row.provider_name = "jimaku"
    mock_row.format = "ass"
    mock_row.score = 200
    mock_row.downloaded_at = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    mock_row.upgraded_from_id = 7
    # First execute() call returns download rows; second returns empty job rows
    mock_session.execute.return_value.all.side_effect = [[mock_row], []]

    with patch("db.repositories.base.db") as mock_db:
        mock_db.session = mock_session
        from db.repositories.cache import CacheRepository

        repo = CacheRepository.__new__(CacheRepository)
        repo._local = __import__("threading").local()
        entries = repo.get_episode_history("/media/ep.mkv")

    assert len(entries) >= 1
    dl_entry = next(e for e in entries if e.get("action") == "download")
    assert "upgraded_from_id" in dl_entry
    assert dl_entry["upgraded_from_id"] == 7
