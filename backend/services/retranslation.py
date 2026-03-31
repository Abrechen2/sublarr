"""Service: re-queue a wanted item for translation."""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)


def retranslate_item(item_id: int) -> str | None:
    """Create a translation job for *item_id*. Returns job_id or None on error.

    Verifies the media file exists and is within the configured media path,
    removes any existing translated sidecar files, then starts a background
    translation thread.
    """
    from config import get_settings
    from db.jobs import create_job
    from db.wanted import get_wanted_item
    from events import emit_event
    from security_utils import is_safe_path

    item = get_wanted_item(item_id)
    if not item:
        return None

    file_path = item.get("file_path") or item.get("path")
    if not file_path or not os.path.exists(file_path):
        return None

    settings = get_settings()
    if not is_safe_path(file_path, settings.media_path):
        logger.warning("retranslate_item: path traversal rejected for item %s", item_id)
        return None

    # Remove existing translated sidecar files so re-translation starts clean
    base = os.path.splitext(file_path)[0]
    for fmt in ("ass", "srt"):
        for pattern in settings.get_target_patterns(fmt):
            target = base + pattern
            if os.path.exists(target):
                try:
                    os.remove(target)
                    logger.info("retranslate_item: removed existing sidecar %s", target)
                except OSError as exc:
                    logger.warning("retranslate_item: could not remove %s: %s", target, exc)

    new_job = create_job(file_path, force=True)

    from flask import current_app as _current_app

    _app = _current_app._get_current_object()

    def _run():
        from routes.translate import _run_job

        with _app.app_context():
            _run_job(new_job)
            emit_event(
                "translation_complete",
                {
                    "file_path": file_path,
                    "job_id": new_job["id"],
                },
            )

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return new_job["id"]
