"""Repository for ``standalone_episodes`` — the stable identity of a standalone
episode file (see docs/specs/standalone-ids.md).

One row per video file. The API exposes ``-id``; ``services.media_ids`` does
the conversion. Rows are written by the standalone scanner and the series
detail, and removed with their series or when the file is gone.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from db.models.standalone import StandaloneEpisode
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class StandaloneEpisodeRepository(BaseRepository):
    """CRUD for standalone episode identities."""

    def _find_by_path(self, file_path: str) -> StandaloneEpisode | None:
        stmt = select(StandaloneEpisode).where(StandaloneEpisode.file_path == file_path)
        return self.session.execute(stmt).scalars().first()

    def upsert_episode(
        self,
        series_id: int,
        file_path: str,
        season: int | None = None,
        episode: int | None = None,
    ) -> dict:
        """Return the row for ``file_path``, creating or re-parenting it.

        Race-safe: an insert that loses to a concurrent writer on the unique
        ``file_path`` rolls back and updates the winner's row instead.
        """
        now = self._now()

        def _apply(row: StandaloneEpisode) -> bool:
            changed = (row.standalone_series_id, row.season, row.episode) != (
                series_id,
                season,
                episode,
            )
            if changed:
                row.standalone_series_id = series_id
                row.season = season
                row.episode = episode
                row.updated_at = now
            return changed

        existing = self._find_by_path(file_path)
        if existing is not None:
            if _apply(existing):
                self._commit()
            return self._to_dict(existing)

        row = StandaloneEpisode(
            standalone_series_id=series_id,
            file_path=file_path,
            season=season,
            episode=episode,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        try:
            self._commit()
            return self._to_dict(row)
        except IntegrityError:
            self.session.rollback()
            existing = self._find_by_path(file_path)
            if existing is None:
                raise
            if _apply(existing):
                self._commit()
            return self._to_dict(existing)

    def get_episode(self, episode_id: int) -> dict | None:
        row = self.session.get(StandaloneEpisode, episode_id)
        return self._to_dict(row) if row else None

    def get_episode_by_path(self, file_path: str) -> dict | None:
        row = self._find_by_path(file_path)
        return self._to_dict(row) if row else None

    def get_episodes_for_series(self, series_id: int) -> list[dict]:
        stmt = (
            select(StandaloneEpisode)
            .where(StandaloneEpisode.standalone_series_id == series_id)
            .order_by(StandaloneEpisode.file_path)
        )
        return [self._to_dict(r) for r in self.session.execute(stmt).scalars().all()]

    def get_all_episodes(self) -> list[dict]:
        stmt = select(StandaloneEpisode).order_by(StandaloneEpisode.id)
        return [self._to_dict(r) for r in self.session.execute(stmt).scalars().all()]

    def delete_episodes_for_series(self, series_id: int) -> int:
        result = self.session.execute(
            delete(StandaloneEpisode).where(StandaloneEpisode.standalone_series_id == series_id)
        )
        self._commit()
        return result.rowcount or 0

    def delete_episodes_by_ids(self, ids: list[int]) -> int:
        if not ids:
            return 0
        result = self.session.execute(
            delete(StandaloneEpisode).where(StandaloneEpisode.id.in_(list(ids)))
        )
        self._commit()
        return result.rowcount or 0
