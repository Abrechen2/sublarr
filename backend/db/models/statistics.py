"""Statistics rollup model (V1.6 #9).

One row per calendar date (ISO ``YYYY-MM-DD``) holding pre-aggregated daily
counts so trend charts don't need expensive live ``GROUP BY date`` scans over
subtitle_downloads / translation_events / sync_job_runs. Written idempotently by
``services.stats_rollup`` (daily scheduler job + on-demand backfill).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class StatsDailyRollup(db.Model):
    __tablename__ = "stats_daily_rollup"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # "YYYY-MM-DD"
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    translations: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    syncs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    translation_chars: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    translation_cost_micro_usd: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    # JSON breakdowns: {dimension_value: count}
    by_source_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    by_provider_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    by_language_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
