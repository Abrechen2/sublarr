"""Subtitle file path repository — thin access layer for subtitle_downloads paths.

Used by cleanup executors that need to enumerate all known subtitle paths
and remove stale DB entries for files that no longer exist on disk.
"""

import logging

from sqlalchemy import select

from db.models.providers import SubtitleDownload
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SubtitleRepository(BaseRepository):
    """Repository for subtitle file path operations used by cleanup executors."""

    def get_all_subtitle_paths(self) -> list[str]:
        """Return a list of all file_path values from subtitle_downloads.

        Returns:
            List of file path strings (may include paths that no longer exist).
        """
        stmt = select(SubtitleDownload.file_path)
        rows = self.session.execute(stmt).scalars().all()
        return list(rows)

    def delete_by_path(self, path: str) -> None:
        """Delete all subtitle_downloads rows with the given file_path.

        Args:
            path: Absolute file path to match against file_path column.
        """
        self.session.query(SubtitleDownload).filter_by(file_path=path).delete()
        self._commit()
