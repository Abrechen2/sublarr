"""Blacklist database operations -- delegating to SQLAlchemy repository."""

from db.repositories.blacklist import BlacklistRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = BlacklistRepository()
    return _repo


def add_blacklist_entry(provider_name: str, subtitle_id: str,
                        language: str = "", file_path: str = "",
                        title: str = "", reason: str = "") -> int:
    """Add a subtitle to the blacklist. Returns the entry ID."""
    return _get_repo().add_blacklist_entry(
        provider_name, subtitle_id, language, file_path, title, reason
    )


def remove_blacklist_entry(entry_id: int) -> bool:
    """Remove a blacklist entry by ID. Returns True if deleted."""
    return _get_repo().remove_blacklist_entry(entry_id)


def clear_blacklist() -> int:
    """Remove all blacklist entries. Returns count deleted."""
    return _get_repo().clear_blacklist()


def is_blacklisted(provider_name: str, subtitle_id: str) -> bool:
    """Check if a subtitle is blacklisted."""
    return _get_repo().is_blacklisted(provider_name, subtitle_id)


def get_blacklist_entries(page: int = 1, per_page: int = 50) -> dict:
    """Get paginated blacklist entries."""
    return _get_repo().get_blacklist_entries(page, per_page)


def get_blacklist_count() -> int:
    """Get total number of blacklisted subtitles."""
    return _get_repo().get_blacklist_count()
