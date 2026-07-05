"""Upsert mixin for WantedRepository.

Extracted from db/repositories/wanted.py. Holds the single large
``upsert_wanted_item`` method that was dominating the repository file.
Behaviour is unchanged: matches on file_path + target_language +
subtitle_type, respects the ``ignored`` status, races against concurrent
inserts via IntegrityError handling.

2026-05-09 (0.92.4-beta): adds a ``_prune_replaced_siblings`` step that
removes wanted_items shadowed by a Sonarr/Radarr quality upgrade. The
upsert match key is ``file_path + target_language + subtitle_type``;
when Sonarr swaps ``WEBRip-1080p.mkv`` for ``WEBDL-1080p.mkv``, the new
file lands as a fresh row while the old row is left orphaned with a
file_path that no longer exists on disk. The sweep deletes such stale
siblings transactionally so the UI stops showing duplicate
``File not found on disk`` rows for the same episode.
"""

import json
import logging
import os

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from db.models.core import WantedItem

logger = logging.getLogger(__name__)


class _WantedUpsertMixin:
    """``upsert_wanted_item`` method composed into WantedRepository."""

    def _prune_replaced_siblings(
        self,
        *,
        keep_id: int,
        keep_file_path: str,
        target_language: str,
        subtitle_type: str,
        sonarr_episode_id: int | None,
        radarr_movie_id: int | None,
        standalone_series_id: int | None,
        standalone_movie_id: int | None,
        season_episode: str,
    ) -> int:
        """Delete sibling wanted_items shadowed by ``keep_id``.

        A sibling is any wanted_item with the same ``(target_language,
        subtitle_type)`` and the same logical media entity (Sonarr
        episode, Radarr movie, or standalone series+S/E / movie) but a
        DIFFERENT ``file_path`` whose file no longer exists on disk.

        Mount-blip defence: the sweep only runs when the freshly
        upserted ``keep_file_path`` actually exists on disk. That is the
        same posture the cleanup executors use (audit C0-3 / standalone
        S0-1) — without proof the mount is reachable we never call
        ``os.path.exists`` on legacy paths and risk wrongly pruning
        rows for a temporarily-unavailable share.

        Returns the number of rows deleted.
        """
        if not target_language:
            # Without a target_language we can't identify siblings safely.
            return 0
        if not keep_file_path or not os.path.exists(keep_file_path):
            # Mount unreachable or path empty — refuse to prune.
            return 0

        identity_filter = None
        if sonarr_episode_id:
            identity_filter = WantedItem.sonarr_episode_id == sonarr_episode_id
        elif radarr_movie_id:
            identity_filter = WantedItem.radarr_movie_id == radarr_movie_id
        elif standalone_series_id and season_episode:
            from sqlalchemy import and_

            identity_filter = and_(
                WantedItem.standalone_series_id == standalone_series_id,
                WantedItem.season_episode == season_episode,
            )
        elif standalone_movie_id:
            identity_filter = WantedItem.standalone_movie_id == standalone_movie_id
        else:
            # No reliable logical identity (e.g., orphaned legacy row) —
            # skip the prune to avoid false-positives.
            return 0

        sibling_stmt = select(WantedItem).where(
            WantedItem.id != keep_id,
            WantedItem.target_language == target_language,
            WantedItem.subtitle_type == subtitle_type,
            identity_filter,
        )
        candidates = self.session.execute(sibling_stmt).scalars().all()

        deleted_ids: list[int] = []
        for sib in candidates:
            sib_path = sib.file_path
            if not sib_path:
                # Path already empty — treat as stale.
                self.session.delete(sib)
                deleted_ids.append(sib.id)
                continue
            # Normalise both sides so a / vs \ mismatch never marks the
            # current path as stale-by-string.
            if os.path.normpath(sib_path) == os.path.normpath(keep_file_path):
                continue
            try:
                exists = os.path.exists(sib_path)
            except OSError:
                # Mount went away mid-prune — bail; better to keep the
                # row than to risk a wrongful delete.
                continue
            if not exists:
                self.session.delete(sib)
                deleted_ids.append(sib.id)

        if deleted_ids:
            logger.info(
                "upsert_wanted_item: pruned %d shadowed sibling row(s) for %s (file: %s)",
                len(deleted_ids),
                target_language,
                keep_file_path,
            )
            self._commit()
        return len(deleted_ids)

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
        *,
        _retry: bool = False,
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
            try:
                self._commit()
            except StaleDataError:
                # The matched row was deleted concurrently (a parallel scan,
                # standalone cleanup, or _prune_replaced_siblings) between our
                # SELECT and this flush, so the UPDATE matched 0 rows. Recover
                # by rolling back and re-running the upsert once — the retry
                # re-SELECTs and inserts a fresh row (or adopts a concurrent
                # insert winner via the IntegrityError path). Without this the
                # StaleDataError propagates and poisons the shared session,
                # cascading to every later item in the same scan.
                self.session.rollback()
                if _retry:
                    raise
                return self.upsert_wanted_item(
                    item_type=item_type,
                    file_path=file_path,
                    title=title,
                    season_episode=season_episode,
                    existing_sub=existing_sub,
                    missing_languages=missing_languages,
                    sonarr_series_id=sonarr_series_id,
                    sonarr_episode_id=sonarr_episode_id,
                    radarr_movie_id=radarr_movie_id,
                    standalone_series_id=standalone_series_id,
                    standalone_movie_id=standalone_movie_id,
                    upgrade_candidate=upgrade_candidate,
                    current_score=current_score,
                    target_language=target_language,
                    instance_name=instance_name,
                    subtitle_type=subtitle_type,
                    embedded_languages=embedded_languages,
                    _retry=True,
                )
            self._prune_replaced_siblings(
                keep_id=row_id,
                keep_file_path=file_path,
                target_language=target_language,
                subtitle_type=subtitle_type,
                sonarr_episode_id=sonarr_episode_id,
                radarr_movie_id=radarr_movie_id,
                standalone_series_id=standalone_series_id,
                standalone_movie_id=standalone_movie_id,
                season_episode=season_episode,
            )
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
            self._prune_replaced_siblings(
                keep_id=item.id,
                keep_file_path=file_path,
                target_language=target_language,
                subtitle_type=subtitle_type,
                sonarr_episode_id=sonarr_episode_id,
                radarr_movie_id=radarr_movie_id,
                standalone_series_id=standalone_series_id,
                standalone_movie_id=standalone_movie_id,
                season_episode=season_episode,
            )
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
                self._prune_replaced_siblings(
                    keep_id=existing.id,
                    keep_file_path=file_path,
                    target_language=target_language,
                    subtitle_type=subtitle_type,
                    sonarr_episode_id=sonarr_episode_id,
                    radarr_movie_id=radarr_movie_id,
                    standalone_series_id=standalone_series_id,
                    standalone_movie_id=standalone_movie_id,
                    season_episode=season_episode,
                )
                return existing.id, True
            raise
