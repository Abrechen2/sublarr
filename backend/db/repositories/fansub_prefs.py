"""Repository for per-series fansub group preferences."""

import json
import logging

from db.models.core import FansubPreference
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FansubPreferenceRepository(BaseRepository):
    """Read/write fansub group preferences for a series."""

    def get_fansub_prefs(self, series_id: int) -> dict | None:
        """Return fansub prefs for series_id, or None if not set."""
        row = self.session.get(FansubPreference, series_id)
        if row is None:
            return None
        return {
            "series_id": series_id,
            "preferred_groups": json.loads(row.preferred_groups_json),
            "excluded_groups": json.loads(row.excluded_groups_json),
            "bonus": row.bonus,
        }

    def set_fansub_prefs(
        self,
        series_id: int,
        preferred: list[str],
        excluded: list[str],
        bonus: int,
    ) -> None:
        """Upsert fansub preferences for series_id."""
        now = self._now()
        existing = self.session.get(FansubPreference, series_id)
        if existing:
            existing.preferred_groups_json = json.dumps(preferred)
            existing.excluded_groups_json = json.dumps(excluded)
            existing.bonus = bonus
            existing.updated_at = now
        else:
            self.session.add(
                FansubPreference(
                    sonarr_series_id=series_id,
                    preferred_groups_json=json.dumps(preferred),
                    excluded_groups_json=json.dumps(excluded),
                    bonus=bonus,
                    updated_at=now,
                )
            )
        self._commit()
        logger.debug("Series %d fansub prefs updated", series_id)

    def delete_fansub_prefs(self, series_id: int) -> None:
        """Remove fansub preferences row for series_id (no-op if absent)."""
        row = self.session.get(FansubPreference, series_id)
        if row:
            self.session.delete(row)
            self._commit()
            logger.debug("Series %d fansub prefs deleted", series_id)
