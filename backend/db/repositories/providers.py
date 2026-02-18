"""Provider cache, download history, and statistics repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/providers.py with SQLAlchemy ORM operations.
Return types match the existing functions exactly.

CRITICAL: The weighted running average for avg_response_time_ms MUST match the
existing formula: (old_avg * (total_searches - 1) + new_time) / total_searches.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, delete

from db.models.providers import ProviderCache, SubtitleDownload, ProviderStats
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ProviderRepository(BaseRepository):
    """Repository for provider_cache, subtitle_downloads, and provider_stats tables."""

    # ---- Provider Cache ----------------------------------------------------------

    def cache_provider_results(self, provider_name: str, query_hash: str,
                                results_json: str, ttl_hours: int = 6,
                                format_filter: str = None):
        """Cache provider search results with TTL expiry."""
        now = datetime.utcnow()
        expires = now + timedelta(hours=ttl_hours)
        entry = ProviderCache(
            provider_name=provider_name,
            query_hash=query_hash,
            results_json=results_json,
            cached_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        self.session.add(entry)
        self._commit()

    def get_cached_results(self, provider_name: str, query_hash: str,
                           format_filter: str = None) -> Optional[str]:
        """Get cached provider results if not expired.

        Returns:
            Cached results JSON string or None.
        """
        now = datetime.utcnow().isoformat()
        stmt = (
            select(ProviderCache.results_json)
            .where(
                ProviderCache.provider_name == provider_name,
                ProviderCache.query_hash == query_hash,
                ProviderCache.expires_at > now,
            )
            .order_by(ProviderCache.cached_at.desc())
            .limit(1)
        )
        result = self.session.execute(stmt).scalar()
        return result

    def cleanup_expired_cache(self):
        """Remove expired cache entries."""
        now = datetime.utcnow().isoformat()
        self.session.execute(
            delete(ProviderCache).where(ProviderCache.expires_at < now)
        )
        self._commit()

    def get_provider_cache_stats(self) -> dict:
        """Get aggregated cache stats per provider (total entries, active/expired)."""
        now = datetime.utcnow().isoformat()
        stmt = (
            select(
                ProviderCache.provider_name,
                func.count().label("total"),
                func.sum(
                    func.cast(ProviderCache.expires_at > now, type_=None)
                ).label("active"),
            )
            .group_by(ProviderCache.provider_name)
        )
        # Use manual approach for SQLite compatibility
        all_entries = self.session.execute(
            select(ProviderCache.provider_name, ProviderCache.expires_at)
        ).all()

        stats = {}
        for name, expires_at in all_entries:
            if name not in stats:
                stats[name] = {"total": 0, "active": 0}
            stats[name]["total"] += 1
            if expires_at > now:
                stats[name]["active"] += 1
        return stats

    def clear_provider_cache(self, provider_name: str = None):
        """Clear provider cache. If provider_name is given, only clear that provider."""
        if provider_name:
            self.session.execute(
                delete(ProviderCache).where(
                    ProviderCache.provider_name == provider_name
                )
            )
        else:
            self.session.execute(delete(ProviderCache))
        self._commit()

    # ---- Subtitle Download History -----------------------------------------------

    def record_subtitle_download(self, provider_name: str, subtitle_id: str,
                                  language: str, fmt: str, file_path: str,
                                  score: int):
        """Record a subtitle download for history tracking."""
        now = self._now()
        entry = SubtitleDownload(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            format=fmt,
            file_path=file_path,
            score=score,
            downloaded_at=now,
        )
        self.session.add(entry)
        self._commit()

    def get_provider_download_stats(self) -> dict:
        """Get download counts per provider, broken down by format."""
        stmt = (
            select(
                SubtitleDownload.provider_name,
                SubtitleDownload.format,
                func.count(),
            )
            .group_by(SubtitleDownload.provider_name, SubtitleDownload.format)
        )
        rows = self.session.execute(stmt).all()

        stats = {}
        for name, fmt, count in rows:
            if name not in stats:
                stats[name] = {"total": 0, "by_format": {}}
            fmt_key = fmt or "unknown"
            stats[name]["total"] += count
            stats[name]["by_format"][fmt_key] = count
        return stats

    # ---- Provider Statistics -----------------------------------------------------

    def record_search(self, provider_name: str, success: bool,
                      response_time_ms: float = None):
        """Record a search attempt and update provider statistics.

        Uses weighted running average for response times:
            new_avg = (old_avg * (n-1) + new_time) / n
        """
        now = self._now()
        existing = self.session.get(ProviderStats, provider_name)

        if existing:
            total_searches = (existing.total_searches or 0) + 1
            consecutive_failures = 0 if success else (existing.consecutive_failures or 0) + 1

            existing.total_searches = total_searches
            existing.consecutive_failures = consecutive_failures

            if success:
                existing.last_success_at = now
            else:
                existing.failed_downloads = (existing.failed_downloads or 0) + 1
                existing.last_failure_at = now

            # Update response time averages
            if response_time_ms is not None:
                existing.last_response_time_ms = response_time_ms
                old_avg = existing.avg_response_time_ms or 0
                if total_searches > 1:
                    existing.avg_response_time_ms = (
                        (old_avg * (total_searches - 1) + response_time_ms) / total_searches
                    )
                else:
                    existing.avg_response_time_ms = response_time_ms

            existing.updated_at = now
        else:
            entry = ProviderStats(
                provider_name=provider_name,
                total_searches=1,
                successful_downloads=0,
                failed_downloads=0 if success else 1,
                avg_score=0,
                last_success_at=now if success else None,
                last_failure_at=now if not success else None,
                consecutive_failures=0 if success else 1,
                avg_response_time_ms=response_time_ms or 0,
                last_response_time_ms=response_time_ms or 0,
                updated_at=now,
            )
            self.session.add(entry)
        self._commit()

    def record_download(self, provider_name: str, score: int):
        """Record a successful download and update average score.

        Uses weighted running average for avg_score:
            new_avg = (old_avg * old_downloads + score) / new_downloads
        """
        now = self._now()
        existing = self.session.get(ProviderStats, provider_name)

        if existing:
            old_downloads = existing.successful_downloads or 0
            new_downloads = old_downloads + 1
            existing.successful_downloads = new_downloads

            if score > 0:
                old_avg = existing.avg_score or 0
                existing.avg_score = (old_avg * old_downloads + score) / new_downloads

            existing.last_success_at = now
            existing.consecutive_failures = 0
            existing.updated_at = now
        else:
            entry = ProviderStats(
                provider_name=provider_name,
                total_searches=0,
                successful_downloads=1,
                failed_downloads=0,
                avg_score=score,
                last_success_at=now,
                consecutive_failures=0,
                avg_response_time_ms=0,
                last_response_time_ms=0,
                updated_at=now,
            )
            self.session.add(entry)
        self._commit()

    def record_download_failure(self, provider_name: str):
        """Record a failed download attempt."""
        now = self._now()
        existing = self.session.get(ProviderStats, provider_name)

        if existing:
            existing.failed_downloads = (existing.failed_downloads or 0) + 1
            existing.consecutive_failures = (existing.consecutive_failures or 0) + 1
            existing.last_failure_at = now
            existing.updated_at = now
        else:
            entry = ProviderStats(
                provider_name=provider_name,
                total_searches=0,
                successful_downloads=0,
                failed_downloads=1,
                avg_score=0,
                last_failure_at=now,
                consecutive_failures=1,
                avg_response_time_ms=0,
                last_response_time_ms=0,
                updated_at=now,
            )
            self.session.add(entry)
        self._commit()

    def get_provider_stats(self, provider_name: str = None) -> dict:
        """Get provider statistics.

        Args:
            provider_name: Optional provider name. If None, returns all providers.

        Returns:
            If provider_name given: dict of stats or empty dict.
            If None: dict keyed by provider_name.
        """
        if provider_name:
            entry = self.session.get(ProviderStats, provider_name)
            if not entry:
                return {}
            return self._row_to_stats(entry)
        else:
            stmt = select(ProviderStats)
            entries = self.session.execute(stmt).scalars().all()
            return {e.provider_name: self._row_to_stats(e) for e in entries}

    def get_all_provider_stats(self) -> list:
        """Get all provider stats as a list of dicts."""
        stmt = select(ProviderStats)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_stats(e) for e in entries]

    def clear_provider_stats(self, provider_name: str) -> bool:
        """Clear stats for a specific provider. Returns True if deleted."""
        entry = self.session.get(ProviderStats, provider_name)
        if not entry:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    # ---- Auto-disable logic ------------------------------------------------------

    def check_auto_disable(self, provider_name: str, threshold: int) -> bool:
        """Check if consecutive_failures >= threshold. If so, auto-disable.

        Returns True if the provider was disabled.
        """
        entry = self.session.get(ProviderStats, provider_name)
        if not entry:
            return False

        if (entry.consecutive_failures or 0) >= threshold:
            entry.auto_disabled = 1
            # Default cooldown: disabled until explicitly cleared
            entry.disabled_until = ""
            entry.updated_at = self._now()
            self._commit()
            return True
        return False

    def auto_disable_provider(self, provider_name: str, cooldown_minutes: int = 30):
        """Auto-disable a provider with a cooldown period."""
        now = datetime.utcnow()
        disabled_until = (now + timedelta(minutes=cooldown_minutes)).isoformat()

        existing = self.session.get(ProviderStats, provider_name)
        if existing:
            existing.auto_disabled = 1
            existing.disabled_until = disabled_until
            existing.updated_at = now.isoformat()
        else:
            entry = ProviderStats(
                provider_name=provider_name,
                auto_disabled=1,
                disabled_until=disabled_until,
                updated_at=now.isoformat(),
            )
            self.session.add(entry)
        self._commit()
        logger.warning("Provider %s auto-disabled until %s (%d min cooldown)",
                       provider_name, disabled_until, cooldown_minutes)

    def clear_auto_disable(self, provider_name: str) -> bool:
        """Manually clear auto-disable flag. Resets consecutive_failures to 0."""
        entry = self.session.get(ProviderStats, provider_name)
        if not entry:
            return False
        entry.auto_disabled = 0
        entry.disabled_until = ""
        entry.consecutive_failures = 0
        entry.updated_at = self._now()
        self._commit()
        logger.info("Provider %s manually re-enabled (auto-disable cleared)",
                     provider_name)
        return True

    def is_auto_disabled(self, provider_name: str) -> bool:
        """Check if a provider is currently auto-disabled.

        If the disabled_until time has passed, automatically clears the flag.
        """
        entry = self.session.get(ProviderStats, provider_name)
        if not entry:
            return False
        if not entry.auto_disabled:
            return False

        # Check if cooldown has expired
        disabled_until = entry.disabled_until
        if disabled_until:
            now = datetime.utcnow().isoformat()
            if disabled_until < now:
                # Cooldown expired, clear auto-disable
                entry.auto_disabled = 0
                entry.disabled_until = ""
                entry.updated_at = now
                self._commit()
                logger.info("Provider %s auto-disable expired, re-enabled",
                            provider_name)
                return False
        return True

    def get_disabled_providers(self) -> list:
        """Get all currently auto-disabled providers."""
        stmt = select(ProviderStats).where(ProviderStats.auto_disabled == 1)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_stats(e) for e in entries]

    def get_provider_health_history(self, provider_name: str = None,
                                     days: int = 7) -> list:
        """Get provider health history entries."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        stmt = select(ProviderStats).where(ProviderStats.updated_at >= cutoff)
        if provider_name:
            stmt = stmt.where(ProviderStats.provider_name == provider_name)
        entries = self.session.execute(stmt).scalars().all()
        return [self._row_to_stats(e) for e in entries]

    def get_provider_success_rate(self, provider_name: str) -> float:
        """Get success rate for a provider (0.0 to 1.0)."""
        entry = self.session.get(ProviderStats, provider_name)
        if not entry or not entry.total_searches:
            return 0.0
        return (entry.successful_downloads or 0) / entry.total_searches

    # ---- Helpers -----------------------------------------------------------------

    def _row_to_stats(self, entry: ProviderStats) -> dict:
        """Convert a ProviderStats model to a dict."""
        return self._to_dict(entry)
