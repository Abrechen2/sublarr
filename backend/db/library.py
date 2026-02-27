"""Download history and upgrade tracking operations -- delegating to SQLAlchemy repository."""

from db.repositories.library import LibraryRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = LibraryRepository()
    return _repo


def get_download_history(
    page: int = 1,
    per_page: int = 50,
    provider: str = None,
    language: str = None,
    format: str = None,
    score_min: int = None,
    score_max: int = None,
    search: str = None,
    sort_by: str = "downloaded_at",
    sort_dir: str = "desc",
) -> dict:
    """Get paginated download history with optional filters, sorting, and text search."""
    return _get_repo().get_download_history(
        page,
        per_page,
        provider,
        language,
        format=format,
        score_min=score_min,
        score_max=score_max,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


def get_download_stats() -> dict:
    """Get aggregated download statistics."""
    return _get_repo().get_download_stats()


def record_upgrade(
    file_path: str,
    old_format: str,
    old_score: int,
    new_format: str,
    new_score: int,
    provider_name: str = "",
    upgrade_reason: str = "",
):
    """Record a subtitle upgrade in history."""
    return _get_repo().record_upgrade(
        file_path, old_format, old_score, new_format, new_score, provider_name, upgrade_reason
    )


def get_upgrade_history(limit: int = 50) -> list:
    """Get recent upgrade history entries."""
    return _get_repo().get_upgrade_history(limit)


def get_upgrade_stats() -> dict:
    """Get aggregated upgrade statistics."""
    return _get_repo().get_upgrade_stats()


def get_library_stats() -> dict:
    """Get library statistics (download + upgrade combined)."""
    dl_stats = _get_repo().get_download_stats()
    up_stats = _get_repo().get_upgrade_stats()
    return {**dl_stats, "upgrades": up_stats}
