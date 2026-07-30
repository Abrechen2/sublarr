"""Download history and upgrade tracking repository using SQLAlchemy ORM.

Replaces the raw sqlite3 queries in db/library.py with SQLAlchemy ORM
operations. Return types match the existing functions exactly.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import asc, desc, func, or_, select

from db.models.core import UpgradeHistory
from db.models.providers import SubtitleDownload
from db.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class LibraryRepository(BaseRepository):
    """Repository for subtitle_downloads and upgrade_history table operations."""

    # Sort field allowlist for get_download_history
    _HISTORY_SORT_FIELDS = {
        "downloaded_at": SubtitleDownload.downloaded_at,
        "score": SubtitleDownload.score,
        "provider_name": SubtitleDownload.provider_name,
        "language": SubtitleDownload.language,
    }

    # ---- Download History ----------------------------------------------------

    def get_download_history(
        self,
        page: int = 1,
        per_page: int = 50,
        provider: str = None,
        language: str = None,
        format: str = None,
        score_min: int = None,
        score_max: int = None,
        search: str = None,
        sort_by: str = "downloaded_at",
        sort_dir: str = "desc",
    ) -> dict:
        """Get paginated download history with optional filters.

        Returns:
            Dict with 'data', 'page', 'per_page', 'total', 'total_pages' keys.
        """
        page = max(1, page)
        per_page = max(1, min(200, per_page))
        offset = (page - 1) * per_page

        # Build filter conditions
        conditions = []
        if provider:
            conditions.append(SubtitleDownload.provider_name == provider)
        if language:
            conditions.append(SubtitleDownload.language == language)
        if format:
            conditions.append(SubtitleDownload.format == format)
        if score_min is not None:
            conditions.append(SubtitleDownload.score >= score_min)
        if score_max is not None:
            conditions.append(SubtitleDownload.score <= score_max)

        # Text search on file_path and provider_name
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    SubtitleDownload.file_path.ilike(search_term),
                    SubtitleDownload.provider_name.ilike(search_term),
                )
            )

        # Count query
        count_stmt = select(func.count()).select_from(SubtitleDownload)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        count = self.session.execute(count_stmt).scalar() or 0

        # Determine sort column and direction
        sort_col = self._HISTORY_SORT_FIELDS.get(sort_by, SubtitleDownload.downloaded_at)
        order = asc(sort_col) if sort_dir == "asc" else desc(sort_col)

        # Data query
        data_stmt = select(SubtitleDownload).order_by(order).limit(per_page).offset(offset)
        for cond in conditions:
            data_stmt = data_stmt.where(cond)
        entries = self.session.execute(data_stmt).scalars().all()

        data = [self._to_dict(e) for e in entries]

        # Enrich upgrade rows with the replaced download's score/format so the
        # UI can show WHY the entry exists ("Upgrade +40" vs. plain download)
        # without a per-row lookup. One batch query for the whole page.
        prev_ids = {e.upgraded_from_id for e in entries if e.upgraded_from_id}
        prev_map: dict[int, tuple] = {}
        if prev_ids:
            prev_rows = self.session.execute(
                select(
                    SubtitleDownload.id,
                    SubtitleDownload.score,
                    SubtitleDownload.format,
                ).where(SubtitleDownload.id.in_(prev_ids))
            ).all()
            prev_map = {row[0]: (row[1], row[2]) for row in prev_rows}
        for row in data:
            prev = prev_map.get(row.get("upgraded_from_id"))
            row["previous_score"] = prev[0] if prev else None
            row["previous_format"] = prev[1] if prev else None

        total_pages = max(1, (count + per_page - 1) // per_page)
        data = [self._history_entry_to_dict(e) for e in entries]
        self._annotate_sync_status(data)
        return {
            "data": data,
            "page": page,
            "per_page": per_page,
            "total": count,
            "total_pages": total_pages,
        }

    def get_download_by_id(self, download_id: int) -> dict | None:
        """Return one subtitle_downloads row as a dict, or None."""
        entry = self.session.get(SubtitleDownload, download_id)
        return self._to_dict(entry) if entry else None


    def _annotate_sync_status(self, rows: list[dict]) -> None:
        """Attach synced/sync_engine/synced_at to history rows in one query.

        The sidecar path is derived the same way the frontend does for
        preview: <media base>.<language>.<format>. Rows whose derived path
        has at least one successful sync_job_runs entry are marked synced.
        Failures here must never break the history endpoint.
        """
        try:
            from db.models.core import SyncJobRun

            path_by_row: dict[int, str] = {}
            for i, row in enumerate(rows):
                fp, lang, fmt = row.get("file_path"), row.get("language"), row.get("format")
                if not (fp and lang and fmt):
                    row["synced"] = False
                    continue
                base = fp.rsplit(".", 1)[0] if "." in fp else fp
                path_by_row[i] = f"{base}.{lang}.{fmt}"
                row["synced"] = False

            if not path_by_row:
                return

            sync_rows = self.session.execute(
                select(
                    SyncJobRun.subtitle_path,
                    SyncJobRun.engine,
                    func.max(SyncJobRun.created_at),
                )
                .where(
                    SyncJobRun.status == "ok",
                    SyncJobRun.subtitle_path.in_(set(path_by_row.values())),
                )
                .group_by(SyncJobRun.subtitle_path, SyncJobRun.engine)
            ).all()

            latest: dict[str, tuple] = {}
            for sub_path, engine, created in sync_rows:
                ts = created.isoformat() if isinstance(created, datetime) else created
                if sub_path not in latest or (ts and ts > latest[sub_path][1]):
                    latest[sub_path] = (engine, ts)

            for i, sub_path in path_by_row.items():
                hit = latest.get(sub_path)
                if hit:
                    rows[i]["synced"] = True
                    rows[i]["sync_engine"] = hit[0]
                    rows[i]["synced_at"] = hit[1]
        except Exception:
            logger.debug("Could not annotate sync status on history rows", exc_info=True)

    def _history_entry_to_dict(self, entry) -> dict:
        """Serialize a SubtitleDownload row, decoding score_breakdown JSON.

        The column stores a JSON string; the API contract is a dict (or None
        for legacy rows / unparseable data) so the frontend never has to
        JSON.parse itself.
        """
        import json

        d = self._to_dict(entry)
        raw = d.get("score_breakdown")
        if raw:
            try:
                parsed = json.loads(raw)
                d["score_breakdown"] = parsed if isinstance(parsed, dict) else None
            except (TypeError, ValueError):
                d["score_breakdown"] = None
        else:
            d["score_breakdown"] = None
        return d

    def get_download_stats(self) -> dict:
        """Get aggregated download statistics.

        Returns:
            Dict with total_downloads, by_provider, by_format, by_language,
            last_24h, last_7d keys.
        """
        total = (
            self.session.execute(select(func.count()).select_from(SubtitleDownload)).scalar() or 0
        )

        # By provider
        by_provider_rows = self.session.execute(
            select(SubtitleDownload.provider_name, func.count()).group_by(
                SubtitleDownload.provider_name
            )
        ).all()
        by_provider = {row[0]: row[1] for row in by_provider_rows}

        # By format
        by_format_rows = self.session.execute(
            select(SubtitleDownload.format, func.count()).group_by(SubtitleDownload.format)
        ).all()
        by_format = {(row[0] or "unknown"): row[1] for row in by_format_rows}

        # By language
        by_language_rows = self.session.execute(
            select(SubtitleDownload.language, func.count()).group_by(SubtitleDownload.language)
        ).all()
        by_language = {(row[0] or "unknown"): row[1] for row in by_language_rows}

        # Last 24h and 7d
        now = datetime.now(UTC)
        last_24h = (
            self.session.execute(
                select(func.count())
                .select_from(SubtitleDownload)
                .where(SubtitleDownload.downloaded_at > now - timedelta(days=1))
            ).scalar()
            or 0
        )

        last_7d = (
            self.session.execute(
                select(func.count())
                .select_from(SubtitleDownload)
                .where(SubtitleDownload.downloaded_at > now - timedelta(days=7))
            ).scalar()
            or 0
        )

        return {
            "total_downloads": total,
            "by_provider": by_provider,
            "by_format": by_format,
            "by_language": by_language,
            "last_24h": last_24h,
            "last_7d": last_7d,
        }

    # ---- Upgrade History -----------------------------------------------------

    def record_upgrade(
        self,
        file_path: str,
        old_format: str,
        old_score: int,
        new_format: str,
        new_score: int,
        provider_name: str = "",
        upgrade_reason: str = "",
    ):
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
        stmt = select(UpgradeHistory).order_by(UpgradeHistory.upgraded_at.desc()).limit(limit)
        entries = self.session.execute(stmt).scalars().all()
        return [self._to_dict(e) for e in entries]

    def get_upgrade_stats(self) -> dict:
        """Get aggregated upgrade statistics.

        Returns:
            Dict with 'total' and 'srt_to_ass' counts.
        """
        total = self.session.execute(select(func.count()).select_from(UpgradeHistory)).scalar() or 0

        srt_to_ass = (
            self.session.execute(
                select(func.count())
                .select_from(UpgradeHistory)
                .where(
                    UpgradeHistory.old_format == "srt",
                    UpgradeHistory.new_format == "ass",
                )
            ).scalar()
            or 0
        )

        return {"total": total, "srt_to_ass": srt_to_ass}

    def delete_download_record(self, file_path: str) -> None:
        """Delete subtitle_downloads entry for the given file path."""
        self.session.query(SubtitleDownload).filter_by(file_path=file_path).delete()
        self.session.commit()
