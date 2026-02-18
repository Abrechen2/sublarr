"""Quality/health-check database operations -- delegating to SQLAlchemy repository.

Thin wrapper with lazy-initialized repository for convenience access
from route handlers and other modules.
"""

from db.repositories.quality import QualityRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = QualityRepository()
    return _repo


def save_health_result(file_path: str, score: int, issues_json: str,
                       checks_run: int, checked_at: str) -> dict:
    """Save a health check result to the database."""
    return _get_repo().save_health_result(
        file_path, score, issues_json, checks_run, checked_at
    )


def get_health_result(file_path: str):
    """Get the most recent health result for a file path."""
    return _get_repo().get_health_result(file_path)


def get_health_results_for_series(path_prefix: str) -> list:
    """Get all health results for files under a series path prefix."""
    return _get_repo().get_health_results_for_series(path_prefix)


def get_quality_trends(days: int = 30) -> list:
    """Get daily average score and issue count for trend tracking."""
    return _get_repo().get_quality_trends(days)


def delete_health_results(file_path: str) -> int:
    """Delete all health results for a file path."""
    return _get_repo().delete_health_results(file_path)
