"""Record of subtitles restored after the pre-1.6.6 pipeline damaged them.

Repair rewrites the file, so afterwards its content no longer matches the
pristine hash in ``subtitle_hashes`` — which is exactly the signal the scanner
uses to spot damage. Without a record of what was already repaired, every
repaired file would look damaged again on the next scan and be re-fetched
forever, burning provider quota.

Storing the post-repair hash also means a file the user edits *after* a repair
is recognised as edited, not as damage.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from extensions import db


class SubtitleRepair(db.Model):
    """One sidecar restored from its provider original."""

    __tablename__ = "subtitle_repairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # The pristine hash the file was restored to — proof of what we put back.
    original_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # The hash of the file as repair left it, so a later hand edit is detectable.
    repaired_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=True)
    subtitle_id: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="repaired")
    repaired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_subtitle_repairs_status", "status"),)
