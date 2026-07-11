"""Cleanup repository: CRUD for subtitle hashes, cleanup rules, and history.

Provides deduplication queries, rule management, cleanup history logging,
and disk space analysis aggregations.
"""

import json as _json
import logging
import os
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import Date, cast, delete, func, select

from db.models.cleanup import CleanupHistory, CleanupRule, SubtitleHash
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Episode-code extractor. Matches e.g. "S01E10", "s1e3" in a filename.
# Used by duplicate-group classification to flag groups where identical
# content is shared across different episodes — almost always a sign the
# subtitle was saved under the wrong filename, not a safe-to-dedup case.
_EP_CODE_RE = re.compile(r"s\d+e\d+", re.IGNORECASE)


def _episode_code(file_path: str) -> str | None:
    """Return the SxxEyy code from the filename, or None when absent."""
    match = _EP_CODE_RE.search(os.path.basename(file_path))
    return match.group(0).lower() if match else None


def _dialect_insert(session):
    """Return the dialect-specific insert function (supports ON CONFLICT)."""
    from extensions import db as _db

    dialect = _db.engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert

        return insert
    from sqlalchemy.dialects.sqlite import insert

    return insert


class CleanupRepository(BaseRepository):
    """Repository for cleanup-related table operations."""

    # ---- Subtitle Hashes -------------------------------------------------------

    def upsert_hash(
        self,
        file_path: str,
        content_hash: str,
        file_size: int,
        format: str,
        language: str = None,
        line_count: int = None,
    ) -> dict:
        """Atomically insert or update a subtitle hash record.

        Uses INSERT ... ON CONFLICT DO UPDATE to avoid race conditions
        when multiple threads hash the same file concurrently.

        Returns:
            Dict representation of the upserted record.
        """
        now = self._now()
        insert = _dialect_insert(self.session)

        values = {
            "file_path": file_path,
            "content_hash": content_hash,
            "file_size": file_size,
            "format": format,
            "language": language,
            "line_count": line_count,
            "last_scanned": now,
        }

        stmt = insert(SubtitleHash).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["file_path"],
            set_={
                "content_hash": stmt.excluded.content_hash,
                "file_size": stmt.excluded.file_size,
                "format": stmt.excluded.format,
                "language": stmt.excluded.language,
                "line_count": stmt.excluded.line_count,
                "last_scanned": stmt.excluded.last_scanned,
            },
        )
        self.session.execute(stmt)
        self._commit()

        # Return the current state of the record
        row = self.session.execute(
            select(SubtitleHash).where(SubtitleHash.file_path == file_path)
        ).scalar_one_or_none()
        return self._to_dict(row)

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
        # Single query: fetch all duplicate files using a subquery for the duplicate hashes
        dup_hashes_subq = (
            select(SubtitleHash.content_hash)
            .group_by(SubtitleHash.content_hash)
            .having(func.count() > 1)
            .scalar_subquery()
        )
        all_dup_files = (
            self.session.execute(
                select(SubtitleHash)
                .where(SubtitleHash.content_hash.in_(dup_hashes_subq))
                .order_by(SubtitleHash.content_hash, SubtitleHash.file_path)
            )
            .scalars()
            .all()
        )

        # Group in Python — already ordered by content_hash
        groups: dict[str, list] = {}
        for f in all_dup_files:
            groups.setdefault(f.content_hash, []).append(
                {
                    "file_path": f.file_path,
                    "content_hash": f.content_hash,
                    "file_size": f.file_size,
                    "format": f.format,
                    "language": f.language,
                    "line_count": f.line_count,
                    "last_scanned": f.last_scanned.isoformat() if f.last_scanned else None,
                }
            )

        def _cross_episode(files: list[dict]) -> bool:
            """Flag groups whose files belong to different episodes.

            Identical-content subtitles in the *same* episode (different
            languages, re-encodes) are safe to dedup. Identical content in
            *different* episodes almost always means the subtitle was
            misfiled — deleting one leaves the wrong one behind. Callers
            should surface a warning in the UI when this is true.
            """
            codes: set[str] = set()
            missing = 0
            for f in files:
                code = _episode_code(f["file_path"])
                if code is None:
                    missing += 1
                else:
                    codes.add(code)
            # More than one distinct episode code → cross-episode.
            if len(codes) > 1:
                return True
            # Mix of files with and without codes → suspicious; warn.
            return bool(codes and missing)

        return [
            {
                "content_hash": h,
                "count": len(files),
                "files": files,
                "cross_episode": _cross_episode(files),
            }
            for h, files in groups.items()
        ]

    def find_by_content_hash(self, content_hash: str) -> list[dict]:
        """Find all subtitle hash records matching the given SHA-256 hash.

        Args:
            content_hash: SHA-256 hex digest to look up.

        Returns:
            List of dicts with file_path, format, language for each match.
        """
        stmt = select(SubtitleHash).where(SubtitleHash.content_hash == content_hash)
        rows = self.session.execute(stmt).scalars().all()
        return [
            {"file_path": r.file_path, "format": r.format, "language": r.language} for r in rows
        ]

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

    # Default rules seeded on every fresh install.  Each entry must include all
    # fields accepted by create_rule().  Rules are keyed by rule_type — the seed
    # is skipped for any type that already has a row (idempotent).
    _DEFAULT_CLEANUP_RULES: list[dict] = [
        {
            "name": "Signs cleanup",
            "rule_type": "signs_cleanup",
            "enabled": False,
            "schedule": "weekly",
            "config_json": _json.dumps(
                {
                    "keep_languages": ["de", "en"],
                    "strip_embedded": True,
                    "permanent_delete": False,
                }
            ),
        },
    ]

    # Default rules introduced AFTER the global first-boot seed flag was already
    # set on existing installs. The full seed below short-circuits on that flag,
    # so a newly-added default would otherwise never reach an existing library
    # (e.g. the subtitle-.bak cleanup was orphaned — its executor existed but no
    # rule was ever created, so .bak files piled up forever). Each back-fill is
    # guarded by its own per-type flag, so it is offered exactly once and a
    # user-deleted rule is never resurrected.
    _BACKFILL_CLEANUP_RULES: list[dict] = [
        {
            "name": "Old subtitle backups",
            "rule_type": "old_subtitle_baks",
            # Seeded DISABLED (like signs_cleanup): the feature becomes available
            # in the UI without silently deleting files on upgrade. The user
            # opts in. Retention falls back to subtitle_bak_retention_days (30d).
            "enabled": False,
            "schedule": "weekly",
            "config_json": "{}",
        },
        {
            "name": "Foreign-Track Cleanup",
            "rule_type": "foreign_tracks",
            # The ONLY path that strips embedded foreign subtitle tracks from an
            # EXISTING library — the post-extract hook only ever touches the file
            # it is currently processing. Without this rule a library keeps every
            # foreign track it was imported with.
            #
            # Seeded DISABLED (same convention as signs_cleanup): remuxing is
            # destructive, so an upgrade must never rewrite media unasked. Once
            # the user opts in, "weekly" means Sublarr sweeps on its own — a
            # "manual" schedule is skipped by the nightly cleanup job entirely.
            #
            # Empty config: keep_languages / keep_und are inherited from the
            # global cleanup_foreign_tracks_* settings at run time.
            "enabled": False,
            "schedule": "weekly",
            "config_json": "{}",
        },
    ]

    # Config flag marking that the built-in defaults were offered once. Once
    # set, seeding is skipped forever so a user who deletes a default rule does
    # not get it resurrected on the next restart ("on first boot" semantics).
    _DEFAULTS_SEEDED_FLAG = "cleanup_default_rules_seeded"

    def ensure_default_rules(self) -> None:
        """Seed built-in cleanup rules on first boot only.

        Idempotent and "first boot" aware: a config flag records that the
        defaults were already offered. On the very first call ever it creates
        any missing default rule and sets the flag; every later call sees the
        flag and returns immediately, so a user-deleted default stays deleted.
        """
        from db.repositories.config import ConfigRepository

        config_repo = ConfigRepository()
        existing_types = {r["rule_type"] for r in self.get_rules()}

        # Full first-boot seed (once, guarded by the global flag).
        if not config_repo.get_config_entry(self._DEFAULTS_SEEDED_FLAG):
            for spec in self._DEFAULT_CLEANUP_RULES:
                if spec["rule_type"] not in existing_types:
                    self.create_rule(
                        name=spec["name"],
                        rule_type=spec["rule_type"],
                        config_json=spec["config_json"],
                        enabled=spec["enabled"],
                        schedule=spec["schedule"],
                    )
                    existing_types.add(spec["rule_type"])
            config_repo.save_config_entry(self._DEFAULTS_SEEDED_FLAG, "1")

        # Per-type back-fill for defaults added after the global flag was set.
        # Runs regardless of the flag but each type is offered exactly once.
        for spec in self._BACKFILL_CLEANUP_RULES:
            flag = f"cleanup_seeded_{spec['rule_type']}"
            if config_repo.get_config_entry(flag):
                continue
            if spec["rule_type"] not in existing_types:
                self.create_rule(
                    name=spec["name"],
                    rule_type=spec["rule_type"],
                    config_json=spec["config_json"],
                    enabled=spec["enabled"],
                    schedule=spec["schedule"],
                )
            config_repo.save_config_entry(flag, "1")

    def _rule_to_dict(self, rule) -> dict:
        """Serialize a CleanupRule ORM object to a dict.

        Parses config_json from a JSON string into a dict and includes
        the schedule field along with all standard rule fields.
        """
        try:
            config = _json.loads(rule.config_json or "{}")
        except (ValueError, TypeError):
            config = {}
        return {
            "id": rule.id,
            "name": rule.name,
            "rule_type": rule.rule_type,
            "config_json": config,
            "enabled": bool(rule.enabled),
            "schedule": rule.schedule,
            "last_run_at": rule.last_run_at.isoformat() if rule.last_run_at else None,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat(),
        }

    def create_rule(
        self,
        name: str,
        rule_type: str,
        config_json: str = "{}",
        enabled: bool = True,
        schedule: str = "manual",
    ) -> dict:
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
            schedule=schedule,
            created_at=now,
            updated_at=now,
        )
        self.session.add(entry)
        self._commit()
        return self._rule_to_dict(entry)

    def get_rules(self) -> list[dict]:
        """Get all cleanup rules ordered by name.

        Returns:
            List of rule dicts.
        """
        stmt = select(CleanupRule).order_by(CleanupRule.name)
        entries = self.session.execute(stmt).scalars().all()
        return [self._rule_to_dict(e) for e in entries]

    def get_rule(self, rule_id: int) -> dict | None:
        """Get a single cleanup rule by ID.

        Returns:
            Dict or None if not found.
        """
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        result = self.session.execute(stmt).scalar_one_or_none()
        return self._rule_to_dict(result) if result is not None else None

    def update_rule(self, rule_id: int, **kwargs) -> dict | None:
        """Update a cleanup rule by ID.

        Accepts any combination of: name, rule_type, config_json, enabled, schedule.

        Returns:
            Updated dict or None if not found.
        """
        stmt = select(CleanupRule).where(CleanupRule.id == rule_id)
        entry = self.session.execute(stmt).scalar_one_or_none()
        if entry is None:
            return None

        allowed_fields = {"name", "rule_type", "config_json", "enabled", "schedule"}
        for key, value in kwargs.items():
            if key in allowed_fields:
                if key == "enabled":
                    value = 1 if value else 0
                setattr(entry, key, value)

        entry.updated_at = self._now()
        self._commit()
        return self._rule_to_dict(entry)

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

    def log_cleanup(
        self,
        action_type: str,
        files_processed: int = 0,
        files_deleted: int = 0,
        bytes_freed: int = 0,
        details_json: str = "{}",
        rule_id: int = None,
    ) -> dict:
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
        page = max(1, page)
        per_page = max(1, min(200, per_page))
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
        format_stmt = select(
            SubtitleHash.format,
            func.count().label("count"),
            func.coalesce(func.sum(SubtitleHash.file_size), 0).label("size"),
        ).group_by(SubtitleHash.format)
        format_rows = self.session.execute(format_stmt).all()
        by_format = {row[0]: {"count": row[1], "size": row[2]} for row in format_rows}

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

        dup_files_stmt = select(
            func.count().label("dup_count"),
            func.coalesce(func.sum(SubtitleHash.file_size), 0).label("dup_size"),
        ).join(dup_subquery, SubtitleHash.content_hash == dup_subquery.c.content_hash)
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
            sizes = sorted(f["file_size"] for f in g["files"])
            # Keep largest, remove rest
            potential_savings += sum(sizes[:-1])

        # Recent cleanup trend (last 30 days)
        trend_stmt = (
            select(
                cast(CleanupHistory.performed_at, Date).label("date"),
                func.coalesce(func.sum(CleanupHistory.bytes_freed), 0).label("freed"),
            )
            .where(CleanupHistory.performed_at > datetime.now(UTC) - timedelta(days=30))
            .group_by(cast(CleanupHistory.performed_at, Date))
            .order_by(cast(CleanupHistory.performed_at, Date))
        )
        trend_rows = self.session.execute(trend_stmt).all()
        recent_cleanups = [{"date": row[0], "bytes_freed": row[1]} for row in trend_rows]

        return {
            "total_files": hash_stats["total_files"],
            "total_size_bytes": hash_stats["total_size"],
            "by_format": by_format,
            "duplicate_count": duplicate_count,
            "duplicate_size_bytes": duplicate_size,
            "potential_savings_bytes": potential_savings,
            "recent_cleanups": recent_cleanups,
        }
