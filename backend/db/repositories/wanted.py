"""Wanted items repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/wanted.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly.

CRITICAL: The upsert logic matches on file_path + target_language + subtitle_type
with conditional handling for empty/null target_language. ``upsert_wanted_item``
itself lives in the sibling ``wanted_upsert.py`` (_WantedUpsertMixin) to keep
this file readable.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import asc, case, delete, desc, func, or_, select, update

from db.models.core import SeriesSettings, WantedItem
from db.repositories.base import BaseRepository
from db.repositories.wanted_updates import _WantedUpdatesMixin  # noqa: F401 — re-exported
from db.repositories.wanted_upsert import _WantedUpsertMixin  # noqa: F401 — re-exported

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


class WantedRepository(BaseRepository, _WantedUpsertMixin, _WantedUpdatesMixin):
    """Repository for wanted_items table operations."""

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
        # Clamp before arithmetic. An unclamped page reached Postgres as
        # OFFSET -50 and answered HTTP 500 on prod (2026-09-03,
        # GET /api/v1/wanted?page=0); an unclamped per_page divides by zero in
        # the total_pages line below. SQLite accepts a negative OFFSET
        # silently, so the suite cannot see the first one — the clamped page
        # this returns is what both engines can be held to.
        # Same shape as db/repositories/blacklist.py.
        page = max(1, page)
        per_page = max(1, per_page)
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

    def get_provisional_items(
        self, limit: int, search_cutoff: datetime | None = None
    ) -> list[dict]:
        """Return ``status="provisional"`` items eligible for MT re-seek.

        Provisional items are Sublarr machine-translations kept alive (profile
        ``mt_keep_seeking_original=1``) while Sublarr seeks a human/provider
        original (feature #8b). Ordered fair — oldest ``last_search_at`` first,
        then fewest ``search_count`` — so the re-seek job spreads its budget
        across the backlog instead of starving older items.

        ``search_cutoff`` applies the per-item backoff: rows searched more
        recently than the cutoff are excluded so the job stays cheap. Rows that
        were never searched (``last_search_at IS NULL``) always qualify.
        """
        stmt = select(WantedItem).where(WantedItem.status == "provisional")
        if search_cutoff is not None:
            stmt = stmt.where(
                or_(
                    WantedItem.last_search_at.is_(None),
                    WantedItem.last_search_at < search_cutoff,
                )
            )
        stmt = stmt.order_by(
            WantedItem.last_search_at.asc().nullsfirst(),
            WantedItem.search_count.asc(),
        ).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_wanted(r) for r in rows]

    def get_mt_pending_items(self) -> list[dict]:
        """Return wanted items with a pending-original notification (feature #8b Task 3).

        Selects rows where ``mt_pending_original IS NOT NULL`` — set by
        ``services.mt_reseek._record_pending_notification`` when
        ``mt_on_original_found=="notify"`` finds a qualifying original during a
        re-seek pass. The raw JSON payload is parsed into a dict (mirroring how
        ``_row_to_wanted`` already parses ``missing_languages``/
        ``embedded_languages``) so API consumers get structured
        ``provider/score/output_path/format/found_at`` fields instead of a raw
        JSON string.
        """
        stmt = (
            select(WantedItem)
            .where(WantedItem.mt_pending_original.isnot(None))
            .order_by(WantedItem.updated_at.desc())
        )
        rows = self.session.execute(stmt).scalars().all()
        items = []
        for row in rows:
            d = self._row_to_wanted(row)
            try:
                d["mt_pending_original"] = json.loads(d["mt_pending_original"])
            except (TypeError, json.JSONDecodeError):
                d["mt_pending_original"] = None
            items.append(d)
        return items

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

    # update_wanted_status, update_wanted_search_outcome, mark_search_attempted,
    # set_retry_after, update_existing_sub live on _WantedUpdatesMixin (see
    # wanted_updates.py).

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

        # Exhausted: wanted items the search will never pick up again (#199).
        # Without this number the queue reads as a healthy backlog — on the
        # install that reported it, 67% of "wanted" had quietly given up and
        # every item sat under the same badge.
        from config import get_settings
        from services.wanted_search_filters import is_exhausted

        settings = get_settings()
        max_attempts = getattr(settings, "wanted_max_search_attempts", 3)
        adaptive = getattr(settings, "wanted_adaptive_backoff_enabled", True)
        capped = (
            self.session.execute(
                select(
                    WantedItem.search_count, WantedItem.failure_kind, WantedItem.retry_after
                ).where(
                    WantedItem.status == "wanted",
                    WantedItem.search_count >= max_attempts,
                )
            )
            .tuples()
            .all()
        )
        exhausted = sum(
            1
            for search_count, failure_kind, retry_after in capped
            if is_exhausted(
                search_count=search_count,
                failure_kind=failure_kind,
                # With adaptive backoff off the bypass cannot fire, exactly as
                # in the search filter — the report has to describe the
                # behaviour, not a nicer version of it.
                retry_after=retry_after if adaptive else None,
                max_attempts=max_attempts,
            )
        )

        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
            "by_existing": by_existing,
            "upgradeable": upgradeable,
            "exhausted": exhausted,
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

    def get_wanted_by_series_bulk(self, sonarr_series_ids: list[int]) -> dict[int, list[dict]]:
        """Bulk variant of get_wanted_by_series.

        One ``WHERE sonarr_series_id IN (...)`` query instead of N. Returned
        dict has every requested id as key (empty list for series with no
        wanted items) so callers do not need a `.get(sid, [])` fallback.
        """
        out: dict[int, list[dict]] = {sid: [] for sid in sonarr_series_ids}
        if not sonarr_series_ids:
            return out
        rows = (
            self.session.execute(
                select(WantedItem).where(
                    WantedItem.status == "wanted",
                    WantedItem.sonarr_series_id.in_(sonarr_series_ids),
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            out[r.sonarr_series_id].append(self._row_to_wanted(r))
        return out

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

    def find_exhausted_ids(
        self,
        *,
        max_attempts: int,
        adaptive: bool = True,
        idle_since=None,
        limit: int | None = None,
    ) -> list[int]:
        """Ids of wanted items the search will never pick up again (#199).

        Selection only — the reset itself goes through
        ``reset_search_attempts``, which already knows the full set of fields
        that gate eligibility. Duplicating that here is how the two would
        drift apart.

        ``idle_since`` restricts to items whose last search is older than the
        given moment, which is what makes a time-based revival bounded rather
        than a permanent retry loop. ``limit`` caps one run so a large parked
        backlog comes back in predictable slices.
        """
        from services.wanted_search_filters import is_exhausted

        stmt = select(
            WantedItem.id,
            WantedItem.search_count,
            WantedItem.failure_kind,
            WantedItem.retry_after,
        ).where(
            WantedItem.status == "wanted",
            WantedItem.search_count >= max_attempts,
        )
        if idle_since is not None:
            # An item that has never been searched has no idle age to compare;
            # it also cannot be at the cap, so excluding it costs nothing.
            stmt = stmt.where(
                WantedItem.last_search_at.is_not(None),
                WantedItem.last_search_at < idle_since,
            )

        ids: list[int] = []
        for item_id, search_count, failure_kind, retry_after in (
            self.session.execute(stmt).tuples().all()
        ):
            if is_exhausted(
                search_count=search_count,
                failure_kind=failure_kind,
                retry_after=retry_after if adaptive else None,
                max_attempts=max_attempts,
            ):
                ids.append(item_id)
                if limit is not None and len(ids) >= limit:
                    break
        return ids

    def reset_search_attempts(self, item_ids: list[int]) -> int:
        """Clear the search backoff on the given items. Returns count updated.

        Slow mode is the right answer while the problem is the subtitle's
        availability, and the wrong one once the problem was the install: items
        that burned their attempts during an outage keep waiting out a 30-day
        window that outlived its cause. This is the operator saying
        "circumstances changed, try again".

        The cleared set is exactly what `_filter_eligible` reads —
        `search_count` against the cap, `retry_after`, and the
        `no_result_slow` marker — plus the error state. `error_count` does not
        gate eligibility on its own, but it sets the LENGTH of the next backoff
        via `compute_retry_after_for_error`, so leaving it would drop the item
        back into a long wait on its first hiccup after the recovery. The stale
        `error` text goes too: describing a fault that has been fixed is worse
        than saying nothing.

        Only items still `wanted` are touched. A bulk action driven by a filter
        can easily include found rows, and re-opening settled work is not what
        the operator asked for.
        """
        if not item_ids:
            return 0
        stmt = (
            update(WantedItem)
            .where(WantedItem.id.in_(item_ids), WantedItem.status == "wanted")
            .values(
                search_count=0,
                retry_after=None,
                failure_kind=None,
                error_count=0,
                last_error_at=None,
                error="",
                updated_at=self._now(),
            )
        )
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    def reclaim_stranded_searching(self) -> int:
        """Return rows stuck in ``status='searching'`` to the wanted pool.

        Called at scheduler bootstrap only: at that moment no search can be
        running, so every ``searching`` row is an orphan — left behind by a
        process kill mid-search, or by the 1.12.1-rc.8/rc.9 deferred-fallback
        exit that never restored the status (prod 2026-08-19: 7,878 rows,
        ~1,600 stranded per tick). The counterpart to the automation queue's
        ``reclaim_orphaned``.

        Backoff state (``search_count``, ``failure_kind``, ``retry_after``) is
        preserved — this restores visibility, it does not grant a free retry.
        Rare edge: a ``provisional`` row killed mid-reseek comes back as
        ``wanted`` (the pre-flip status is unknowable here); the existing-
        sidecar gate then settles it on the next pass.
        """
        stmt = (
            update(WantedItem)
            .where(WantedItem.status == "searching")
            .values(status="wanted", updated_at=self._now())
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
        # The decision-log blob can be large — replace it with a flag and
        # serve the payload via GET /wanted/<id>/decision on demand.
        d["has_decision_log"] = bool(d.pop("last_decision_log_json", None))
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
