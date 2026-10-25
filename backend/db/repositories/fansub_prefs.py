"""Repository for per-series fansub group preferences."""

import json
import logging

from db.models.core import FansubPreference
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class FansubPreferenceRepository(BaseRepository):
    """Read/write fansub group preferences for a series."""

    def get_fansub_prefs(self, series_id: int) -> dict | None:
        """Return fansub prefs for series_id, or None if not set.

        A standalone owner key without its own row reads the pre-1.18 row
        where allowed (services/standalone_owner_keys.py).
        """
        from services.standalone_owner_keys import get_row

        row = get_row(FansubPreference, series_id)
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
        from services.standalone_owner_keys import row_for_write

        now = self._now()
        row = row_for_write(FansubPreference, series_id, updated_at=now)
        row.preferred_groups_json = json.dumps(preferred)
        row.excluded_groups_json = json.dumps(excluded)
        row.bonus = bonus
        row.updated_at = now
        self._commit()
        logger.debug("Series %d fansub prefs updated", series_id)

    def delete_fansub_prefs(self, series_id: int) -> None:
        """Remove fansub preferences row for series_id (no-op if absent)."""
        from services.standalone_owner_keys import SERIES, claim

        claimed = claim(series_id, SERIES) is not None
        row = self.session.get(FansubPreference, series_id)
        if row:
            self.session.delete(row)
            logger.debug("Series %d fansub prefs deleted", series_id)
        if row or claimed:
            self._commit()
