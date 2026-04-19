"""Blacklist entries repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/blacklist.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import func, select

from db.models.core import BlacklistEntry
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class BlacklistRepository(BaseRepository):
    """Repository for blacklist_entries table operations."""

    def add_blacklist_entry(
        self,
        provider_name: str,
        subtitle_id: str,
        language: str = "",
        file_path: str = "",
        title: str = "",
        reason: str = "",
        file_hash: str | None = None,
    ) -> int:
        """Add a subtitle to the blacklist. Returns the entry ID.

        Uses INSERT OR IGNORE semantics via checking existence first.

        If ``file_hash`` is provided, we also check for existing
        ``(provider, file_hash)`` conflicts — the partial UNIQUE index
        would reject the insert anyway, so we surface the existing ID
        instead of raising.
        """
        now = self._now()

        # Check if already blacklisted by (provider, subtitle_id) first
        existing = self.session.execute(
            select(BlacklistEntry).where(
                BlacklistEntry.provider_name == provider_name,
                BlacklistEntry.subtitle_id == subtitle_id,
            )
        ).scalar_one_or_none()

        if existing:
            return existing.id

        # If a file_hash was provided, also check by (provider, file_hash)
        if file_hash is not None:
            existing_by_hash = self.session.execute(
                select(BlacklistEntry).where(
                    BlacklistEntry.provider_name == provider_name,
                    BlacklistEntry.file_hash == file_hash,
                )
            ).scalar_one_or_none()
            if existing_by_hash:
                return existing_by_hash.id

        entry = BlacklistEntry(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            file_path=file_path,
            title=title,
            reason=reason,
            file_hash=file_hash,
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
        count = self.session.execute(select(func.count()).select_from(BlacklistEntry)).scalar()
        self.session.query(BlacklistEntry).delete()
        self._commit()
        return count or 0

    def is_blacklisted(
        self,
        provider_name: str,
        subtitle_id: str | None = None,
        file_hash: str | None = None,
    ) -> bool:
        """Check if a subtitle is blacklisted.

        Callers may pass either ``subtitle_id`` (traditional) or
        ``file_hash`` (Plan B3). If both are passed, ANY match returns
        True. If neither is passed, returns False (caller error — no
        discriminator).
        """
        if subtitle_id is None and file_hash is None:
            return False

        conditions = [BlacklistEntry.provider_name == provider_name]
        if subtitle_id is not None and file_hash is not None:
            # Either discriminator matching counts
            from sqlalchemy import or_

            conditions.append(
                or_(
                    BlacklistEntry.subtitle_id == subtitle_id,
                    BlacklistEntry.file_hash == file_hash,
                )
            )
        elif subtitle_id is not None:
            conditions.append(BlacklistEntry.subtitle_id == subtitle_id)
        else:  # file_hash is not None (enforced by the early-return above)
            conditions.append(BlacklistEntry.file_hash == file_hash)

        result = self.session.execute(
            select(BlacklistEntry.id).where(*conditions)
        ).scalar_one_or_none()
        return result is not None

    def is_blacklisted_by_hash(self, provider_name: str, file_hash: str) -> bool:
        """Check if a ``(provider, file_hash)`` pair is blacklisted.

        Convenience wrapper around :meth:`is_blacklisted` for hash-only
        callers.
        """
        return self.is_blacklisted(provider_name=provider_name, file_hash=file_hash)

    def get_blacklist_entries(self, page: int = 1, per_page: int = 50) -> dict:
        """Get paginated blacklist entries.

        Returns:
            Dict with 'data', 'page', 'per_page', 'total', 'total_pages' keys.
        """
        offset = (page - 1) * per_page

        count = self.session.execute(select(func.count()).select_from(BlacklistEntry)).scalar() or 0

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
        return self.session.execute(select(func.count()).select_from(BlacklistEntry)).scalar() or 0
