"""Global search database operations -- delegating to SQLAlchemy repository.

Thin wrapper with lazy-initialized repository for convenience access
from route handlers and other modules.
"""

from db.repositories.search import SearchRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = SearchRepository()
    return _repo


def init_search_tables() -> None:
    """Create FTS5 virtual tables. Call from app.py after db.create_all()."""
    _get_repo().init_search_tables()


def rebuild_search_index() -> None:
    """Rebuild FTS5 tables from current DB state."""
    _get_repo().rebuild_index()


def search_all(query: str, limit: int = 20) -> dict:
    """FTS5 trigram search across series, episodes, and subtitles."""
    return _get_repo().search_all(query, limit=limit)
