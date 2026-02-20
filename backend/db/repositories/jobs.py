"""Jobs and daily stats repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/jobs.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly.
"""

import json
import uuid
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, delete

from db.models.core import Job, DailyStats
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class JobRepository(BaseRepository):
    """Repository for jobs and daily_stats table operations."""

    # ---- Job CRUD ----

    def create_job(self, file_path: str, force: bool = False,
                   arr_context: dict = None) -> dict:
        """Create a new translation job in the database."""
        job_id = str(uuid.uuid4())[:8]
        now = self._now()
        context_json = json.dumps(arr_context) if arr_context else ""

        job = Job(
            id=job_id,
            file_path=file_path,
            status="queued",
            force=int(force),
            bazarr_context_json=context_json,
            created_at=now,
            completed_at="",
        )
        self.session.add(job)
        self._commit()

        return {
            "id": job_id,
            "file_path": file_path,
            "status": "queued",
            "force": force,
            "arr_context": arr_context,
            "created_at": now,
            "completed_at": None,
            "result": None,
            "error": None,
        }

    def update_job(self, job_id: str, status: str, result: dict = None,
                   error: str = None):
        """Update a job's status and result."""
        now = self._now() if status in ("completed", "failed") else ""
        stats_json = json.dumps(result.get("stats", {})) if result else "{}"
        output_path = result.get("output_path", "") if result else ""
        source_format = ""
        config_hash = ""
        if result and result.get("stats"):
            source_format = result["stats"].get("format", "")
            config_hash = result["stats"].get("config_hash", "")

        job = self.session.get(Job, job_id)
        if job:
            job.status = status
            job.stats_json = stats_json
            job.output_path = output_path
            job.source_format = source_format
            job.error = error or ""
            job.completed_at = now
            job.config_hash = config_hash
            self._commit()

    def get_job(self, job_id: str) -> Optional[dict]:
        """Get a job by ID."""
        job = self.session.get(Job, job_id)
        if not job:
            return None
        return self._row_to_job(job)

    def get_jobs(self, page: int = 1, per_page: int = 50,
                 status: str = None) -> dict:
        """Get paginated job list."""
        offset = (page - 1) * per_page

        # Count query
        count_stmt = select(func.count()).select_from(Job)
        if status:
            count_stmt = count_stmt.where(Job.status == status)
        count = self.session.execute(count_stmt).scalar()

        # Data query
        data_stmt = select(Job).order_by(Job.created_at.desc()).limit(per_page).offset(offset)
        if status:
            data_stmt = data_stmt.where(Job.status == status)
        rows = self.session.execute(data_stmt).scalars().all()

        total_pages = max(1, (count + per_page - 1) // per_page)
        return {
            "data": [self._row_to_job(r) for r in rows],
            "page": page,
            "per_page": per_page,
            "total": count,
            "total_pages": total_pages,
        }

    def get_recent_jobs(self, limit: int = 10) -> list:
        """Get recent jobs ordered by created_at DESC."""
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_job(r) for r in rows]

    def get_pending_job_count(self) -> int:
        """Get count of queued/running jobs."""
        stmt = select(func.count()).select_from(Job).where(
            Job.status.in_(["queued", "running"])
        )
        return self.session.execute(stmt).scalar()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job by ID."""
        job = self.session.get(Job, job_id)
        if not job:
            return False
        self.session.delete(job)
        self._commit()
        return True

    def delete_old_jobs(self, days: int) -> int:
        """Delete jobs older than N days. Returns count deleted."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        stmt = delete(Job).where(Job.created_at < cutoff)
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    def get_outdated_jobs_count(self, current_hash: str) -> int:
        """Get count of completed jobs with a different config hash."""
        stmt = select(func.count()).select_from(Job).where(
            Job.status == "completed",
            Job.config_hash != "",
            Job.config_hash != current_hash,
        )
        return self.session.execute(stmt).scalar()

    def get_outdated_jobs(self, current_hash: str, limit: int = 100) -> list:
        """Get completed jobs with a different config hash."""
        stmt = (
            select(Job)
            .where(
                Job.status == "completed",
                Job.config_hash != "",
                Job.config_hash != current_hash,
            )
            .order_by(Job.completed_at.desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._row_to_job(r) for r in rows]

    # ---- Daily Stats ----

    def record_daily_stats(self, success: bool, skipped: bool = False,
                           fmt: str = "", source: str = ""):
        """Record a translation result in daily stats (upsert with JSON merge)."""
        today = date.today().isoformat()

        existing = self.session.get(DailyStats, today)

        if existing:
            by_format = json.loads(existing.by_format_json or "{}")
            by_source = json.loads(existing.by_source_json or "{}")

            if success and not skipped:
                existing.translated = (existing.translated or 0) + 1
                if fmt:
                    by_format[fmt] = by_format.get(fmt, 0) + 1
                if source:
                    by_source[source] = by_source.get(source, 0) + 1
            elif success and skipped:
                existing.skipped = (existing.skipped or 0) + 1
            else:
                existing.failed = (existing.failed or 0) + 1

            existing.by_format_json = json.dumps(by_format)
            existing.by_source_json = json.dumps(by_source)
        else:
            by_format = {}
            by_source = {}
            translated = 0
            failed = 0
            skip_count = 0

            if success and not skipped:
                translated = 1
                if fmt:
                    by_format[fmt] = 1
                if source:
                    by_source[source] = 1
            elif success and skipped:
                skip_count = 1
            else:
                failed = 1

            stats = DailyStats(
                date=today,
                translated=translated,
                failed=failed,
                skipped=skip_count,
                by_format_json=json.dumps(by_format),
                by_source_json=json.dumps(by_source),
            )
            self.session.add(stats)

        self._commit()

    def get_daily_stats(self, days: int = 30) -> list:
        """Get last N days of daily stats."""
        stmt = (
            select(DailyStats)
            .order_by(DailyStats.date.desc())
            .limit(days)
        )
        rows = self.session.execute(stmt).scalars().all()
        return [self._to_dict(r) for r in rows]

    def get_stats_summary(self) -> dict:
        """Get aggregated stats summary (last 30 days)."""
        stmt = (
            select(DailyStats)
            .order_by(DailyStats.date.desc())
            .limit(30)
        )
        rows = self.session.execute(stmt).scalars().all()

        total_translated = 0
        total_failed = 0
        total_skipped = 0
        by_format_total = {}
        by_source_total = {}
        daily = []

        for row in rows:
            total_translated += row.translated or 0
            total_failed += row.failed or 0
            total_skipped += row.skipped or 0

            by_format = json.loads(row.by_format_json or "{}")
            for k, v in by_format.items():
                by_format_total[k] = by_format_total.get(k, 0) + v

            by_source = json.loads(row.by_source_json or "{}")
            for k, v in by_source.items():
                by_source_total[k] = by_source_total.get(k, 0) + v

            daily.append({
                "date": row.date,
                "translated": row.translated or 0,
                "failed": row.failed or 0,
                "skipped": row.skipped or 0,
            })

        # Today's stats
        today_row = self.session.get(DailyStats, date.today().isoformat())
        today_translated = today_row.translated if today_row else 0

        return {
            "total_translated": total_translated,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "today_translated": today_translated,
            "by_format": by_format_total,
            "by_source": by_source_total,
            "daily": daily,
        }

    # ---- Helpers ----

    def _row_to_job(self, job: Job) -> dict:
        """Convert a Job model to a dict matching existing format."""
        d = self._to_dict(job)

        # Parse JSON fields
        if d.get("stats_json"):
            try:
                d["stats"] = json.loads(d["stats_json"])
            except json.JSONDecodeError:
                d["stats"] = {}
        else:
            d["stats"] = {}
        del d["stats_json"]

        if d.get("bazarr_context_json"):
            try:
                d["arr_context"] = json.loads(d["bazarr_context_json"])
            except json.JSONDecodeError:
                d["arr_context"] = None
        else:
            d["arr_context"] = None
        del d["bazarr_context_json"]

        d["force"] = bool(d.get("force", 0))
        return d
