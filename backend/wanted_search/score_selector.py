"""Score comparison and upgrade selection helpers for wanted search.

Extracted from wanted_search/process.py — contains helpers for
evaluating whether a new subtitle result should replace an existing one.
"""

import logging
import os

from db.library import record_upgrade
from upgrade_scorer import should_upgrade

logger = logging.getLogger(__name__)


def evaluate_upgrade(
    item_id: int,
    file_path: str,
    is_upgrade: bool,
    current_score: int,
    new_score: int,
    new_format: str,
    existing_format: str,
    provider_name: str,
    settings,
) -> tuple[bool, str]:
    """Check whether a new subtitle result should replace the existing one.

    For non-upgrade candidates, always returns (True, "new item").
    For upgrade candidates, delegates to should_upgrade() using the configured
    upgrade policy settings.

    Returns:
        (approved, reason) — if approved is False, the caller should skip this result.
    """
    if not is_upgrade or current_score <= 0:
        return True, "new item"

    from translator import get_output_path_for_lang

    existing_srt = get_output_path_for_lang(file_path, existing_format, "")
    if getattr(settings, "upgrade_protect_user_modified", True):
        from db.quality import is_user_modified

        if is_user_modified(existing_srt):
            return False, "existing subtitle was hand-edited (user-modified guard)"
    do_upgrade, reason = should_upgrade(
        existing_format,
        current_score,
        new_format,
        new_score,
        upgrade_prefer_ass=settings.upgrade_prefer_ass,
        upgrade_min_score_delta=settings.upgrade_min_score_delta,
        upgrade_window_days=settings.upgrade_window_days,
        existing_file_path=existing_srt,
    )
    return do_upgrade, reason


def record_format_upgrade(
    file_path: str,
    old_format: str,
    old_score: int,
    new_format: str,
    new_score: int,
    provider_name: str,
) -> None:
    """Record a format upgrade (e.g. SRT -> ASS) in the upgrade audit table.

    Removes the old format file if it exists on disk.
    """
    from translator import get_output_path_for_lang

    old_path = get_output_path_for_lang(file_path, old_format, "")
    if old_path and os.path.exists(old_path):
        try:
            os.remove(old_path)
            logger.info("Removed old %s file during upgrade: %s", old_format.upper(), old_path)
        except OSError as e:
            logger.warning("Could not remove old %s file %s: %s", old_format.upper(), old_path, e)

    record_upgrade(
        file_path=file_path,
        old_format=old_format,
        old_score=old_score,
        new_format=new_format,
        new_score=new_score,
        provider_name=provider_name,
        upgrade_reason=f"{old_format.upper()}->{new_format.upper()} via {provider_name}",
    )
