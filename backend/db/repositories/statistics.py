"""Repository for statistics queries."""

from __future__ import annotations

import json

from sqlalchemy import text

from db.repositories.base import BaseRepository

_SCORE_MAX = 900.0


def _iso_timestamp(value) -> str | None:
    """Normalise a timestamp column to an ISO string.

    SQLite returns a text value; Postgres returns a ``datetime``. Handle both so
    the response shape is stable regardless of backend.
    """
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value).replace(" ", "T")


class StatisticsRepository(BaseRepository):
    def get_daily_stats(self, days: int = 30) -> tuple[list[dict], dict]:
        """Return daily stats rows and aggregated by-format totals.

        Returns (daily_list, by_format_totals).
        """
        rows = self.session.execute(
            text("SELECT * FROM daily_stats ORDER BY date DESC LIMIT :days"),
            {"days": days},
        ).fetchall()

        daily = []
        by_format_totals: dict = {}
        for row in rows:
            d = row._mapping
            daily.append(
                {
                    "date": d["date"],
                    "translated": d["translated"],
                    "failed": d["failed"],
                    "skipped": d["skipped"],
                }
            )
            fmt_json = d.get("by_format_json", '{"ass": 0, "srt": 0}')
            try:
                fmt = json.loads(fmt_json) if isinstance(fmt_json, str) else {}
            except (json.JSONDecodeError, TypeError):
                fmt = {}
            for k, v in fmt.items():
                by_format_totals[k] = by_format_totals.get(k, 0) + (v or 0)

        return daily, by_format_totals

    def get_downloads_by_provider(self) -> list[dict]:
        """Return subtitle download counts and average score per provider."""
        rows = self.session.execute(
            text(
                "SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score"
                " FROM subtitle_downloads GROUP BY provider_name"
            )
        ).fetchall()
        return [
            {"provider_name": row[0], "count": row[1], "avg_score": round(float(row[2] or 0), 1)}
            for row in rows
        ]

    def get_translation_backend_stats(self) -> list[dict]:
        """Return all translation_backend_stats rows."""
        rows = self.session.execute(text("SELECT * FROM translation_backend_stats")).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_upgrade_type_summary(self) -> list[dict]:
        """Return upgrade counts grouped by format-transition type."""
        rows = self.session.execute(
            text(
                "SELECT old_format || ' -> ' || new_format as upgrade_type, COUNT(*) as count"
                " FROM upgrade_history GROUP BY upgrade_type"
            )
        ).fetchall()
        return [{"type": row[0], "count": row[1]} for row in rows]

    def get_quality_trend(self, days: int = 30) -> list[dict]:
        """Return daily quality metrics from subtitle_downloads for the last *days* days."""
        from datetime import UTC, datetime, timedelta

        # Portable across SQLite + Postgres: SQLite's substr()/date('now', …) do
        # not exist on Postgres (substr(timestamptz, …) → UndefinedFunction).
        # Cast the timestamp to text first, then slice the YYYY-MM-DD prefix, and
        # bind a Python-computed cutoff date instead of date('now', …).
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.session.execute(
            text("""
                SELECT substr(CAST(downloaded_at AS TEXT), 1, 10) as day,
                       AVG(COALESCE(score, 0)) as avg_score,
                       COUNT(*) as files_checked,
                       SUM(CASE WHEN COALESCE(score, 0) < 100 THEN 1 ELSE 0 END) as issues_count
                FROM subtitle_downloads
                WHERE substr(CAST(downloaded_at AS TEXT), 1, 10) >= :cutoff
                GROUP BY substr(CAST(downloaded_at AS TEXT), 1, 10)
                ORDER BY day ASC
            """),
            {"cutoff": cutoff},
        ).fetchall()
        return [
            {
                "date": row[0],
                "avg_score": round(min(100.0, float(row[1] or 0) / _SCORE_MAX * 100), 1),
                "files_checked": row[2] or 0,
                "issues_count": row[3] or 0,
            }
            for row in rows
        ]

    def get_series_quality(self) -> list[dict]:
        """Return per-series quality summary (top 20 by download count)."""
        # SQLite aggregates a distinct list with GROUP_CONCAT; Postgres uses
        # string_agg (GROUP_CONCAT does not exist there). Pick per dialect.
        dialect = self.session.get_bind().dialect.name
        fmt_agg = (
            "string_agg(DISTINCT sd.format, ',')"
            if dialect == "postgresql"
            else "GROUP_CONCAT(DISTINCT sd.format)"
        )
        rows = self.session.execute(
            text(f"""
                SELECT wi.title,
                       AVG(COALESCE(sd.score, 0)) as avg_score,
                       COUNT(*) as download_count,
                       MAX(sd.downloaded_at) as last_download,
                       {fmt_agg} as formats
                FROM subtitle_downloads sd
                JOIN wanted_items wi ON sd.file_path = wi.file_path
                WHERE wi.title != ''
                GROUP BY wi.title
                ORDER BY download_count DESC
                LIMIT 20
            """)
        ).fetchall()
        return [
            {
                "title": row[0],
                "avg_score": round(float(row[1] or 0), 1),
                "avg_score_pct": round(min(100.0, float(row[1] or 0) / _SCORE_MAX * 100), 1),
                "download_count": row[2] or 0,
                # MAX(downloaded_at) is a str on SQLite but a datetime on Postgres.
                "last_download": _iso_timestamp(row[3]),
                "formats": [f for f in (row[4] or "").split(",") if f],
            }
            for row in rows
        ]
