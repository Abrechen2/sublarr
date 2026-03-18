"""System statistics routes — /stats, /statistics, /statistics/export."""

import csv
import io
import json
import logging
import time
from datetime import UTC, datetime

from flask import jsonify, request, send_file
from sqlalchemy import text

from routes.system import bp

logger = logging.getLogger(__name__)


@bp.route("/stats", methods=["GET"])
def get_stats():
    """Get overall statistics.
    ---
    get:
      tags:
        - System
      summary: Get runtime statistics
      description: Returns translation stats, pending jobs, uptime, and batch status.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Statistics summary
          content:
            application/json:
              schema:
                type: object
                properties:
                  total_jobs:
                    type: integer
                  completed_jobs:
                    type: integer
                  pending_jobs:
                    type: integer
                  uptime_seconds:
                    type: integer
                  batch_running:
                    type: boolean
                  upgrades:
                    type: object
                  quality_warnings:
                    type: integer
    """
    from db.jobs import get_pending_job_count, get_stats_summary
    from routes.batch_state import _memory_stats, batch_lock, batch_state, stats_lock

    db_stats = get_stats_summary()

    with stats_lock:
        uptime = time.time() - _memory_stats["started_at"]
        memory_extras = {
            "upgrades": dict(_memory_stats["upgrades"]),
            "quality_warnings": _memory_stats["quality_warnings"],
        }

    pending = get_pending_job_count()

    with batch_lock:
        is_batch_running = batch_state.get("running", False)

    return jsonify(
        {
            **db_stats,
            **memory_extras,
            "pending_jobs": pending,
            "uptime_seconds": round(uptime),
            "batch_running": is_batch_running,
        }
    )


@bp.route("/statistics", methods=["GET"])
def get_statistics():
    """Get comprehensive statistics with time range filter.
    ---
    get:
      tags:
        - System
      summary: Get comprehensive statistics
      description: Returns daily stats, provider stats, download counts, backend stats, upgrades, and format breakdown.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: range
          schema:
            type: string
            enum: ["7d", "30d", "90d", "365d"]
            default: "30d"
          description: Time range for statistics
      responses:
        200:
          description: Statistics data
          content:
            application/json:
              schema:
                type: object
                properties:
                  daily:
                    type: array
                    items:
                      type: object
                  providers:
                    type: object
                    additionalProperties: true
                  downloads_by_provider:
                    type: array
                    items:
                      type: object
                  backend_stats:
                    type: array
                    items:
                      type: object
                  upgrades:
                    type: array
                    items:
                      type: object
                  by_format:
                    type: object
                    additionalProperties:
                      type: integer
                  range:
                    type: string
    """
    from db import get_db
    from db.providers import get_provider_stats

    range_param = request.args.get("range", "30d")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    db = get_db()

    # Daily stats
    daily_rows = db.execute(
        text("SELECT * FROM daily_stats ORDER BY date DESC LIMIT :days"), {"days": days}
    ).fetchall()
    daily = []
    by_format_totals: dict = {}
    for row in daily_rows:
        d = row._mapping
        daily.append(
            {
                "date": d["date"],
                "translated": d["translated"],
                "failed": d["failed"],
                "skipped": d["skipped"],
            }
        )
        # Aggregate per-format totals across all days
        fmt_json = d.get("by_format_json", '{"ass": 0, "srt": 0}')
        try:
            fmt = json.loads(fmt_json) if isinstance(fmt_json, str) else {}
        except (json.JSONDecodeError, TypeError):
            fmt = {}
        for k, v in fmt.items():
            by_format_totals[k] = by_format_totals.get(k, 0) + (v or 0)

    # Provider stats (all providers)
    providers = get_provider_stats()

    # Downloads by provider
    dl_rows = db.execute(
        text("""SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
           FROM subtitle_downloads GROUP BY provider_name""")
    ).fetchall()
    downloads_by_provider = [
        {"provider_name": row[0], "count": row[1], "avg_score": round(row[2] or 0, 1)}
        for row in dl_rows
    ]

    # Translation backend stats
    backend_rows = db.execute(text("SELECT * FROM translation_backend_stats")).fetchall()
    backend_stats = [dict(row._mapping) for row in backend_rows]

    # Upgrade history summary
    upgrade_rows = db.execute(
        text("""SELECT old_format || ' -> ' || new_format as upgrade_type, COUNT(*) as count
           FROM upgrade_history GROUP BY upgrade_type""")
    ).fetchall()
    upgrades = [{"type": row[0], "count": row[1]} for row in upgrade_rows]

    # Quality trend: daily avg score from subtitle_downloads (normalized 0-100)
    _SCORE_MAX = 900.0
    qt_rows = db.execute(
        text("""
            SELECT substr(downloaded_at, 1, 10) as date,
                   AVG(COALESCE(score, 0)) as avg_score,
                   COUNT(*) as files_checked,
                   SUM(CASE WHEN COALESCE(score, 0) < 100 THEN 1 ELSE 0 END) as issues_count
            FROM subtitle_downloads
            WHERE downloaded_at >= date('now', :offset)
            GROUP BY substr(downloaded_at, 1, 10)
            ORDER BY date ASC
        """),
        {"offset": f"-{days} days"},
    ).fetchall()
    quality_trend = [
        {
            "date": row[0],
            "avg_score": round(min(100.0, (row[1] or 0) / _SCORE_MAX * 100), 1),
            "files_checked": row[2] or 0,
            "issues_count": row[3] or 0,
        }
        for row in qt_rows
    ]

    # Series quality: per-series avg score and format breakdown from subtitle_downloads
    sq_rows = db.execute(
        text("""
            SELECT wi.title,
                   AVG(COALESCE(sd.score, 0)) as avg_score,
                   COUNT(*) as download_count,
                   MAX(sd.downloaded_at) as last_download,
                   GROUP_CONCAT(DISTINCT sd.format) as formats
            FROM subtitle_downloads sd
            JOIN wanted_items wi ON sd.file_path = wi.file_path
            WHERE wi.title != ''
            GROUP BY wi.title
            ORDER BY download_count DESC
            LIMIT 20
        """)
    ).fetchall()
    series_quality = [
        {
            "title": row[0],
            "avg_score": round(row[1] or 0, 1),
            "avg_score_pct": round(min(100.0, (row[1] or 0) / _SCORE_MAX * 100), 1),
            "download_count": row[2] or 0,
            "last_download": row[3],
            "formats": [f for f in (row[4] or "").split(",") if f],
        }
        for row in sq_rows
    ]

    return jsonify(
        {
            "daily": daily,
            "providers": providers,
            "downloads_by_provider": downloads_by_provider,
            "backend_stats": backend_stats,
            "upgrades": upgrades,
            "by_format": by_format_totals,
            "quality_trend": quality_trend,
            "series_quality": series_quality,
            "range": range_param,
        }
    )


@bp.route("/statistics/export", methods=["GET"])
def export_statistics():
    """Export statistics as JSON or CSV file download.
    ---
    get:
      tags:
        - System
      summary: Export statistics
      description: Downloads statistics as JSON or CSV file for the specified time range.
      security:
        - apiKeyAuth: []
      parameters:
        - in: query
          name: range
          schema:
            type: string
            enum: ["7d", "30d", "90d", "365d"]
            default: "30d"
          description: Time range for export
        - in: query
          name: format
          schema:
            type: string
            enum: [json, csv]
            default: json
          description: Export file format
      responses:
        200:
          description: File download
          content:
            application/json:
              schema:
                type: string
                format: binary
            text/csv:
              schema:
                type: string
                format: binary
    """
    from db import get_db
    from db.providers import get_provider_stats

    range_param = request.args.get("range", "30d")
    export_format = request.args.get("format", "json")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    db = get_db()

    # Fetch daily stats
    daily_rows = db.execute(
        text("SELECT * FROM daily_stats ORDER BY date DESC LIMIT :days"), {"days": days}
    ).fetchall()
    daily = []
    for row in daily_rows:
        d = row._mapping
        daily.append(
            {
                "date": d["date"],
                "translated": d["translated"],
                "failed": d["failed"],
                "skipped": d["skipped"],
            }
        )

    today = datetime.now(UTC).strftime("%Y%m%d")

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["date", "translated", "failed", "skipped"])
        for row in daily:
            writer.writerow([row["date"], row["translated"], row["failed"], row["skipped"]])

        csv_bytes = output.getvalue().encode("utf-8")
        buf = io.BytesIO(csv_bytes)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"sublarr_stats_{today}.csv",
        )
    else:
        # JSON export with full data
        providers = get_provider_stats()
        dl_rows = db.execute(
            text("""SELECT provider_name, COUNT(*) as count, AVG(score) as avg_score
               FROM subtitle_downloads GROUP BY provider_name""")
        ).fetchall()
        downloads_by_provider = [
            {"provider": row[0], "count": row[1], "avg_score": round(row[2] or 0, 1)}
            for row in dl_rows
        ]

        stats_data = {
            "daily": daily,
            "providers": providers,
            "downloads_by_provider": downloads_by_provider,
            "range": range_param,
            "exported_at": datetime.now(UTC).isoformat(),
        }

        json_bytes = json.dumps(stats_data, indent=2).encode("utf-8")
        buf = io.BytesIO(json_bytes)
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"sublarr_stats_{today}.json",
        )
