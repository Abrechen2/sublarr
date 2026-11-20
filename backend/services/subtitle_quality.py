"""Accepting the quality of a subtitle that scored low (#255).

The decision is stored on the file's subtitle_downloads rows, where the score
that triggers the low-score warning lives; the score itself stays unchanged.
A download recorded later starts unaccepted, so a new subtitle is judged
again. Wanted rows of the accepted languages are set to 'ignored' so no
upgrade search runs for them.
"""

import logging

from sqlalchemy import select, update

from db import get_db
from db.models.providers import SubtitleDownload
from db.wanted import get_wanted_items_by_path, update_wanted_status

logger = logging.getLogger(__name__)


def accept_subtitle_quality(file_path: str, language: str | None = None) -> dict:
    """Mark the subtitles of ``file_path`` (one ``language`` or all) as accepted."""
    session = get_db()
    rows = [SubtitleDownload.file_path == file_path, SubtitleDownload.format != ""]
    if language:
        rows.append(SubtitleDownload.language == language)
    accepted_langs = set(
        session.execute(select(SubtitleDownload.language).where(*rows).distinct()).scalars()
    )
    session.execute(update(SubtitleDownload).where(*rows).values(quality_accepted=1))
    session.commit()

    langs = {language} if language else accepted_langs
    ignored = 0
    for item in get_wanted_items_by_path(file_path):
        if item.get("target_language") in langs and item.get("status") != "ignored":
            update_wanted_status(item["id"], "ignored")
            ignored += 1

    logger.info(
        "Subtitle quality accepted for %s (%s): %d languages, %d wanted rows ignored",
        file_path,
        language or "all languages",
        len(accepted_langs),
        ignored,
    )
    return {"accepted": len(accepted_langs), "ignored": ignored}
