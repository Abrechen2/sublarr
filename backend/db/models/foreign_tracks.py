"""ORM model for the foreign-track scan cache / worklist.

One row per video file. The table is both the verdict cache (so a rescan
costs a stat() instead of an ffprobe) and the worklist the batched sweep
draws from, which is what makes the sweep resumable after a restart.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db

STATE_PENDING = "pending"
STATE_CLEAN = "clean"
STATE_AFFECTED = "affected"
STATE_STRIPPING = "stripping"
STATE_STRIPPED = "stripped"
STATE_FAILED = "failed"

ERROR_PROBE = "probe"
ERROR_REMUX = "remux"
ERROR_VERIFY = "verify"
ERROR_IO = "io"

# A file may fail this often before it is parked in STATE_FAILED. The counter
# resets when the file changes on disk — a replaced file deserves a fresh try.
MAX_ATTEMPTS = 3


class ForeignTrackScan(db.Model):
    """Per-file scan state for the foreign-track sweep."""

    __tablename__ = "foreign_track_scan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mtime: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default=STATE_PENDING)
    foreign_langs: Mapped[str] = mapped_column(Text, nullable=True)
    track_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    probed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    error_class: Mapped[str] = mapped_column(String(16), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_foreign_track_scan_state_generation", "state", "generation"),
        Index("idx_foreign_track_scan_state_attempts", "state", "attempts"),
    )
