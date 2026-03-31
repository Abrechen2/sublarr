"""Statistics database operations -- delegating to StatisticsRepository."""

from __future__ import annotations

from db.repositories.statistics import StatisticsRepository

_repo: StatisticsRepository | None = None


def _get_repo() -> StatisticsRepository:
    global _repo
    if _repo is None:
        _repo = StatisticsRepository()
    return _repo


def get_daily_stats(days: int = 30) -> tuple[list[dict], dict]:
    """Return (daily_list, by_format_totals) for the last *days* days."""
    return _get_repo().get_daily_stats(days)


def get_downloads_by_provider() -> list[dict]:
    """Return subtitle download counts and average score per provider."""
    return _get_repo().get_downloads_by_provider()


def get_translation_backend_stats() -> list[dict]:
    """Return all translation_backend_stats rows."""
    return _get_repo().get_translation_backend_stats()


def get_upgrade_type_summary() -> list[dict]:
    """Return upgrade counts grouped by format-transition type."""
    return _get_repo().get_upgrade_type_summary()


def get_quality_trend(days: int = 30) -> list[dict]:
    """Return daily quality metrics for the last *days* days."""
    return _get_repo().get_quality_trend(days)


def get_series_quality() -> list[dict]:
    """Return per-series quality summary (top 20 by download count)."""
    return _get_repo().get_series_quality()
