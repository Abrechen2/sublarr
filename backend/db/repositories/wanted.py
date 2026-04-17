"""Wanted items repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/wanted.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly.

CRITICAL: The upsert logic matches on file_path + target_language + subtitle_type
with conditional handling for empty/null target_language.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import asc, case, delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from db.models.core import SeriesSettings, WantedItem
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Supported presets for get_items_for_scheduled_search
_SCHEDULED_SEARCH_ORDERS = ("fair", "newest_first", "weighted")
# Boundary between "recent" (bucket 0) and "older" (bucket 1) items for the
# 'weighted' preset. Kept local to the repository so the scheduler can stay
# preset-based and not need to pass a window parameter.
_WEIGHTED_RECENT_DAYS = 30


# Priority rank used to prefix scheduler ORDER BY clauses:
#   premium -> 0 (highest), standard -> 1, backlog -> 2 (lowest).
# Applied by get_items_for_scheduled_search when priority_weighting is on.
def _priority_rank_expr():
    """Rank expression: premium=0, backlog=2, standard=1.

    Uses ``COALESCE(series_settings.priority_override, WantedItem.priority)`` so
    a per-series override wins over the item's intrinsic priority. Callers
    MUST apply ``LEFT OUTER JOIN series_settings ON sonarr_series_id`` before
    using this expression — otherwise ``priority_override`` resolves to NULL
    for every row, defeating the point of the override.
    """
    effective = func.coalesce(SeriesSettings.priority_override, WantedItem.priority)
    return case(
        (effective == "premium", 0),
        (effective == "backlog", 2),
        else_=1,
    )


class WantedRepository(BaseRepository):
    """Repository for wanted_items table operations."""

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

    # Sort field allowlist for get_wanted_items
    _SORT_FIELDS = {
        "added_at": WantedItem.added_at,
        "title": WantedItem.title,
        "last_search_at": WantedItem.last_search_at,
        "current_score": WantedItem.current_score,
        "search_count": WantedItem.search_count,
    }

    def get_wanted_items(
        self,
        page: int = 1,
        per_page: int = 50,
        item_type: str = None,
        status: str = None,
        series_id: int = None,
        movie_id: int = None,
        subtitle_type: str = None,
        sort_by: str = "added_at",
        sort_dir: str = "desc",
        search: str = None,
        preset_conditions: dict = None,
    ) -> dict:
        """Get paginated wanted items with optional filters, sorting, and text search."""
        offset = (page - 1) * per_page

        conditions = []
        if item_type:
            conditions.append(WantedItem.item_type == item_type)
        if status:
            conditions.append(WantedItem.status == status)
        if series_id is not None:
            conditions.append(WantedItem.sonarr_series_id == series_id)
        if movie_id is not None:
            conditions.append(WantedItem.standalone_movie_id == movie_id)
        if subtitle_type:
            conditions.append(WantedItem.subtitle_type == subtitle_type)

        # Text search on title and file_path
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    WantedItem.title.ilike(search_term),
                    WantedItem.file_path.ilike(search_term),
                )
            )

        # Preset condition tree (AND/OR filter presets)
        if preset_conditions is not None:
            from db.repositories.presets import FilterPresetsRepository

            wanted_field_map = {
                "status": WantedItem.status,
                "item_type": WantedItem.item_type,
                "subtitle_type": WantedItem.subtitle_type,
                "target_language": WantedItem.target_language,
                "upgrade_candidate": WantedItem.upgrade_candidate,
                "title": WantedItem.title,
            }
            clause = FilterPresetsRepository().build_clause(preset_conditions, wanted_field_map)
            conditions.append(clause)

        # Count query
        count_stmt = select(func.count()).select_from(WantedItem)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count = self.session.execute(count_stmt).scalar()

        # Determine sort column and direction
        sort_col = self._SORT_FIELDS.get(sort_by, WantedItem.added_at)
        order = asc(sort_col) if sort_dir == "asc" else desc(sort_col)

        # Data query
        # Secondary sort by file_path (always asc) keeps language pairs for the same
        # episode adjacent regardless of the primary sort direction.
        data_stmt = (
            select(WantedItem).order_by(order, WantedItem.file_path).limit(per_page).offset(offset)
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

    def get_items_for_scheduled_search(
        self,
        limit: int,
        order: str = "fair",
        priority_weighting: bool | None = None,
    ) -> list[dict]:
        """Return wanted items eligible for scheduler-driven search, ordered by preset.

        Replaces the legacy ``get_wanted_items(page=1, per_page=N, status='wanted')`` call
        used by the scheduler, which returned newest-first and starved older items.

        Args:
            limit: Max rows to return (safety cap for a single scheduler tick).
            order: One of ``'fair'``, ``'newest_first'``, ``'weighted'``.
            priority_weighting: If True, prepend a priority rank (premium=0,
                standard=1, backlog=2) to every preset's ORDER BY. If False, skip
                the prefix and use the Phase 1 behaviour. When ``None`` (default),
                read ``wanted_scheduler_priority_weighting_enabled`` from settings
                (defaults to True).

        Returns:
            List of dict rows (via ``self._row_to_wanted``).

        Raises:
            ValueError: If ``order`` is not one of the three supported presets.
        """
        if order not in _SCHEDULED_SEARCH_ORDERS:
            raise ValueError(
                f"Invalid order preset {order!r}. "
                f"Expected one of: {', '.join(_SCHEDULED_SEARCH_ORDERS)}"
            )

        if priority_weighting is None:
            try:
                from config import get_settings  # noqa: PLC0415

                priority_weighting = bool(
                    getattr(
                        get_settings(),
                        "wanted_scheduler_priority_weighting_enabled",
                        True,
                    )
                )
            except Exception:  # noqa: BLE001
                priority_weighting = True

        stmt = select(WantedItem).where(WantedItem.status == "wanted")
        if priority_weighting:
            stmt = stmt.outerjoin(
                SeriesSettings,
                SeriesSettings.sonarr_series_id == WantedItem.sonarr_series_id,
            )

        order_clauses: list = []
        if priority_weighting:
            order_clauses.append(_priority_rank_expr().asc())

        if order == "newest_first":
            order_clauses.append(desc(WantedItem.added_at))
        elif order == "fair":
            order_clauses.extend(
                [
                    WantedItem.last_search_at.asc().nullsfirst(),
                    WantedItem.search_count.asc(),
                ]
            )
        else:  # weighted
            cutoff = datetime.now(UTC) - timedelta(days=_WEIGHTED_RECENT_DAYS)
            bucket = case(
                (WantedItem.added_at >= cutoff, 0),
                else_=1,
            )
            order_clauses.extend(
                [
                    bucket.asc(),
                    WantedItem.last_search_at.asc().nullsfirst(),
                    WantedItem.search_count.asc(),
                ]
            )

        stmt = stmt.order_by(*order_clauses).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def get_wanted_item(self, item_id: int) -> dict | None:
        """Get a single wanted item by ID."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return None
        return self._row_to_wanted(item)

    def get_wanted_by_file_path(
        self, file_path: str, target_language: str = None, subtitle_type: str = None
    ) -> dict | None:
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

    def get_wanted_items_by_path(self, file_path: str) -> list[dict]:
        """Return all wanted items sharing a file path (one per target language).

        Used by the webhook pipeline so that a single import event processes
        every pending target language, not just the first one returned by the
        single-item lookup above.
        """
        stmt = select(WantedItem).where(WantedItem.file_path == file_path)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def update_wanted_status(self, item_id: int, status: str, error: str = "") -> bool:
        """Update a wanted item's status."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.status = status
        item.error = error
        item.updated_at = self._now()
        self._commit()
        return True

    # Allowed fields for ``update_wanted_search_outcome``. Anything not in this
    # set is silently ignored so typos in callers don't mutate unrelated rows.
    _OUTCOME_ALLOWED_FIELDS = frozenset(
        {
            "status",
            "search_count",
            "error_count",
            "failure_kind",
            "retry_after",
            "last_error_at",
            "last_search_at",
            "error",
        }
    )

    def update_wanted_search_outcome(
        self,
        item_id: int,
        *,
        search_count_increment: int = 0,
        error_count_increment: int = 0,
        reset_failure: bool = False,
        **fields,
    ) -> bool:
        """Partial update for scheduler-driven search outcomes.

        Supported fields (anything else is ignored): ``status, search_count,
        error_count, failure_kind, retry_after, last_error_at, last_search_at,
        error``.

        Column semantics:
        - ``error`` field uses **None-means-don't-touch** — passing
          ``error=None`` leaves the column unchanged. Pass ``error=""`` to
          explicitly clear it. This prevents silent data loss when a caller
          doesn't have a message to record (e.g. a new provider_error event
          without an error string should preserve the prior operator note).
        - All other allowlisted fields accept ``None`` as a valid value
          (e.g. ``retry_after=None`` to clear it).

        Atomic SQL-side increments:
        - ``search_count_increment: int = 0`` — when > 0, emits
          ``search_count = search_count + N`` as a SQL column expression so
          concurrent scheduler threads cannot lose increments via
          read-modify-write races.
        - ``error_count_increment: int = 0`` — same semantics for
          ``error_count``.

        ``reset_failure=True`` clears the failure-tracking state
        (``error_count=0, failure_kind=None, error=None, retry_after=None``).
        This is how the ``'found'`` outcome wipes prior error history.

        Returns ``True`` if the row existed and was updated, ``False`` if the
        ID was unknown (no exception — the caller is typically a background
        worker that shouldn't die just because a concurrent delete won).
        """
        # Build the patch dict respecting the allowlist. ``error`` is
        # handled separately because None means "leave column alone".
        patch: dict = {
            k: v for k, v in fields.items() if k in self._OUTCOME_ALLOWED_FIELDS and k != "error"
        }
        if "error" in fields and fields["error"] is not None:
            patch["error"] = fields["error"]

        if reset_failure:
            patch["error_count"] = 0
            patch["failure_kind"] = None
            patch["error"] = None
            patch["retry_after"] = None

        # SQL-side atomic increments to avoid read-modify-write races under
        # concurrent writers. Using column expressions (WantedItem.col + N)
        # means the DB server is the sole writer for these fields.
        if search_count_increment:
            patch["search_count"] = WantedItem.search_count + search_count_increment
        if error_count_increment:
            patch["error_count"] = WantedItem.error_count + error_count_increment

        patch["updated_at"] = self._now()

        stmt = update(WantedItem).where(WantedItem.id == item_id).values(**patch)
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount > 0

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

    def set_retry_after(self, item_id: int, retry_after) -> bool:
        """Set retry_after datetime for adaptive backoff."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.retry_after = retry_after
        item.updated_at = self._now()
        self._commit()
        return True

    def update_existing_sub(self, item_id: int, value: str) -> bool:
        """Update the existing_sub field for a wanted item."""
        item = self.session.get(WantedItem, item_id)
        if not item:
            return False
        item.existing_sub = value
        item.updated_at = self._now()
        self._commit()
        return True

    def get_wanted_summary(self) -> dict:
        """Get aggregated wanted counts by type, status, and existing_sub."""
        total_stmt = select(func.count()).select_from(WantedItem)
        total = self.session.execute(total_stmt).scalar()

        # By type
        by_type_stmt = select(WantedItem.item_type, func.count()).group_by(WantedItem.item_type)
        by_type = {row[0]: row[1] for row in self.session.execute(by_type_stmt).all()}

        # By status
        by_status_stmt = select(WantedItem.status, func.count()).group_by(WantedItem.status)
        by_status = {row[0]: row[1] for row in self.session.execute(by_status_stmt).all()}

        # By existing_sub
        by_existing_stmt = select(WantedItem.existing_sub, func.count()).group_by(
            WantedItem.existing_sub
        )
        by_existing = {}
        for row in self.session.execute(by_existing_stmt).all():
            key = row[0] if row[0] else "none"
            by_existing[key] = row[1]

        # Upgradeable
        upgradeable_stmt = (
            select(func.count()).select_from(WantedItem).where(WantedItem.upgrade_candidate == 1)
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
        stmt = select(WantedItem).where(WantedItem.sonarr_series_id == sonarr_series_id)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def get_wanted_by_series(self, sonarr_series_id: int) -> list[dict]:
        """Return all wanted-status items for a Sonarr series id."""
        rows = (
            self.session.execute(
                select(WantedItem).where(
                    WantedItem.status == "wanted",
                    WantedItem.sonarr_series_id == sonarr_series_id,
                )
            )
            .scalars()
            .all()
        )
        return [self._row_to_wanted(r) for r in rows]

    def get_wanted_for_movie(self, radarr_movie_id: int) -> list:
        """Get all wanted items for a specific movie."""
        stmt = select(WantedItem).where(WantedItem.radarr_movie_id == radarr_movie_id)
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

    def get_wanted_items_by_ids(self, item_ids: list[int]) -> dict[int, dict]:
        """Fetch multiple wanted items in one query. Returns a dict mapping id -> item dict."""
        if not item_ids:
            return {}
        stmt = select(WantedItem).where(WantedItem.id.in_(item_ids))
        rows = self.session.execute(stmt).scalars().all()
        return {r.id: self._row_to_wanted(r) for r in rows}

    def update_wanted_status_bulk(self, item_ids: list[int], status: str, error: str = "") -> int:
        """Update status for multiple wanted items in one UPDATE. Returns count updated."""
        if not item_ids:
            return 0
        stmt = (
            update(WantedItem)
            .where(WantedItem.id.in_(item_ids))
            .values(status=status, error=error, updated_at=self._now())
        )
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
            WantedItem.id,
            WantedItem.file_path,
            WantedItem.target_language,
            WantedItem.instance_name,
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
        stmt = select(func.count()).select_from(WantedItem).where(WantedItem.upgrade_candidate == 1)
        return self.session.execute(stmt).scalar()

    def find_wanted_by_episode(
        self, sonarr_episode_id: int, target_language: str = ""
    ) -> dict | None:
        """Find a wanted item for a specific episode + language."""
        stmt = select(WantedItem).where(WantedItem.sonarr_episode_id == sonarr_episode_id)
        if target_language:
            stmt = stmt.where(WantedItem.target_language == target_language)
        stmt = stmt.limit(1)
        item = self.session.execute(stmt).scalars().first()
        if not item:
            return None
        return self._row_to_wanted(item)

    def get_series_missing_counts(self) -> dict:
        """Get count of truly missing wanted items per Sonarr series ID.

        Only counts items with no existing subtitle (existing_sub is null or empty).
        Upgrade candidates (existing_sub = 'srt') are not counted as missing
        since the episode already has a subtitle, just not the ideal format.

        Returns:
            Dict mapping sonarr_series_id -> count of truly missing items.
        """
        stmt = (
            select(WantedItem.sonarr_series_id, func.count())
            .where(
                WantedItem.sonarr_series_id.isnot(None),
                WantedItem.status == "wanted",
                or_(
                    WantedItem.existing_sub == "",
                    WantedItem.existing_sub.is_(None),
                ),
            )
            .group_by(WantedItem.sonarr_series_id)
        )
        rows = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in rows}

    def get_wanted_by_subtitle_type(self) -> dict:
        """Get wanted item counts grouped by subtitle_type."""
        stmt = select(WantedItem.subtitle_type, func.count()).group_by(WantedItem.subtitle_type)
        rows = self.session.execute(stmt).all()
        result = {}
        for row in rows:
            key = row[0] if row[0] else "full"
            result[key] = row[1]
        return result

    # ---- Helpers ----

    def _row_to_wanted(self, item: WantedItem) -> dict:
        """Convert a WantedItem model to a dict. Parse missing_languages and embedded_languages JSON."""
        d = self._to_dict(item)
        if d.get("missing_languages"):
            try:
                d["missing_languages"] = json.loads(d["missing_languages"])
            except json.JSONDecodeError:
                d["missing_languages"] = []
        else:
            d["missing_languages"] = []
        if d.get("embedded_languages"):
            try:
                d["embedded_languages"] = json.loads(d["embedded_languages"])
            except json.JSONDecodeError:
                d["embedded_languages"] = []
        else:
            d["embedded_languages"] = []
        return d
