"""Download history and upgrade tracking repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/library.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging

from sqlalchemy import select, func

from db.models.core import UpgradeHistory
from db.models.providers import SubtitleDownload
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class LibraryRepository(BaseRepository):
    """Repository for subtitle_downloads and upgrade_history table operations."""

    # ---- Download History ----------------------------------------------------

    def get_download_history(self, page: int = 1, per_page: int = 50,
                             provider: str = None, language: str = None) -> dict:
        """Get paginated download history with optional filters.

        Returns:
            Dict with 'data', 'page', 'per_page', 'total', 'total_pages' keys.
        """
        offset = (page - 1) * per_page

        # Build filter conditions
        conditions = []
        if provider:
            conditions.append(SubtitleDownload.provider_name == provider)
        if language:
            conditions.append(SubtitleDownload.language == language)

        # Count query
        count_stmt = select(func.count()).select_from(SubtitleDownload)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        count = self.session.execute(count_stmt).scalar() or 0

        # Data query
        data_stmt = (
            select(SubtitleDownload)
            .order_by(SubtitleDownload.downloaded_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        for cond in conditions:
            data_stmt = data_stmt.where(cond)
        entries = self.session.execute(data_stmt).scalars().all()

        total_pages = max(1, (count + per_page - 1) // per_page)
        return {
            "data": [self._to_dict(e) for e in entries],
            "page": page,
            "per_page": per_page,
            "total": count,
            "total_pages": total_pages,
        }

    def get_download_stats(self) -> dict:
        """Get aggregated download statistics.

        Returns:
            Dict with total_downloads, by_provider, by_format, by_language,
            last_24h, last_7d keys.
        """
        total = self.session.execute(
            select(func.count()).select_from(SubtitleDownload)
        ).scalar() or 0

        # By provider
        by_provider_rows = self.session.execute(
            select(SubtitleDownload.provider_name, func.count())
            .group_by(SubtitleDownload.provider_name)
        ).all()
        by_provider = {row[0]: row[1] for row in by_provider_rows}

        # By format
        by_format_rows = self.session.execute(
            select(SubtitleDownload.format, func.count())
            .group_by(SubtitleDownload.format)
        ).all()
        by_format = {(row[0] or "unknown"): row[1] for row in by_format_rows}

        # By language
        by_language_rows = self.session.execute(
            select(SubtitleDownload.language, func.count())
            .group_by(SubtitleDownload.language)
        ).all()
        by_language = {(row[0] or "unknown"): row[1] for row in by_language_rows}

        # Last 24h and 7d using SQLite datetime function
        from sqlalchemy import text
        last_24h = self.session.execute(
            select(func.count()).select_from(SubtitleDownload)
            .where(SubtitleDownload.downloaded_at > text("datetime('now', '-1 day')"))
        ).scalar() or 0

        last_7d = self.session.execute(
            select(func.count()).select_from(SubtitleDownload)
            .where(SubtitleDownload.downloaded_at > text("datetime('now', '-7 days')"))
        ).scalar() or 0

        return {
            "total_downloads": total,
            "by_provider": by_provider,
            "by_format": by_format,
            "by_language": by_language,
            "last_24h": last_24h,
            "last_7d": last_7d,
        }

    # ---- Upgrade History -----------------------------------------------------

    def record_upgrade(self, file_path: str, old_format: str, old_score: int,
                       new_format: str, new_score: int,
                       provider_name: str = "", upgrade_reason: str = ""):
        """Record a subtitle upgrade in history."""
        now = self._now()
        entry = UpgradeHistory(
            file_path=file_path,
            old_format=old_format,
            old_score=old_score,
            new_format=new_format,
            new_score=new_score,
            provider_name=provider_name,
            upgrade_reason=upgrade_reason,
            upgraded_at=now,
        )
        self.session.add(entry)
        self._commit()

    def get_upgrade_history(self, limit: int = 50) -> list:
        """Get recent upgrade history entries.

        Returns:
            List of dicts ordered by upgraded_at descending.
        """
        stmt = (
            select(UpgradeHistory)
            .order_by(UpgradeHistory.upgraded_at.desc())
            .limit(limit)
        )
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_upgrade_stats(self) -> dict:
        """Get aggregated upgrade statistics.

        Returns:
            Dict with 'total' and 'srt_to_ass' counts.
        """
        total = self.session.execute(
            select(func.count()).select_from(UpgradeHistory)
        ).scalar() or 0

        srt_to_ass = self.session.execute(
            select(func.count()).select_from(UpgradeHistory)
            .where(
                UpgradeHistory.old_format == "srt",
                UpgradeHistory.new_format == "ass",
            )
        ).scalar() or 0

        return {"total": total, "srt_to_ass": srt_to_ass}
