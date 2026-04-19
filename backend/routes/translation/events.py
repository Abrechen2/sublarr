"""Translation admin API — cost + memory GET/purge endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from flask import Blueprint, jsonify, request

from db.models.translation import TranslationEvent
from extensions import db
from translation.cost_tracker import micro_usd_to_usd

logger = logging.getLogger(__name__)

bp = Blueprint("translation_admin", __name__, url_prefix="/api/v1/translation")


def _audit_log(action: str, **kwargs) -> None:
    """Log admin mutation for audit trail. First 6 chars of API key as actor."""
    api_key = request.headers.get("X-Api-Key", "")
    fp = api_key[:6] if api_key else "anon"
    extras = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(
        "translation_admin_action action=%s actor=%s %s",
        action,
        fp,
        extras,
    )


def _window_start(window: str) -> datetime:
    now = datetime.now(UTC)
    if window == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if window == "7d":
        return now - timedelta(days=7)
    if window == "30d":
        return now - timedelta(days=30)
    raise ValueError(f"unknown window: {window}")


def _aggregate(window_start: datetime) -> dict:
    """Total cost + events + cache-hits for events started >= window_start."""
    row = db.session.execute(
        sa.select(
            sa.func.coalesce(sa.func.sum(TranslationEvent.cost_estimate_micro_usd), 0),
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(sa.case((TranslationEvent.cache_hit, 1), else_=0)), 0),
        ).where(TranslationEvent.started_at >= window_start)
    ).one()
    total_micro, events, hits = row
    return {
        "cost_usd": float(micro_usd_to_usd(int(total_micro))),
        "events": int(events),
        "cache_hits": int(hits),
    }


@bp.route("/cost", methods=["GET"])
def cost_summary():
    today = _aggregate(_window_start("today"))
    d7 = _aggregate(_window_start("7d"))
    d30 = _aggregate(_window_start("30d"))
    return jsonify({"today": today, "last_7d": d7, "last_30d": d30}), 200


@bp.route("/cost/by-backend", methods=["GET"])
def cost_by_backend():
    window = request.args.get("window", "7d")
    try:
        start = _window_start(window)
    except ValueError as exc:
        return jsonify({"error": str(exc), "error_type": "ValueError"}), 400

    rows = db.session.execute(
        sa.select(
            TranslationEvent.backend,
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(TranslationEvent.cost_estimate_micro_usd), 0),
            sa.func.coalesce(sa.func.avg(TranslationEvent.latency_ms), 0),
            sa.func.coalesce(
                sa.func.sum(sa.case((TranslationEvent.status != "ok", 1), else_=0)),
                0,
            ),
        )
        .where(TranslationEvent.started_at >= start)
        .group_by(TranslationEvent.backend)
    ).all()

    backends = [
        {
            "backend": backend,
            "events": int(events),
            "cost_usd": float(micro_usd_to_usd(int(total))),
            "avg_latency_ms": float(avg_lat),
            "error_rate": (float(errors) / int(events)) if events else 0.0,
        }
        for backend, events, total, avg_lat, errors in rows
    ]
    return jsonify({"window": window, "backends": backends}), 200


@bp.route("/memory/stats", methods=["GET"])
def memory_stats():
    from sqlalchemy import text

    row = db.session.execute(
        text("SELECT COUNT(*), COALESCE(SUM(LENGTH(translated_text)), 0) FROM translation_memory")
    ).one()
    rows_count, size_bytes = row[0], row[1]

    cutoff = datetime.now(UTC) - timedelta(days=7)
    hit_row = db.session.execute(
        sa.select(
            sa.func.count(),
            sa.func.coalesce(sa.func.sum(sa.case((TranslationEvent.cache_hit, 1), else_=0)), 0),
        ).where(TranslationEvent.started_at >= cutoff)
    ).one()
    total_7d, hits_7d = int(hit_row[0]), int(hit_row[1])
    hit_rate = (hits_7d / total_7d) if total_7d else 0.0

    return (
        jsonify(
            {
                "rows": int(rows_count),
                "size_bytes": int(size_bytes),
                "hit_rate_7d": round(hit_rate, 4),
            }
        ),
        200,
    )


@bp.route("/memory/purge", methods=["POST"])
def memory_purge():
    body = request.get_json(silent=True) or {}
    older_than_days = body.get("older_than_days")

    from sqlalchemy import text

    conditions = []
    params = {}
    if older_than_days is not None:
        try:
            days = int(older_than_days)
        except (TypeError, ValueError):
            return (
                jsonify(
                    {
                        "error": "older_than_days must be int",
                        "error_type": "ValidationError",
                    }
                ),
                400,
            )
        cutoff = datetime.now(UTC) - timedelta(days=days)
        conditions.append("created_at < :cutoff")
        params["cutoff"] = cutoff

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    result = db.session.execute(text(f"DELETE FROM translation_memory {where}"), params)
    db.session.commit()
    deleted = result.rowcount or 0

    _audit_log(
        "purge-memory",
        older_than_days=older_than_days,
        deleted=deleted,
    )
    return jsonify({"status": "purged", "deleted": deleted}), 202
