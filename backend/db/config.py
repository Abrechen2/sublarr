"""Config entries database operations -- delegating to SQLAlchemy repository."""

from db.repositories.config import ConfigRepository

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = ConfigRepository()
    return _repo


def save_config_entry(key: str, value: str):
    """Save a config entry to the database."""
    return _get_repo().save_config_entry(key, value)


def get_config_entry(key: str):
    """Get a config entry from the database."""
    return _get_repo().get_config_entry(key)


def get_all_config_entries() -> dict:
    """Get all config entries."""
    return _get_repo().get_all_config_entries()
