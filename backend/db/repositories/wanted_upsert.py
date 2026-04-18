"""Upsert mixin for WantedRepository.

Extracted from db/repositories/wanted.py. Holds the single large
``upsert_wanted_item`` method that was dominating the repository file.
Behaviour is unchanged: matches on file_path + target_language +
subtitle_type, respects the ``ignored`` status, races against concurrent
inserts via IntegrityError handling.
"""

import json
import logging
import os

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from db.models.core import WantedItem

logger = logging.getLogger(__name__)


class _WantedUpsertMixin:
    """``upsert_wanted_item`` method composed into WantedRepository."""

    def upsert_wanted_item(
        self,
        item_type: str,
        file_path: str,
        title: str = "",
        season_episode: str = "",
        existing_sub: str = "",
        missing_languages: list = None,
        sonarr_series_id: int = None,
        sonarr_episode_id: int = None,
        radarr_movie_id: int = None,
        standalone_series_id: int = None,
        standalone_movie_id: int = None,
        upgrade_candidate: bool = False,
        current_score: int = 0,
        target_language: str = "",
        instance_name: str = "",
        subtitle_type: str = "full",
        embedded_languages: list = None,
    ) -> tuple:
        """Insert or update a wanted item (matched on file_path + target_language + subtitle_type).

        The uniqueness check includes subtitle_type so that a single file can have
        parallel wanted items for different subtitle types (e.g., full + forced)
        in the same language.

        Returns (row_id, was_updated) where was_updated=True if an existing row
        was updated, False if a new row was inserted.
        """
        # Normalize path separators to avoid duplicate rows from mixed / and \ paths
        file_path = os.path.normpath(file_path) if file_path else file_path
        now = self._now()
        langs_json = json.dumps(missing_languages or [])
        embedded_json = json.dumps(embedded_languages) if embedded_languages is not None else None
        upgrade_int = 1 if upgrade_candidate else 0

        # Match on file_path + target_language + subtitle_type for multi-language + multi-type support
        if target_language:
            stmt = select(WantedItem).where(
                WantedItem.file_path == file_path,
                WantedItem.target_language == target_language,
                WantedItem.subtitle_type == subtitle_type,
            )
        else:
            stmt = select(WantedItem).where(
                WantedItem.file_path == file_path,
                or_(
                    WantedItem.target_language == "",
                    WantedItem.target_language.is_(None),
                ),
                WantedItem.subtitle_type == subtitle_type,
            )

        existing = self.session.execute(stmt).scalars().first()

        if existing:
            row_id = existing.id
            # Don't overwrite 'ignored' status — but update all other fields
            if existing.status == "ignored":
                existing.item_type = item_type
                existing.title = title
                existing.season_episode = season_episode
                existing.existing_sub = existing_sub
                existing.missing_languages = langs_json
                if embedded_json is not None:
                    existing.embedded_languages = embedded_json
                existing.sonarr_series_id = sonarr_series_id
                existing.sonarr_episode_id = sonarr_episode_id
                existing.radarr_movie_id = radarr_movie_id
                existing.standalone_series_id = standalone_series_id
                existing.standalone_movie_id = standalone_movie_id
                existing.upgrade_candidate = upgrade_int
                existing.current_score = current_score
                existing.target_language = target_language
                existing.instance_name = instance_name
                existing.subtitle_type = subtitle_type
                existing.updated_at = now
            else:
                existing.item_type = item_type
                existing.title = title
                existing.season_episode = season_episode
                existing.existing_sub = existing_sub
                existing.missing_languages = langs_json
                if embedded_json is not None:
                    existing.embedded_languages = embedded_json
                existing.status = "wanted"
                existing.sonarr_series_id = sonarr_series_id
                existing.sonarr_episode_id = sonarr_episode_id
                existing.radarr_movie_id = radarr_movie_id
                existing.standalone_series_id = standalone_series_id
                existing.standalone_movie_id = standalone_movie_id
                existing.upgrade_candidate = upgrade_int
                existing.current_score = current_score
                existing.target_language = target_language
                existing.instance_name = instance_name
                existing.subtitle_type = subtitle_type
                existing.updated_at = now
            self._commit()
            return row_id, True

        item = WantedItem(
            item_type=item_type,
            file_path=file_path,
            title=title,
            season_episode=season_episode,
            existing_sub=existing_sub,
            missing_languages=langs_json,
            embedded_languages=embedded_json if embedded_json is not None else "[]",
            sonarr_series_id=sonarr_series_id,
            sonarr_episode_id=sonarr_episode_id,
            radarr_movie_id=radarr_movie_id,
            standalone_series_id=standalone_series_id,
            standalone_movie_id=standalone_movie_id,
            upgrade_candidate=upgrade_int,
            current_score=current_score,
            target_language=target_language,
            instance_name=instance_name,
            subtitle_type=subtitle_type,
            status="wanted",
            added_at=now,
            updated_at=now,
        )
        try:
            self.session.add(item)
            self.session.flush()  # populate item.id even in batch mode (no-op _commit)
            self._commit()
            return item.id, False
        except IntegrityError:
            # Concurrent insert won the race — roll back and fetch the winner
            self.session.rollback()
            existing = self.session.execute(stmt).scalars().first()
            if existing:
                logger.debug(
                    "Race condition on upsert for %s — returning existing %d",
                    file_path,
                    existing.id,
                )
                return existing.id, True
            raise
