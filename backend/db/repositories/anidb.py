"""AniDB absolute episode order repository.

Provides CRUD operations for the anidb_absolute_mappings table and
read/write access to the series_settings table for the absolute_order flag.

These are populated by the AniDB sync job (anidb_sync.py) which fetches
the anime-lists XML from GitHub weekly.
"""

import logging

from sqlalchemy import delete, select

from db.models.core import AnidbAbsoluteMapping, SeriesSettings
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AnidbRepository(BaseRepository):
    """Repository for AniDB absolute episode mappings and series settings."""

    # ---- Absolute episode lookups -------------------------------------------

    def get_anidb_absolute(
        self, tvdb_id: int, season: int, episode: int
    ) -> int | None:
        """Return the AniDB absolute episode number for a given TVDB S/E.

        Returns:
            Absolute episode number as int, or None if no mapping exists.
        """
        row = self.session.execute(
            select(AnidbAbsoluteMapping.anidb_absolute_episode).where(
                AnidbAbsoluteMapping.tvdb_id == tvdb_id,
                AnidbAbsoluteMapping.season == season,
                AnidbAbsoluteMapping.episode == episode,
            )
        ).scalar_one_or_none()
        return row

    def upsert_mapping(
        self,
        tvdb_id: int,
        season: int,
        episode: int,
        anidb_absolute_episode: int,
        source: str | None = None,
    ) -> None:
        """Insert or update an absolute episode mapping.

        Uses the unique constraint (tvdb_id, season, episode) to decide
        whether to insert a new row or update the existing one.
        """
        now = self._now()
        existing = self.session.execute(
            select(AnidbAbsoluteMapping).where(
                AnidbAbsoluteMapping.tvdb_id == tvdb_id,
                AnidbAbsoluteMapping.season == season,
                AnidbAbsoluteMapping.episode == episode,
            )
        ).scalar_one_or_none()

        if existing:
            existing.anidb_absolute_episode = anidb_absolute_episode
            existing.updated_at = now
            if source is not None:
                existing.source = source
        else:
            new_row = AnidbAbsoluteMapping(
                tvdb_id=tvdb_id,
                season=season,
                episode=episode,
                anidb_absolute_episode=anidb_absolute_episode,
                updated_at=now,
                source=source,
            )
            self.session.add(new_row)

        self._commit()

    def list_by_tvdb(self, tvdb_id: int) -> list:
        """Return all absolute mappings for a given TVDB series ID.

        Returns:
            List of dicts with keys: id, tvdb_id, season, episode,
            anidb_absolute_episode, updated_at, source.
        """
        rows = self.session.execute(
            select(AnidbAbsoluteMapping)
            .where(AnidbAbsoluteMapping.tvdb_id == tvdb_id)
            .order_by(AnidbAbsoluteMapping.season, AnidbAbsoluteMapping.episode)
        ).scalars().all()
        return [self._to_dict(r) for r in rows]

    def clear_for_tvdb(self, tvdb_id: int) -> int:
        """Delete all absolute mappings for a given TVDB series ID.

        Returns:
            Number of rows deleted.
        """
        result = self.session.execute(
            delete(AnidbAbsoluteMapping).where(
                AnidbAbsoluteMapping.tvdb_id == tvdb_id
            )
        )
        self._commit()
        deleted = result.rowcount
        logger.debug("Cleared %d AniDB absolute mappings for TVDB %d", deleted, tvdb_id)
        return deleted

    def clear_all(self) -> int:
        """Delete all rows from anidb_absolute_mappings.

        Used before a full re-sync from the anime-lists XML.

        Returns:
            Number of rows deleted.
        """
        result = self.session.execute(delete(AnidbAbsoluteMapping))
        self._commit()
        return result.rowcount

    def count_mappings(self) -> int:
        """Return the total number of stored absolute episode mappings."""
        from sqlalchemy import func
        return self.session.execute(
            select(func.count()).select_from(AnidbAbsoluteMapping)
        ).scalar() or 0

    # ---- Series settings (absolute_order flag) --------------------------------

    def get_absolute_order(self, sonarr_series_id: int) -> bool:
        """Return True if the series has absolute_order enabled."""
        row = self.session.execute(
            select(SeriesSettings.absolute_order).where(
                SeriesSettings.sonarr_series_id == sonarr_series_id
            )
        ).scalar_one_or_none()
        return bool(row) if row is not None else False

    def set_absolute_order(self, sonarr_series_id: int, enabled: bool) -> None:
        """Enable or disable absolute_order mode for a series."""
        now = self._now()
        existing = self.session.get(SeriesSettings, sonarr_series_id)
        if existing:
            existing.absolute_order = 1 if enabled else 0
            existing.updated_at = now
        else:
            self.session.add(
                SeriesSettings(
                    sonarr_series_id=sonarr_series_id,
                    absolute_order=1 if enabled else 0,
                    updated_at=now,
                )
            )
        self._commit()
        logger.debug(
            "Series %d absolute_order set to %s", sonarr_series_id, enabled
        )

    def get_series_settings(self, sonarr_series_id: int) -> dict | None:
        """Return the full settings dict for a series, or None if not set."""
        row = self.session.get(SeriesSettings, sonarr_series_id)
        return self._to_dict(row) if row else None

    def list_series_with_absolute_order(self) -> list:
        """Return all series IDs that have absolute_order enabled.

        Returns:
            List of sonarr_series_id integers.
        """
        rows = self.session.execute(
            select(SeriesSettings.sonarr_series_id).where(
                SeriesSettings.absolute_order == 1
            )
        ).scalars().all()
        return list(rows)
