"""Quality repository: CRUD for subtitle health check results.

Provides save, fetch, series-level queries, trend aggregation,
and cleanup operations for SubtitleHealthResult records.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, func, select

from db.models.quality import AIQualityResult, SubtitleHealthResult, UserModifiedSubtitle
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class QualityRepository(BaseRepository):
    """Repository for subtitle_health_results table operations."""

    def save_health_result(
        self, file_path: str, score: int, issues_json: str, checks_run: int, checked_at: datetime
    ) -> dict:
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
        # Both the bucket AND the cutoff work on a text cast of checked_at,
        # because the column's physical type differs per install:
        #   * DBs created from the current models  -> TIMESTAMP WITH TIME ZONE
        #   * DBs predating the timestamp cleanup  -> TEXT (prod/RC are these)
        # Postgres rejects each type in the opposite expression — substr() has
        # no timestamptz overload, and `text > timestamptz` has no operator —
        # so touching the raw column 500s on one install or the other. Casting
        # to text normalises both to a leading "YYYY-MM-DD", where a string
        # comparison is also a chronological one. SQLite is happy either way,
        # which is why CI never caught this.
        day_expr = func.substr(cast(SubtitleHealthResult.checked_at, String), 1, 10)
        cutoff_day = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        stmt = (
            select(
                day_expr.label("date"),
                func.round(func.avg(SubtitleHealthResult.score), 1).label("avg_score"),
                func.count().label("check_count"),
            )
            .where(day_expr >= cutoff_day)
            .group_by(day_expr)
            .order_by(day_expr)
        )
        rows = self.session.execute(stmt).all()

        trends = []
        for row in rows:
            trends.append(
                {
                    "date": row[0],
                    "avg_score": float(row[1]) if row[1] is not None else 0.0,
                    "check_count": row[2],
                }
            )
        return trends

    # ---- AI quality verdicts (advisory) --------------------------------------

    def save_ai_quality_result(
        self,
        file_path: str,
        language: str,
        verdict: str,
        scores_json: str,
        reasons_json: str,
        model: str,
        sampled_cues: int,
    ) -> dict:
        """Save the AI quality verdict for a sidecar, replacing any previous row."""
        stmt = select(AIQualityResult).where(AIQualityResult.file_path == file_path)
        for old in self.session.execute(stmt).scalars().all():
            self.session.delete(old)
        entry = AIQualityResult(
            file_path=file_path,
            language=language,
            verdict=verdict,
            scores_json=scores_json,
            reasons_json=reasons_json,
            model=model,
            sampled_cues=sampled_cues,
            created_at=datetime.now(UTC),
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_ai_quality_result(self, file_path: str) -> dict | None:
        """Get the AI quality verdict for a sidecar path, or None."""
        stmt = (
            select(AIQualityResult)
            .where(AIQualityResult.file_path == file_path)
            .order_by(AIQualityResult.id.desc())
            .limit(1)
        )
        return self._to_dict(self.session.execute(stmt).scalar_one_or_none())

    def get_ai_quality_results_for_paths(self, paths: list[str]) -> dict[str, dict]:
        """Batch-fetch AI verdicts for a list of sidecar paths.

        Returns:
            Dict keyed by file_path (paths without a verdict are absent).
        """
        if not paths:
            return {}
        stmt = (
            select(AIQualityResult)
            .where(AIQualityResult.file_path.in_(paths))
            .order_by(AIQualityResult.id)
        )
        results: dict[str, dict] = {}
        for entry in self.session.execute(stmt).scalars().all():
            results[entry.file_path] = self._to_dict(entry)
        return results

    def delete_ai_quality_result(self, file_path: str) -> int:
        """Delete AI verdicts for a sidecar path. Returns deleted count."""
        stmt = select(AIQualityResult).where(AIQualityResult.file_path == file_path)
        entries = self.session.execute(stmt).scalars().all()
        for entry in entries:
            self.session.delete(entry)
        if entries:
            self._commit()
        return len(entries)

    def delete_health_results(self, file_path: str) -> int:
        """Delete all health results for a file path.

        Returns:
            Count of deleted records.
        """
        stmt = select(SubtitleHealthResult).where(SubtitleHealthResult.file_path == file_path)
        entries = self.session.execute(stmt).scalars().all()
        count = len(entries)
        for entry in entries:
            self.session.delete(entry)
        if count > 0:
            self._commit()
        return count

    # ── User-modified markers (editor trust guard) ──────────────────────────

    def mark_user_modified(self, file_path: str, source: str = "editor") -> dict:
        """Mark a subtitle file as hand-edited (upsert on file_path)."""
        stmt = select(UserModifiedSubtitle).where(UserModifiedSubtitle.file_path == file_path)
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry is None:
            entry = UserModifiedSubtitle(
                file_path=file_path, marked_at=datetime.now(UTC), source=source
            )
            self.session.add(entry)
        else:
            entry.marked_at = datetime.now(UTC)
            entry.source = source
        self._commit()
        return self._to_dict(entry)

    def is_user_modified(self, file_path: str) -> bool:
        """Whether a subtitle file carries the hand-edited marker."""
        stmt = select(UserModifiedSubtitle.id).where(UserModifiedSubtitle.file_path == file_path)
        return self.session.execute(stmt).scalar_one_or_none() is not None

    def clear_user_modified(self, file_path: str) -> int:
        """Remove the hand-edited marker (e.g. after a deliberate replace).

        Returns:
            Count of deleted markers (0 or 1).
        """
        stmt = select(UserModifiedSubtitle).where(UserModifiedSubtitle.file_path == file_path)
        entries = self.session.execute(stmt).scalars().all()
        for entry in entries:
            self.session.delete(entry)
        if entries:
            self._commit()
        return len(entries)
