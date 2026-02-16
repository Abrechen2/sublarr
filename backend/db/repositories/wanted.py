"""Wanted items repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/wanted.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly.

CRITICAL: The upsert logic matches on file_path + target_language + subtitle_type
with conditional handling for empty/null target_language.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, delete, and_, or_

from db.models.core import WantedItem
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WantedRepository(BaseRepository):
    """Repository for wanted_items table operations."""

    def upsert_wanted_item(self, item_type: str, file_path: str, title: str = "",
                           season_episode: str = "", existing_sub: str = "",
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
                           subtitle_type: str = "full") -> int:
        """Insert or update a wanted item (matched on file_path + target_language + subtitle_type).

        The uniqueness check includes subtitle_type so that a single file can have
        parallel wanted items for different subtitle types (e.g., full + forced)
        in the same language.

        Returns the row id.
        """
        now = self._now()
        langs_json = json.dumps(missing_languages or [])
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
            # Don't overwrite 'ignored' status
            if existing.status == "ignored":
                existing.title = title
                existing.season_episode = season_episode
                existing.existing_sub = existing_sub
                existing.missing_languages = langs_json
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
        else:
            item = WantedItem(
                item_type=item_type,
                file_path=file_path,
                title=title,
                season_episode=season_episode,
                existing_sub=existing_sub,
                missing_languages=langs_json,
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
            self.session.add(item)
            self._commit()
            row_id = item.id
            return row_id

        self._commit()
        return row_id

    def get_wanted_items(self, page: int = 1, per_page: int = 50,
                         item_type: str = None, status: str = None,
                         series_id: int = None,
                         subtitle_type: str = None) -> dict:
        """Get paginated wanted items with optional filters."""
        offset = (page - 1) * per_page

        conditions = []
        if item_type:
            conditions.append(WantedItem.item_type == item_type)
        if status:
            conditions.append(WantedItem.status == status)
        if series_id is not None:
            conditions.append(WantedItem.sonarr_series_id == series_id)
        if subtitle_type:
            conditions.append(WantedItem.subtitle_type == subtitle_type)

        # Count query
        count_stmt = select(func.count()).select_from(WantedItem)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count = self.session.execute(count_stmt).scalar()

        # Data query
        data_stmt = (
            select(WantedItem)
            .order_by(WantedItem.added_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(*conditions)
        rows = self.session.execute(data_stmt).scalars().all()

        total_pages = max(1, (count + per_page - 1) // per_page)
        return {
            "data": [self._row_to_wanted(r) for r in rows],
            "page": page,
            "per_page": per_page,
            "total": count,
            "total_pages": total_pages,
        }

    def get_wanted_item(self, item_id: int) -> Optional[dict]:
        """Get a single wanted item by ID."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return None
        return self._row_to_wanted(item)

    def get_wanted_by_file_path(self, file_path: str,
                                target_language: str = None,
                                subtitle_type: str = None) -> Optional[dict]:
        """Get a wanted item by file path (optionally with language/type filter)."""
        stmt = select(WantedItem).where(WantedItem.file_path == file_path)
        if target_language is not None:
            stmt = stmt.where(WantedItem.target_language == target_language)
        if subtitle_type is not None:
            stmt = stmt.where(WantedItem.subtitle_type == subtitle_type)
        item = self.session.execute(stmt).scalars().first()
        if not item:
            return None
        return self._row_to_wanted(item)

    def update_wanted_status(self, item_id: int, status: str,
                             error: str = "") -> bool:
        """Update a wanted item's status."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.status = status
        item.error = error
        item.updated_at = self._now()
        self._commit()
        return True

    def mark_search_attempted(self, item_id: int) -> bool:
        """Increment search_count and set last_search_at."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        now = self._now()
        item.search_count = (item.search_count or 0) + 1
        item.last_search_at = now
        item.updated_at = now
        self._commit()
        return True

    def get_wanted_summary(self) -> dict:
        """Get aggregated wanted counts by type, status, and existing_sub."""
        total_stmt = select(func.count()).select_from(WantedItem)
        total = self.session.execute(total_stmt).scalar()

        # By type
        by_type_stmt = select(
            WantedItem.item_type, func.count()
        ).group_by(WantedItem.item_type)
        by_type = {
            row[0]: row[1]
            for row in self.session.execute(by_type_stmt).all()
        }

        # By status
        by_status_stmt = select(
            WantedItem.status, func.count()
        ).group_by(WantedItem.status)
        by_status = {
            row[0]: row[1]
            for row in self.session.execute(by_status_stmt).all()
        }

        # By existing_sub
        by_existing_stmt = select(
            WantedItem.existing_sub, func.count()
        ).group_by(WantedItem.existing_sub)
        by_existing = {}
        for row in self.session.execute(by_existing_stmt).all():
            key = row[0] if row[0] else "none"
            by_existing[key] = row[1]

        # Upgradeable
        upgradeable_stmt = select(func.count()).select_from(WantedItem).where(
            WantedItem.upgrade_candidate == 1
        )
        upgradeable = self.session.execute(upgradeable_stmt).scalar()

        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
            "by_existing": by_existing,
            "upgradeable": upgradeable,
        }

    def get_wanted_for_series(self, sonarr_series_id: int) -> list:
        """Get all wanted items for a specific series."""
        stmt = select(WantedItem).where(
            WantedItem.sonarr_series_id == sonarr_series_id
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def get_wanted_for_movie(self, radarr_movie_id: int) -> list:
        """Get all wanted items for a specific movie."""
        stmt = select(WantedItem).where(
            WantedItem.radarr_movie_id == radarr_movie_id
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def delete_wanted_item(self, item_id: int) -> bool:
        """Delete a single wanted item."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        self.session.delete(item)
        self._commit()
        return True

    def delete_wanted_by_file_path(self, file_path: str) -> int:
        """Delete wanted items by file path. Returns count deleted."""
        stmt = delete(WantedItem).where(WantedItem.file_path == file_path)
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    def delete_wanted_items_by_ids(self, item_ids: list) -> int:
        """Delete wanted items by their IDs (batch). Returns count deleted."""
        if not item_ids:
            return 0
        stmt = delete(WantedItem).where(WantedItem.id.in_(item_ids))
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    def cleanup_wanted_items(self, instance_name: str = None) -> list:
        """Get wanted items with file_path, target_language, instance_name, and id for cleanup."""
        stmt = select(
            WantedItem.id, WantedItem.file_path,
            WantedItem.target_language, WantedItem.instance_name
        )
        rows = self.session.execute(stmt).all()
        return [
            {
                "id": r[0],
                "file_path": r[1],
                "target_language": r[2] or "",
                "instance_name": r[3] or "",
            }
            for r in rows
        ]

    def get_all_wanted_file_paths(self) -> set:
        """Get all file paths currently in the wanted table (for cleanup)."""
        stmt = select(WantedItem.file_path)
        rows = self.session.execute(stmt).scalars().all()
        return set(rows)

    def get_wanted_count(self, status: str = None) -> int:
        """Get count of wanted items with optional status filter."""
        stmt = select(func.count()).select_from(WantedItem)
        if status:
            stmt = stmt.where(WantedItem.status == status)
        return self.session.execute(stmt).scalar()

    def get_upgradeable_count(self) -> int:
        """Get count of items marked as upgrade candidates."""
        stmt = select(func.count()).select_from(WantedItem).where(
            WantedItem.upgrade_candidate == 1
        )
        return self.session.execute(stmt).scalar()

    def find_wanted_by_episode(self, sonarr_episode_id: int,
                               target_language: str = "") -> Optional[dict]:
        """Find a wanted item for a specific episode + language."""
        stmt = select(WantedItem).where(
            WantedItem.sonarr_episode_id == sonarr_episode_id
        )
        if target_language:
            stmt = stmt.where(WantedItem.target_language == target_language)
        stmt = stmt.limit(1)
        item = self.session.execute(stmt).scalars().first()
        if not item:
            return None
        return self._row_to_wanted(item)

    def get_wanted_by_subtitle_type(self) -> dict:
        """Get wanted item counts grouped by subtitle_type."""
        stmt = select(
            WantedItem.subtitle_type, func.count()
        ).group_by(WantedItem.subtitle_type)
        rows = self.session.execute(stmt).all()
        result = {}
        for row in rows:
            key = row[0] if row[0] else "full"
            result[key] = row[1]
        return result

    # ---- Helpers ----

    def _row_to_wanted(self, item: WantedItem) -> dict:
        """Convert a WantedItem model to a dict. Parse missing_languages JSON."""
        d = self._to_dict(item)
        if d.get("missing_languages"):
            try:
                d["missing_languages"] = json.loads(d["missing_languages"])
            except json.JSONDecodeError:
                d["missing_languages"] = []
        else:
            d["missing_languages"] = []
        return d
