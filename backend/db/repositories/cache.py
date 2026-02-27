"""Cache and download history repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/cache.py with SQLAlchemy ORM
operations. Covers ffprobe_cache, episode_history (cross-table), and
anidb_mappings operations. Return types match the existing functions exactly.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select

from db.models.core import FfprobeCache, Job
from db.models.providers import SubtitleDownload
from db.models.standalone import AnidbMapping
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class CacheRepository(BaseRepository):
    """Repository for ffprobe_cache, episode history, and anidb_mappings operations."""

    # ---- App-level cache invalidation ----------------------------------------

    @staticmethod
    def invalidate_app_cache(prefix: str = "provider:") -> int:
        """Clear entries from the app-level fast cache (Redis or memory).

        Ensures that when DB cache is cleared, the fast cache layer is also
        invalidated. Safe to call from any context -- a Redis failure never
        blocks the caller.

        Args:
            prefix: Key prefix to clear. Defaults to "provider:" which covers
                    all provider search result cache entries.

        Returns:
            Number of keys cleared, or 0 if cache_backend is unavailable.
        """
        try:
            from flask import current_app

            cache_backend = getattr(current_app, "cache_backend", None)
            if cache_backend:
                return cache_backend.clear(prefix=prefix)
        except (RuntimeError, ImportError):
            pass  # Outside Flask context or Flask not available
        except Exception as e:
            logger.debug("App cache invalidation failed (non-blocking): %s", e)
        return 0

    # ---- FFprobe Cache -------------------------------------------------------

    def get_ffprobe_cache(self, file_path: str, mtime: float) -> dict | None:
        """Get cached ffprobe data if file hasn't changed (mtime matches)."""
        entry = self.session.execute(
            select(FfprobeCache.probe_data_json).where(
                FfprobeCache.file_path == file_path,
                FfprobeCache.mtime == mtime,
            )
        ).scalar_one_or_none()

        if entry:
            try:
                return json.loads(entry)
            except json.JSONDecodeError:
                return None
        return None

    def set_ffprobe_cache(self, file_path: str, mtime: float, probe_data: dict):
        """Cache ffprobe data for a file."""
        now = self._now()
        probe_json = json.dumps(probe_data)
        entry = FfprobeCache(
            file_path=file_path,
            mtime=mtime,
            probe_data_json=probe_json,
            cached_at=now,
        )
        self.session.merge(entry)
        self._commit()

    def clear_ffprobe_cache(self, file_path: str = None):
        """Clear ffprobe cache. If file_path is given, only clear that entry."""
        if file_path:
            entry = self.session.get(FfprobeCache, file_path)
            if entry:
                self.session.delete(entry)
        else:
            self.session.execute(delete(FfprobeCache))
        self._commit()

    # ---- Episode History (cross-table) ----------------------------------------

    def get_episode_history(self, file_path: str) -> list:
        """Get combined download + job history for a file path."""
        results = []

        # Match on the directory path since subtitle files share the base name
        base = file_path.rsplit(".", 1)[0] if "." in file_path else file_path
        like_pattern = base + "%"

        # Subtitle downloads
        dl_rows = self.session.execute(
            select(
                SubtitleDownload.provider_name,
                SubtitleDownload.format,
                SubtitleDownload.score,
                SubtitleDownload.downloaded_at,
            )
            .where(SubtitleDownload.file_path.like(like_pattern))
            .order_by(SubtitleDownload.downloaded_at.desc())
            .limit(50)
        ).all()

        for r in dl_rows:
            results.append(
                {
                    "action": "download",
                    "provider_name": r.provider_name,
                    "format": r.format,
                    "score": r.score,
                    "date": r.downloaded_at,
                    "status": "completed",
                    "error": "",
                }
            )

        # Translation jobs
        job_rows = self.session.execute(
            select(
                Job.file_path,
                Job.source_format,
                Job.status,
                Job.error,
                Job.created_at,
                Job.config_hash,
            )
            .where(Job.file_path.like(like_pattern))
            .order_by(Job.created_at.desc())
            .limit(50)
        ).all()

        for r in job_rows:
            results.append(
                {
                    "action": "translate",
                    "provider_name": "",
                    "format": r.source_format or "",
                    "score": 0,
                    "date": r.created_at,
                    "status": r.status,
                    "error": r.error or "",
                }
            )

        # Sort combined results by date descending
        results.sort(key=lambda x: x["date"], reverse=True)
        return results[:50]

    # ---- AniDB Mapping Operations ---------------------------------------------

    def get_anidb_mapping(self, tvdb_id: int) -> int | None:
        """Get cached AniDB ID for a TVDB ID.

        Returns:
            AniDB ID as int, or None if not found or expired.
        """
        from config import get_settings

        settings = get_settings()

        mapping = self.session.get(AnidbMapping, tvdb_id)
        if not mapping:
            return None

        # Check if cache entry is still valid (within TTL)
        cache_ttl_days = settings.anidb_cache_ttl_days
        if cache_ttl_days > 0:
            try:
                last_used = datetime.fromisoformat(mapping.last_used)
                age_days = (datetime.utcnow() - last_used).days
                if age_days > cache_ttl_days:
                    logger.debug(
                        "AniDB mapping for TVDB %d expired (age: %d days)", tvdb_id, age_days
                    )
                    return None
            except (ValueError, TypeError):
                return None

        # Update last_used timestamp
        mapping.last_used = self._now()
        self._commit()

        return mapping.anidb_id

    def save_anidb_mapping(self, tvdb_id: int, anidb_id: int, series_title: str = ""):
        """Save or update an AniDB mapping in the cache."""
        now = self._now()
        existing = self.session.get(AnidbMapping, tvdb_id)

        if existing:
            existing.anidb_id = anidb_id
            existing.series_title = series_title
            existing.last_used = now
        else:
            mapping = AnidbMapping(
                tvdb_id=tvdb_id,
                anidb_id=anidb_id,
                series_title=series_title,
                created_at=now,
                last_used=now,
            )
            self.session.add(mapping)

        self._commit()
        logger.debug("Saved AniDB mapping: TVDB %d -> AniDB %d", tvdb_id, anidb_id)

    def cleanup_old_anidb_mappings(self, days: int = 90) -> int:
        """Remove AniDB mappings older than specified days.

        Returns:
            Number of mappings deleted.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        result = self.session.execute(delete(AnidbMapping).where(AnidbMapping.last_used < cutoff))
        self._commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info("Cleaned up %d old AniDB mappings (older than %d days)", deleted, days)
        return deleted

    def get_anidb_mapping_stats(self) -> dict:
        """Get statistics about AniDB mappings cache.

        Returns:
            Dict with total_mappings, oldest_entry, newest_entry.
        """
        total = self.session.execute(select(func.count()).select_from(AnidbMapping)).scalar() or 0

        oldest = self.session.execute(
            select(AnidbMapping.created_at).order_by(AnidbMapping.created_at.asc()).limit(1)
        ).scalar_one_or_none()

        newest = self.session.execute(
            select(AnidbMapping.created_at).order_by(AnidbMapping.created_at.desc()).limit(1)
        ).scalar_one_or_none()

        return {
            "total_mappings": total,
            "oldest_entry": oldest,
            "newest_entry": newest,
        }
