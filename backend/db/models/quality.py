"""Quality/health-check ORM model for subtitle health results.

Stores per-file health check results including quality score,
issues JSON, and check metadata for trend tracking.
"""

from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class SubtitleHealthResult(db.Model):
    """Stores health-check results for a subtitle file."""

    __tablename__ = "subtitle_health_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    issues_json: Mapped[str] = mapped_column(Text, default="[]")
    checks_run: Mapped[int] = mapped_column(Integer, default=0)
    checked_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_health_results_path", "file_path"),
        Index("idx_health_results_score", "score"),
    )
