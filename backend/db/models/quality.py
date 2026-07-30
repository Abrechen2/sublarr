"""Quality/health-check ORM model for subtitle health results.

Stores per-file health check results including quality score,
issues JSON, and check metadata for trend tracking.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
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
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_health_results_path", "file_path"),
        Index("idx_health_results_score", "score"),
    )


class UserModifiedSubtitle(db.Model):
    """Marks a subtitle file as hand-edited (saved from the editor).

    The upgrade automation refuses to replace marked files while the
    ``upgrade_protect_user_modified`` setting is enabled, so manual timing
    work is never silently overwritten by a "better" provider download.
    The marker is cleared when the file is deliberately replaced.
    """

    __tablename__ = "user_modified_subtitles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="editor")

    __table_args__ = (Index("idx_user_modified_path", "file_path", unique=True),)


class AIQualityResult(db.Model):
    """Advisory LLM language-quality verdict for a subtitle sidecar file.

    One row per (sidecar path) — re-analysis replaces the previous row.
    Purely advisory: nothing in the pipeline reads this to make decisions.
    """

    __tablename__ = "ai_quality_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Path of the subtitle sidecar that was sampled (not the video file).
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, default="")
    # "green" | "yellow" | "red" — derived deterministically from the scores.
    verdict: Mapped[str] = mapped_column(Text, nullable=False, default="green")
    # {"machine_translation": 0-3, "ocr_artifacts": 0-3, "grammar": 0-3,
    #  "encoding_damage": 0-3} — higher is worse.
    scores_json: Mapped[str] = mapped_column(Text, default="{}")
    # Short free-text findings from the model (capped list of strings).
    reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    model: Mapped[str] = mapped_column(Text, default="")
    sampled_cues: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_ai_quality_path", "file_path"),)
