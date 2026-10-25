"""Repository for per-series audio track preferences.

Reads and writes preferred_audio_track_index on the series_settings table.
Uses UPSERT semantics: creates the row if it does not exist yet.
"""

import logging

from db.models.core import SeriesSettings
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SeriesAudioRepository(BaseRepository):
    """Read/write preferred_audio_track_index in series_settings."""

    def get_audio_track_pref(self, series_id: int) -> int | None:
        """Return the pinned audio track index for a series, or None if not set."""
        from services.standalone_owner_keys import get_row

        row = get_row(SeriesSettings, series_id)
        return row.preferred_audio_track_index if row else None

    def set_audio_track_pref(self, series_id: int, track_index: int | None) -> None:
        """Persist preferred_audio_track_index for a series.

        Creates a series_settings row if one does not exist yet.
        Pass track_index=None to clear the preference (auto-select resumes).
        """
        from services.standalone_owner_keys import row_for_write

        now = self._now()
        row = row_for_write(SeriesSettings, series_id, absolute_order=0, updated_at=now)
        row.preferred_audio_track_index = track_index
        row.updated_at = now
        self._commit()
        logger.debug("Series %d preferred_audio_track_index -> %s", series_id, track_index)
