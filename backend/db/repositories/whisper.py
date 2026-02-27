"""Whisper job repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/whisper.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import func, select

from db.models.translation import WhisperJob
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class WhisperRepository(BaseRepository):
    """Repository for whisper_jobs table operations."""

    def create_whisper_job(self, job_id: str, file_path: str, language: str = "") -> dict:
        """Create a new whisper job in the database.

        Returns:
            Dict representing the created job.
        """
        now = self._now()
        job = WhisperJob(
            id=job_id,
            file_path=file_path,
            language=language,
            status="queued",
            progress=0.0,
            created_at=now,
        )
        self.session.add(job)
        self._commit()

        return {
            "id": job_id,
            "file_path": file_path,
            "language": language,
            "status": "queued",
            "progress": 0.0,
            "created_at": now,
        }

    def update_whisper_job(self, job_id: str, **kwargs) -> None:
        """Update a whisper job with arbitrary column values.

        Args:
            job_id: Job to update.
            **kwargs: Column name-value pairs to update.
        """
        if not kwargs:
            return

        job = self.session.get(WhisperJob, job_id)
        if job is None:
            return

        for key, value in kwargs.items():
            setattr(job, key, value)
        self._commit()

    def get_whisper_job(self, job_id: str) -> dict | None:
        """Get a whisper job by ID.

        Returns:
            Job dict or None if not found.
        """
        job = self.session.get(WhisperJob, job_id)
        return self._to_dict(job)

    def get_whisper_jobs(self, status: str = None, limit: int = 50) -> list[dict]:
        """Get whisper jobs, optionally filtered by status.

        Returns:
            List of job dicts, ordered by created_at descending.
        """
        stmt = select(WhisperJob).order_by(WhisperJob.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(WhisperJob.status == status)
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def delete_whisper_job(self, job_id: str) -> bool:
        """Delete a whisper job.

        Returns:
            True if a row was deleted.
        """
        job = self.session.get(WhisperJob, job_id)
        if job is None:
            return False
        self.session.delete(job)
        self._commit()
        return True

    def get_whisper_stats(self) -> dict:
        """Get aggregate whisper job statistics.

        Returns:
            Dict with total count, counts by status, and average processing time.
        """
        total = self.session.execute(
            select(func.count()).select_from(WhisperJob)
        ).scalar() or 0

        # Counts by status
        status_rows = self.session.execute(
            select(WhisperJob.status, func.count())
            .group_by(WhisperJob.status)
        ).all()
        by_status = {row[0]: row[1] for row in status_rows}

        # Average processing time (completed jobs only)
        avg_processing_time = self.session.execute(
            select(func.avg(WhisperJob.processing_time_ms))
            .where(
                WhisperJob.status == "completed",
                WhisperJob.processing_time_ms > 0,
            )
        ).scalar()

        return {
            "total": total,
            "by_status": by_status,
            "avg_processing_time_ms": round(avg_processing_time, 1) if avg_processing_time is not None else 0.0,
        }
