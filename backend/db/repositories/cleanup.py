"""Cleanup repository: CRUD for subtitle hashes, cleanup rules, and history.

Provides deduplication queries, rule management, cleanup history logging,
and disk space analysis aggregations.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from db.models.cleanup import CleanupHistory, CleanupRule, SubtitleHash
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class CleanupRepository(BaseRepository):
    """Repository for cleanup-related table operations."""

    # ---- Subtitle Hashes -------------------------------------------------------

    def upsert_hash(self, file_path: str, content_hash: str, file_size: int,
                    format: str, language: str = None, line_count: int = None) -> dict:
        """Insert or update a subtitle hash record.

        Returns:
            Dict representation of the upserted record.
        """
        stmt = select(SubtitleHash).where(SubtitleHash.file_path == file_path)
        existing = self.session.execute(stmt).scalar_one_or_none()

        now = self._now()

        if existing:
            existing.content_hash = content_hash
            existing.file_size = file_size
            existing.format = format
            existing.language = language
            existing.line_count = line_count
            existing.last_scanned = now
            self._commit()
            return self._to_dict(existing)

        entry = SubtitleHash(
            file_path=file_path,
            content_hash=content_hash,
            file_size=file_size,
            format=format,
            language=language,
            line_count=line_count,
            last_scanned=now,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_hash_by_path(self, file_path: str) -> dict | None:
        """Get a subtitle hash record by file path.

        Returns:
            Dict or None if not found.
        """
        stmt = select(SubtitleHash).where(SubtitleHash.file_path == file_path)
        result = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(result)

    def get_duplicate_groups(self) -> list[dict]:
        """Get groups of files sharing the same content hash.

        Only returns groups with 2+ files (actual duplicates).

        Returns:
            List of dicts: [{hash, count, files: [{path, size, format, language}]}]
        """
        # Find content hashes with multiple files
        dup_hashes_stmt = (
            select(
                SubtitleHash.content_hash,
                func.count().label("cnt"),
            )
            .group_by(SubtitleHash.content_hash)
            .having(func.count() > 1)
        )
        dup_rows = self.session.execute(dup_hashes_stmt).all()

        groups = []
        for row in dup_rows:
            content_hash = row[0]
            count = row[1]

            files_stmt = (
                select(SubtitleHash)
                .where(SubtitleHash.content_hash == content_hash)
                .order_by(SubtitleHash.file_path)
            )
            files = self.session.execute(files_stmt).scalars().all()

            groups.append({
                "hash": content_hash,
                "count": count,
                "files": [
                    {
                        "path": f.file_path,
                        "size": f.file_size,
                        "format": f.format,
                        "language": f.language,
                    }
                    for f in files
                ],
            })

        return groups

    def delete_hashes_by_paths(self, file_paths: list[str]) -> int:
        """Delete hash records for the given file paths.

        Returns:
            Count of deleted records.
        """
        if not file_paths:
            return 0

        stmt = delete(SubtitleHash).where(SubtitleHash.file_path.in_(file_paths))
        result = self.session.execute(stmt)
        self._commit()
        return result.rowcount

    def get_hash_stats(self) -> dict:
        """Get aggregate statistics about stored hashes.

        Returns:
            Dict with total_files, total_size, unique_hashes.
        """
        stmt = select(
            func.count().label("total_files"),
            func.coalesce(func.sum(SubtitleHash.file_size), 0).label("total_size"),
            func.count(func.distinct(SubtitleHash.content_hash)).label("unique_hashes"),
        )
        row = self.session.execute(stmt).one()
        return {
            "total_files": row[0],
            "total_size": row[1],
            "unique_hashes": row[2],
        }

    # ---- Cleanup Rules ---------------------------------------------------------

    def create_rule(self, name: str, rule_type: str,
                    config_json: str = "{}", enabled: bool = True) -> dict:
        """Create a new cleanup rule.

        Returns:
            Dict representation of the created rule.
        """
        now = self._now()
        entry = CleanupRule(
            name=name,
            rule_type=rule_type,
            config_json=config_json,
            enabled=1 if enabled else 0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_rules(self) -> list[dict]:
        """Get all cleanup rules ordered by name.

        Returns:
            List of rule dicts.
        """
        stmt = select(CleanupRule).order_by(CleanupRule.name)
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_rule(self, rule_id: int) -> dict | None:
        """Get a single cleanup rule by ID.

        Returns:
            Dict or None if not found.
        """
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return self._to_dict(result)

    def update_rule(self, rule_id: int, **kwargs) -> dict | None:
        """Update a cleanup rule by ID.

        Accepts any combination of: name, rule_type, config_json, enabled.

        Returns:
            Updated dict or None if not found.
        """
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry is None:
            return None

        allowed_fields = {"name", "rule_type", "config_json", "enabled"}
        for key, value in kwargs.items():
            if key in allowed_fields:
                if key == "enabled":
                    value = 1 if value else 0
                setattr(entry, key, value)

        entry.updated_at = self._now()
        self._commit()
        return self._to_dict(entry)

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a cleanup rule by ID.

        Returns:
            True if deleted, False if not found.
        """
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry is None:
            return False
        self.session.delete(entry)
        self._commit()
        return True

    def update_rule_last_run(self, rule_id: int) -> None:
        """Update last_run_at timestamp for a rule."""
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry:
            entry.last_run_at = self._now()
            self._commit()

    # ---- Cleanup History -------------------------------------------------------

    def log_cleanup(self, action_type: str, files_processed: int = 0,
                    files_deleted: int = 0, bytes_freed: int = 0,
                    details_json: str = "{}", rule_id: int = None) -> dict:
        """Log a cleanup operation to history.

        Returns:
            Dict representation of the history entry.
        """
        entry = CleanupHistory(
            rule_id=rule_id,
            action_type=action_type,
            files_processed=files_processed,
            files_deleted=files_deleted,
            bytes_freed=bytes_freed,
            details_json=details_json,
            performed_at=self._now(),
        )
        self.session.add(entry)
        self._commit()
        return self._to_dict(entry)

    def get_history(self, page: int = 1, per_page: int = 50) -> dict:
        """Get paginated cleanup history.

        Returns:
            Dict with items, total, page, per_page.
        """
        count_stmt = select(func.count()).select_from(CleanupHistory)
        total = self.session.execute(count_stmt).scalar() or 0

        offset = (page - 1) * per_page
        stmt = (
            select(CleanupHistory)
            .order_by(CleanupHistory.performed_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        entries = self.session.execute(stmt).scalars().all()

        return {
            "items": [self._to_dict(e) for e in entries],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    def get_cleanup_stats(self) -> dict:
        """Get aggregate cleanup statistics.

        Returns:
            Dict with total_freed_bytes, total_files_deleted, total_operations.
        """
        stmt = select(
            func.coalesce(func.sum(CleanupHistory.bytes_freed), 0).label("total_freed"),
            func.coalesce(func.sum(CleanupHistory.files_deleted), 0).label("total_deleted"),
            func.count().label("total_operations"),
        )
        row = self.session.execute(stmt).one()
        return {
            "total_freed_bytes": row[0],
            "total_files_deleted": row[1],
            "total_operations": row[2],
        }

    # ---- Disk Analysis ---------------------------------------------------------

    def get_disk_stats(self) -> dict:
        """Get comprehensive disk space analysis from subtitle hashes.

        Returns:
            Dict with total_files, total_size, by_format, duplicate_count,
            duplicate_size, recent_cleanups (last 30 days of bytes_freed).
        """
        # Total files and size
        hash_stats = self.get_hash_stats()

        # By format breakdown
        format_stmt = (
            select(
                SubtitleHash.format,
                func.count().label("count"),
                func.coalesce(func.sum(SubtitleHash.file_size), 0).label("size"),
            )
            .group_by(SubtitleHash.format)
        )
        format_rows = self.session.execute(format_stmt).all()
        by_format = {
            row[0]: {"count": row[1], "size": row[2]}
            for row in format_rows
        }

        # Duplicate stats
        dup_subquery = (
            select(
                SubtitleHash.content_hash,
                func.count().label("cnt"),
            )
            .group_by(SubtitleHash.content_hash)
            .having(func.count() > 1)
            .subquery()
        )

        dup_files_stmt = (
            select(
                func.count().label("dup_count"),
                func.coalesce(func.sum(SubtitleHash.file_size), 0).label("dup_size"),
            )
            .join(dup_subquery, SubtitleHash.content_hash == dup_subquery.c.content_hash)
        )
        dup_row = self.session.execute(dup_files_stmt).one()
        duplicate_count = dup_row[0]
        duplicate_size = dup_row[1]

        # Potential savings = duplicate_size - (unique hash count * average single file size)
        # Simplified: count files that could be removed (total dups - one per group)
        groups = self.get_duplicate_groups()
        sum(g["count"] - 1 for g in groups)
        # Estimate savings: total dup size - keep one per group
        potential_savings = 0
        for g in groups:
            sizes = sorted(f["size"] for f in g["files"])
            # Keep largest, remove rest
            potential_savings += sum(sizes[:-1])

        # Recent cleanup trend (last 30 days)
        trend_stmt = (
            select(
                func.substr(CleanupHistory.performed_at, 1, 10).label("date"),
                func.coalesce(func.sum(CleanupHistory.bytes_freed), 0).label("freed"),
            )
            .where(
                CleanupHistory.performed_at > (datetime.now(UTC) - timedelta(days=30)).isoformat()
            )
            .group_by(func.substr(CleanupHistory.performed_at, 1, 10))
            .order_by(func.substr(CleanupHistory.performed_at, 1, 10))
        )
        trend_rows = self.session.execute(trend_stmt).all()
        recent_cleanups = [
            {"date": row[0], "bytes_freed": row[1]}
            for row in trend_rows
        ]

        return {
            "total_files": hash_stats["total_files"],
            "total_size_bytes": hash_stats["total_size"],
            "by_format": by_format,
            "duplicate_count": duplicate_count,
            "duplicate_size_bytes": duplicate_size,
            "potential_savings_bytes": potential_savings,
            "recent_cleanups": recent_cleanups,
        }
