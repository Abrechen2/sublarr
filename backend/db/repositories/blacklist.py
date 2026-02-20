"""Blacklist entries repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/blacklist.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import select, func

from db.models.core import BlacklistEntry
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class BlacklistRepository(BaseRepository):
    """Repository for blacklist_entries table operations."""

    def add_blacklist_entry(self, provider_name: str, subtitle_id: str,
                            language: str = "", file_path: str = "",
                            title: str = "", reason: str = "") -> int:
        """Add a subtitle to the blacklist. Returns the entry ID.

        Uses INSERT OR IGNORE semantics via checking existence first.
        """
        now = self._now()

        # Check if already blacklisted (mirrors INSERT OR IGNORE)
        existing = self.session.execute(
            select(BlacklistEntry).where(
                BlacklistEntry.provider_name == provider_name,
                BlacklistEntry.subtitle_id == subtitle_id,
            )
        ).scalar_one_or_none()

        if existing:
            return existing.id

        entry = BlacklistEntry(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            file_path=file_path,
            title=title,
            reason=reason,
            added_at=now,
        )
        self.session.add(entry)
        self._commit()
        return entry.id or 0

    def remove_blacklist_entry(self, entry_id: int) -> bool:
        """Remove a blacklist entry by ID. Returns True if deleted."""
        entry = self.session.get(BlacklistEntry, entry_id)
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def clear_blacklist(self) -> int:
        """Remove all blacklist entries. Returns count deleted."""
        count = self.session.execute(
            select(func.count()).select_from(BlacklistEntry)
        ).scalar()
        self.session.query(BlacklistEntry).delete()
        self._commit()
        return count or 0

    def is_blacklisted(self, provider_name: str, subtitle_id: str) -> bool:
        """Check if a subtitle is blacklisted."""
        result = self.session.execute(
            select(BlacklistEntry.id).where(
                BlacklistEntry.provider_name == provider_name,
                BlacklistEntry.subtitle_id == subtitle_id,
            )
        ).scalar_one_or_none()
        return result is not None

    def get_blacklist_entries(self, page: int = 1, per_page: int = 50) -> dict:
        """Get paginated blacklist entries.

        Returns:
            Dict with 'data', 'page', 'per_page', 'total', 'total_pages' keys.
        """
        offset = (page - 1) * per_page

        count = self.session.execute(
            select(func.count()).select_from(BlacklistEntry)
        ).scalar() or 0

        stmt = (
            select(BlacklistEntry)
            .order_by(BlacklistEntry.added_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        entries = self.session.execute(stmt).scalars().all()

        total_pages = max(1, (count + per_page - 1) // per_page)
        return {
            "data": [self._to_dict(e) for e in entries],
            "page": page,
            "per_page": per_page,
            "total": count,
            "total_pages": total_pages,
        }

    def get_blacklist_count(self) -> int:
        """Get total number of blacklisted subtitles."""
        return self.session.execute(
            select(func.count()).select_from(BlacklistEntry)
        ).scalar() or 0
