"""Tests for services.episode_video_path.resolve_episode_video_path (V1.6 GAP-B).

Episode combine/upload/track endpoints previously resolved paths via the Sonarr
client only, returning 503 on a standalone install. The resolver now also
handles standalone episodes (wanted_items rows keyed by id).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from services.episode_video_path import resolve_episode_video_path


def test_sonarr_mode_returns_mapped_existing_path(app_ctx):
    client = MagicMock()
    client.get_episode_file_path.return_value = "/sonarr/media/ep.mkv"
    with (
        patch("sonarr_client.get_sonarr_client", return_value=client),
        patch("config.map_path", return_value="/local/media/ep.mkv"),
        patch("os.path.exists", return_value=True),
    ):
        assert resolve_episode_video_path(42) == "/local/media/ep.mkv"
    client.get_episode_file_path.assert_called_once_with(42)


def test_sonarr_mode_missing_file_returns_none(app_ctx):
    client = MagicMock()
    client.get_episode_file_path.return_value = None
    with patch("sonarr_client.get_sonarr_client", return_value=client):
        assert resolve_episode_video_path(99) is None


def test_standalone_mode_resolves_via_wanted_items(app_ctx, temp_db, tmp_path):
    from db.models.core import WantedItem
    from extensions import db

    video = tmp_path / "ep.mkv"
    video.write_bytes(b"x")
    now = datetime.now(UTC)
    wi = WantedItem(
        item_type="episode",
        title="Standalone Ep",
        file_path=str(video),
        standalone_series_id=1,
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    db.session.add(wi)
    db.session.commit()

    with patch("sonarr_client.get_sonarr_client", return_value=None):
        # Known standalone episode → its video path.
        assert resolve_episode_video_path(wi.id) == str(video)
        # Unknown id → None (was a 503 before the fix).
        assert resolve_episode_video_path(wi.id + 9999) is None


def test_standalone_row_without_file_on_disk_returns_none(app_ctx, temp_db, tmp_path):
    from db.models.core import WantedItem
    from extensions import db

    now = datetime.now(UTC)
    wi = WantedItem(
        item_type="episode",
        title="Gone",
        file_path=str(tmp_path / "missing.mkv"),
        standalone_series_id=1,
        status="wanted",
        added_at=now,
        updated_at=now,
    )
    db.session.add(wi)
    db.session.commit()

    with patch("sonarr_client.get_sonarr_client", return_value=None):
        assert resolve_episode_video_path(wi.id) is None
