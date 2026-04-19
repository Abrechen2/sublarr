"""Blacklist database operations -- delegating to SQLAlchemy repository."""

import logging
import os

from db.repositories.blacklist import BlacklistRepository

logger = logging.getLogger(__name__)

_repo = None


def _get_repo():
    global _repo
    if _repo is None:
        _repo = BlacklistRepository()
    return _repo


def add_blacklist_entry(
    provider_name: str,
    subtitle_id: str,
    language: str = "",
    file_path: str = "",
    title: str = "",
    reason: str = "",
    file_hash: str | None = None,
) -> int:
    """Add a subtitle to the blacklist. Returns the entry ID."""
    return _get_repo().add_blacklist_entry(
        provider_name,
        subtitle_id,
        language,
        file_path,
        title,
        reason,
        file_hash=file_hash,
    )


def remove_blacklist_entry(entry_id: int) -> bool:
    """Remove a blacklist entry by ID. Returns True if deleted."""
    return _get_repo().remove_blacklist_entry(entry_id)


def clear_blacklist() -> int:
    """Remove all blacklist entries. Returns count deleted."""
    return _get_repo().clear_blacklist()


def is_blacklisted(
    provider_name: str,
    subtitle_id: str | None = None,
    file_hash: str | None = None,
) -> bool:
    """Check if a subtitle is blacklisted (by subtitle_id or file_hash)."""
    return _get_repo().is_blacklisted(
        provider_name, subtitle_id=subtitle_id, file_hash=file_hash
    )


def is_blacklisted_by_hash(provider_name: str, file_hash: str) -> bool:
    """Check if a ``(provider, file_hash)`` pair is blacklisted."""
    return _get_repo().is_blacklisted_by_hash(provider_name, file_hash)


def get_blacklist_entries(page: int = 1, per_page: int = 50) -> dict:
    """Get paginated blacklist entries."""
    return _get_repo().get_blacklist_entries(page, per_page)


def get_blacklist_count() -> int:
    """Get total number of blacklisted subtitles."""
    return _get_repo().get_blacklist_count()


def blacklist_subtitle_sidecar(subtitle_path: str) -> None:
    """Add a subtitle sidecar to the blacklist (best-effort, never raises).

    Derives the video base path from the subtitle path (strips lang + ext),
    then looks up provider/subtitle_id in subtitle_downloads.
    """
    try:
        from sqlalchemy import text as _text

        from extensions import db as sa_db

        parts = os.path.basename(subtitle_path).split(".")
        if len(parts) < 3:
            return
        lang = parts[-2]
        base_name = ".".join(parts[:-2])
        base_path = os.path.join(os.path.dirname(subtitle_path), base_name)

        with sa_db.engine.connect() as conn:
            row = conn.execute(
                _text(
                    "SELECT provider_name, subtitle_id, language"
                    " FROM subtitle_downloads"
                    " WHERE file_path LIKE :p AND language = :lang"
                    " ORDER BY downloaded_at DESC LIMIT 1"
                ),
                {"p": base_path + ".%", "lang": lang},
            ).fetchone()

        if row:
            add_blacklist_entry(
                provider_name=row[0] or "manual",
                subtitle_id=row[1] or "",
                language=row[2] or lang,
                file_path=subtitle_path,
                reason="Deleted from library",
            )
    except Exception as exc:
        logger.debug("Could not add blacklist entry for %s: %s", subtitle_path, exc)
