"""Job and daily stats database operations -- delegating to SQLAlchemy repository."""

from db.repositories.jobs import JobRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = JobRepository()
    return _repo


# ---- Job CRUD ----


def create_job(file_path: str, force: bool = False, arr_context: dict = None) -> dict:
    """Create a new translation job in the database."""
    return _get_repo().create_job(file_path, force, arr_context)


def update_job(job_id: str, status: str, result: dict = None, error: str = None):
    """Update a job's status and result."""
    return _get_repo().update_job(job_id, status, result, error)


def get_job(job_id: str) -> dict | None:
    """Get a job by ID."""
    return _get_repo().get_job(job_id)


def get_jobs(page: int = 1, per_page: int = 50, status: str = None) -> dict:
    """Get paginated job list."""
    return _get_repo().get_jobs(page, per_page, status)


def get_pending_job_count() -> int:
    """Get count of queued/running jobs."""
    return _get_repo().get_pending_job_count()


def get_recent_jobs(limit: int = 10) -> list:
    """Get recent jobs ordered by created_at DESC."""
    return _get_repo().get_recent_jobs(limit)


def delete_job(job_id: str) -> bool:
    """Delete a job by ID."""
    return _get_repo().delete_job(job_id)


def delete_old_jobs(days: int) -> int:
    """Delete jobs older than N days. Returns count deleted."""
    return _get_repo().delete_old_jobs(days)


# ---- Stats Operations ----


def record_stat(success: bool, skipped: bool = False, fmt: str = "", source: str = ""):
    """Record a translation result in daily stats."""
    return _get_repo().record_daily_stats(success, skipped, fmt, source)


def get_daily_stats(days: int = 30) -> list:
    """Get last N days of daily stats."""
    return _get_repo().get_daily_stats(days)


def get_stats_summary() -> dict:
    """Get aggregated stats summary."""
    return _get_repo().get_stats_summary()


def get_outdated_jobs_count(current_hash: str) -> int:
    """Get count of completed jobs with a different config hash."""
    return _get_repo().get_outdated_jobs_count(current_hash)


def get_outdated_jobs(current_hash: str, limit: int = 100) -> list:
    """Get completed jobs with a different config hash (candidates for re-translation)."""
    return _get_repo().get_outdated_jobs(current_hash, limit)


# Keep private helper for backward compat (some code may import it)
def _row_to_job(row) -> dict:
    """Convert a database row to a job dict (legacy compat)."""
    if hasattr(row, "__dict__"):
        return _get_repo()._row_to_job(row)
    return dict(row) if row else None
