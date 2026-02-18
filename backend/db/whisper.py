"""Whisper job database operations -- delegating to SQLAlchemy repository."""

from typing import Optional

from db.repositories.whisper import WhisperRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = WhisperRepository()
    return _repo


def create_whisper_job(job_id: str, file_path: str, language: str = "") -> dict:
    """Create a new whisper job in the database."""
    return _get_repo().create_whisper_job(job_id, file_path, language)


def update_whisper_job(job_id: str, **kwargs) -> None:
    """Update a whisper job with arbitrary column values."""
    return _get_repo().update_whisper_job(job_id, **kwargs)


def get_whisper_job(job_id: str) -> Optional[dict]:
    """Get a whisper job by ID."""
    return _get_repo().get_whisper_job(job_id)


def get_whisper_jobs(status: str = None, limit: int = 50) -> list:
    """Get whisper jobs, optionally filtered by status."""
    return _get_repo().get_whisper_jobs(status, limit)


def delete_whisper_job(job_id: str) -> bool:
    """Delete a whisper job."""
    return _get_repo().delete_whisper_job(job_id)


def get_whisper_stats() -> dict:
    """Get aggregate whisper job statistics."""
    return _get_repo().get_whisper_stats()
