"""Quality repository: CRUD for subtitle health check results.

Provides save, fetch, series-level queries, trend aggregation,
and cleanup operations for SubtitleHealthResult records.
"""

import json
import logging

from sqlalchemy import select, func, text

from db.models.quality import SubtitleHealthResult
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class QualityRepository(BaseRepository):
    """Repository for subtitle_health_results table operations."""

    def save_health_result(self, file_path: str, score: int,
                           issues_json: str, checks_run: int,
                           checked_at: str) -> dict:
        """Save or update a health check result for a file.

        Creates a new record each time (for trend tracking).

        Returns:
            Dict representation of the saved record.
        """
        entry = SubtitleHealthResult(
            file_path=file_path,
            score=score,
            issues_json=issues_json,
            checks_run=checks_run,
            checked_at=checked_at,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_health_result(self, file_path: str) -> dict | None:
        """Get the most recent health result for a file path.

        Returns:
            Dict or None if no results exist.
        """
        stmt = (
            select(SubtitleHealthResult)
            .where(SubtitleHealthResult.file_path == file_path)
            .order_by(SubtitleHealthResult.checked_at.desc())
            .limit(1)
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(result)

    def get_health_results_for_series(self, path_prefix: str) -> list[dict]:
        """Get all health results for files under a series path prefix.

        Returns:
            List of dicts for all matching results (most recent per file).
        """
        # Get the most recent result per file under this prefix
        subquery = (
            select(
                SubtitleHealthResult.file_path,
                func.max(SubtitleHealthResult.id).label("max_id"),
            )
            .where(SubtitleHealthResult.file_path.like(f"{path_prefix}%"))
            .group_by(SubtitleHealthResult.file_path)
            .subquery()
        )

        stmt = (
            select(SubtitleHealthResult)
            .join(subquery, SubtitleHealthResult.id == subquery.c.max_id)
            .order_by(SubtitleHealthResult.file_path)
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_quality_trends(self, days: int = 30) -> list[dict]:
        """Get daily average score and issue count for trend tracking.

        Returns:
            List of dicts with date, avg_score, total_issues, check_count.
        """
        # Use SQLite date() function to group by day
        stmt = (
            select(
                func.substr(SubtitleHealthResult.checked_at, 1, 10).label("date"),
                func.round(func.avg(SubtitleHealthResult.score), 1).label("avg_score"),
                func.count().label("check_count"),
            )
            .where(
                SubtitleHealthResult.checked_at > text(f"datetime('now', '-{days} days')")
            )
            .group_by(func.substr(SubtitleHealthResult.checked_at, 1, 10))
            .order_by(func.substr(SubtitleHealthResult.checked_at, 1, 10))
        )
        rows = self.session.execute(stmt).all()

        trends = []
        for row in rows:
            trends.append({
                "date": row[0],
                "avg_score": float(row[1]) if row[1] is not None else 0.0,
                "check_count": row[2],
            })
        return trends

    def delete_health_results(self, file_path: str) -> int:
        """Delete all health results for a file path.

        Returns:
            Count of deleted records.
        """
        stmt = (
            select(SubtitleHealthResult)
            .where(SubtitleHealthResult.file_path == file_path)
        )
        entries = self.session.execute(stmt).scalars().all()
        count = len(entries)
        for entry in entries:
            self.session.delete(entry)
        if count > 0:
            self._commit()
        return count
