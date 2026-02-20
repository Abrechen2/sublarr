"""Wanted items database operations -- delegating to SQLAlchemy repository."""

from typing import Optional

from db.repositories.wanted import WantedRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = WantedRepository()
    return _repo


def upsert_wanted_item(item_type: str, file_path: str, title: str = "",
                       season_episode: str = "", existing_sub: str = "",
                       missing_languages: list = None,
                       sonarr_series_id: int = None,
                       sonarr_episode_id: int = None,
                       radarr_movie_id: int = None,
                       standalone_series_id: int = None,
                       standalone_movie_id: int = None,
                       upgrade_candidate: bool = False,
                       current_score: int = 0,
                       target_language: str = "",
                       instance_name: str = "",
                       subtitle_type: str = "full") -> tuple:
    """Insert or update a wanted item. Returns (row_id, was_updated)."""
    return _get_repo().upsert_wanted_item(
        item_type, file_path, title, season_episode, existing_sub,
        missing_languages, sonarr_series_id, sonarr_episode_id,
        radarr_movie_id, standalone_series_id, standalone_movie_id,
        upgrade_candidate, current_score, target_language, instance_name,
        subtitle_type
    )


def get_wanted_items(page: int = 1, per_page: int = 50,
                     item_type: str = None, status: str = None,
                     series_id: int = None,
                     subtitle_type: str = None,
                     sort_by: str = "added_at",
                     sort_dir: str = "desc",
                     search: str = None) -> dict:
    """Get paginated wanted items with optional filters, sorting, and text search."""
    return _get_repo().get_wanted_items(
        page, per_page, item_type, status, series_id, subtitle_type,
        sort_by=sort_by, sort_dir=sort_dir, search=search,
    )


def get_wanted_item(item_id: int) -> Optional[dict]:
    """Get a single wanted item by ID."""
    return _get_repo().get_wanted_item(item_id)


def get_wanted_item_by_path(file_path: str) -> Optional[dict]:
    """Get a wanted item by file path."""
    return _get_repo().get_wanted_by_file_path(file_path)


def update_wanted_status(item_id: int, status: str, error: str = ""):
    """Update a wanted item's status."""
    return _get_repo().update_wanted_status(item_id, status, error)


def update_wanted_search(item_id: int):
    """Increment search_count and set last_search_at."""
    return _get_repo().mark_search_attempted(item_id)


def delete_wanted_items(file_paths: list):
    """Delete wanted items by file paths (batch)."""
    for fp in (file_paths or []):
        _get_repo().delete_wanted_by_file_path(fp)


def delete_wanted_item(item_id: int):
    """Delete a single wanted item."""
    return _get_repo().delete_wanted_item(item_id)


def delete_wanted_items_by_ids(item_ids: list):
    """Delete wanted items by their IDs (batch)."""
    return _get_repo().delete_wanted_items_by_ids(item_ids)


def get_wanted_count(status: str = None) -> int:
    """Get count of wanted items with optional status filter."""
    return _get_repo().get_wanted_count(status)


def get_wanted_summary() -> dict:
    """Get aggregated wanted counts by type, status, and existing_sub."""
    return _get_repo().get_wanted_summary()


def get_all_wanted_file_paths() -> set:
    """Get all file paths currently in the wanted table (for cleanup)."""
    return _get_repo().get_all_wanted_file_paths()


def get_wanted_items_for_cleanup() -> list:
    """Get wanted items with file_path, target_language, instance_name, and id for cleanup."""
    return _get_repo().cleanup_wanted_items()


def get_upgradeable_count() -> int:
    """Get count of items marked as upgrade candidates."""
    return _get_repo().get_upgradeable_count()


def find_wanted_by_episode(sonarr_episode_id: int, target_language: str = "") -> Optional[dict]:
    """Find a wanted item for a specific episode + language."""
    return _get_repo().find_wanted_by_episode(sonarr_episode_id, target_language)


def get_series_missing_counts() -> dict:
    """Get count of 'wanted' items per Sonarr series ID.

    Returns:
        Dict mapping sonarr_series_id -> count of wanted items.
    """
    return _get_repo().get_series_missing_counts()


def get_wanted_by_subtitle_type() -> dict:
    """Get wanted item counts grouped by subtitle_type."""
    return _get_repo().get_wanted_by_subtitle_type()


# Keep private helper for backward compat
def _row_to_wanted(row) -> dict:
    """Convert a database row to a wanted item dict (legacy compat)."""
    if hasattr(row, '__dict__'):
        return _get_repo()._row_to_wanted(row)
    return dict(row) if row else None
