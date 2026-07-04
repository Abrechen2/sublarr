"""System statistics routes — /stats, /statistics, /statistics/export."""

import csv
import io
import json
import logging
import time
from datetime import UTC, datetime

from flask import jsonify, request, send_file

from cache_response import cached_get
from routes.system import bp

logger = logging.getLogger(__name__)

_VALID_RANGES = ("24h", "7d", "30d", "all")


def _range_param() -> str:
    r = (request.args.get("range") or "30d").strip().lower()
    return r if r in _VALID_RANGES else "30d"


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
    from db.providers import get_provider_stats
    from db.statistics import (
        get_daily_stats,
        get_downloads_by_provider,
        get_quality_trend,
        get_series_quality,
        get_translation_backend_stats,
        get_upgrade_type_summary,
    )

    range_param = request.args.get("range", "30d")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    daily, by_format_totals = get_daily_stats(days)
    providers = get_provider_stats()
    downloads_by_provider = get_downloads_by_provider()
    backend_stats = get_translation_backend_stats()
    upgrades = get_upgrade_type_summary()
    quality_trend = get_quality_trend(days)
    series_quality = get_series_quality()

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
    from db.providers import get_provider_stats
    from db.statistics import get_daily_stats, get_downloads_by_provider

    range_param = request.args.get("range", "30d")
    export_format = request.args.get("format", "json")
    range_map = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
    days = range_map.get(range_param, 30)

    daily, _ = get_daily_stats(days)
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
        raw_dl = get_downloads_by_provider()
        # Export uses "provider" key (legacy field name for exports)
        downloads_by_provider = [
            {"provider": d["provider_name"], "count": d["count"], "avg_score": d["avg_score"]}
            for d in raw_dl
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


# ── V1.6 #9: grouped analytics endpoints (/api/v1/statistics/<group>) ─────────
# Snapshot groups query live tables (cached ~5 min); trends reads the daily
# rollup. Documented as anonymous-readable analytics like the legacy /statistics.


@bp.route("/statistics/subtitles", methods=["GET"])
@cached_get(ttl_seconds=300)
def statistics_subtitles():
    from services.statistics_service import get_subtitles_stats

    return jsonify(get_subtitles_stats(_range_param()))


@bp.route("/statistics/translation", methods=["GET"])
@cached_get(ttl_seconds=300)
def statistics_translation():
    from services.statistics_service import get_translation_stats

    return jsonify(get_translation_stats(_range_param()))


@bp.route("/statistics/providers", methods=["GET"])
@cached_get(ttl_seconds=300)
def statistics_providers():
    from services.statistics_service import get_providers_stats

    return jsonify(get_providers_stats())


@bp.route("/statistics/system", methods=["GET"])
@cached_get(ttl_seconds=60)
def statistics_system():
    from services.statistics_service import get_system_stats

    return jsonify(get_system_stats())


@bp.route("/statistics/library", methods=["GET"])
@cached_get(ttl_seconds=300)
def statistics_library():
    from services.statistics_service import get_library_stats

    return jsonify(get_library_stats())


@bp.route("/statistics/trends", methods=["GET"])
@cached_get(ttl_seconds=300)
def statistics_trends():
    from services.statistics_service import get_trends

    return jsonify(get_trends(_range_param()))
