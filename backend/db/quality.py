"""Quality/health-check database operations -- delegating to SQLAlchemy repository.

Thin wrapper with lazy-initialized repository for convenience access
from route handlers and other modules.
"""

from datetime import datetime

from db.repositories.quality import QualityRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = QualityRepository()
    return _repo


def save_health_result(
    file_path: str, score: int, issues_json: str, checks_run: int, checked_at: datetime
) -> dict:
    """Save a health check result to the database."""
    return _get_repo().save_health_result(file_path, score, issues_json, checks_run, checked_at)


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


def mark_user_modified(file_path: str, source: str = "editor") -> dict:
    """Mark a subtitle file as hand-edited (editor save)."""
    return _get_repo().mark_user_modified(file_path, source)


def is_user_modified(file_path: str) -> bool:
    """Whether a subtitle file carries the hand-edited marker."""
    return _get_repo().is_user_modified(file_path)


def clear_user_modified(file_path: str) -> int:
    """Remove the hand-edited marker (after a deliberate replace)."""
    return _get_repo().clear_user_modified(file_path)


# ---- AI quality verdicts (advisory) ------------------------------------------


def save_ai_quality_result(
    file_path: str,
    language: str,
    verdict: str,
    scores_json: str,
    reasons_json: str,
    model: str,
    sampled_cues: int,
) -> dict:
    """Save the AI quality verdict for a sidecar, replacing any previous row."""
    return _get_repo().save_ai_quality_result(
        file_path, language, verdict, scores_json, reasons_json, model, sampled_cues
    )


def get_ai_quality_result(file_path: str):
    """Get the AI quality verdict for a sidecar path, or None."""
    return _get_repo().get_ai_quality_result(file_path)


def get_ai_quality_results_for_paths(paths: list) -> dict:
    """Batch-fetch AI verdicts keyed by sidecar path."""
    return _get_repo().get_ai_quality_results_for_paths(paths)


def delete_ai_quality_result(file_path: str) -> int:
    """Delete AI verdicts for a sidecar path."""
    return _get_repo().delete_ai_quality_result(file_path)
