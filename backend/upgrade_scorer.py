"""Upgrade scoring logic — decides if a new subtitle is worth replacing the existing one.

Scores existing subtitles based on format and file characteristics, then compares
with new candidates to determine if an upgrade should proceed.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

# Base scores by format (ASS is inherently better for anime due to styling)
FORMAT_BASE_SCORES = {
    "ass": 300,
    "ssa": 280,
    "srt": 150,
}

# File size thresholds for score adjustments (larger files tend to be higher quality)
SIZE_BONUS_THRESHOLDS = [
    (50_000, 20),   # >50KB: +20
    (100_000, 30),  # >100KB: +30
    (200_000, 40),  # >200KB: +40
]


def score_existing_subtitle(file_path: str) -> tuple[str, int]:
    """Score an existing subtitle file based on format and file characteristics.

    Returns:
        (format, score) tuple. Format is lowercase extension without dot.
    """
    if not os.path.exists(file_path):
        return ("", 0)

    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    base_score = FORMAT_BASE_SCORES.get(ext, 100)

    # Adjust based on file size
    try:
        size = os.path.getsize(file_path)
        for threshold, bonus in SIZE_BONUS_THRESHOLDS:
            if size >= threshold:
                base_score = FORMAT_BASE_SCORES.get(ext, 100) + bonus
    except OSError:
        pass

    return (ext, base_score)


def should_upgrade(
    current_fmt: str,
    current_score: int,
    new_fmt: str,
    new_score: int,
    upgrade_prefer_ass: bool = True,
    upgrade_min_score_delta: int = 50,
    upgrade_window_days: int = 7,
    existing_file_path: str = "",
) -> tuple[bool, str]:
    """Decide if a new subtitle is worth upgrading to.

    Rules:
    1. Never downgrade ASS -> SRT
    2. SRT -> ASS: Always upgrade if upgrade_prefer_ass is True
    3. Same format: Only upgrade if score delta >= upgrade_min_score_delta
    4. Recently downloaded subs (within upgrade_window_days) require 2x the delta

    Returns:
        (should_upgrade, reason) tuple.
    """
    # Rule 1: Never downgrade ASS to SRT
    if current_fmt == "ass" and new_fmt == "srt":
        return (False, "Would downgrade from ASS to SRT")

    # Rule 2: SRT -> ASS always upgrades if preferred
    if current_fmt == "srt" and new_fmt == "ass" and upgrade_prefer_ass:
        return (True, f"SRT->ASS format upgrade (score {current_score}->{new_score})")

    # Rule 4: Recently downloaded subs require higher delta
    effective_delta = upgrade_min_score_delta
    if existing_file_path and upgrade_window_days > 0:
        try:
            mtime = os.path.getmtime(existing_file_path)
            age_days = (time.time() - mtime) / 86400
            if age_days < upgrade_window_days:
                effective_delta = upgrade_min_score_delta * 2
                logger.debug(
                    "Sub is %.1f days old (window=%d), requiring 2x delta: %d",
                    age_days, upgrade_window_days, effective_delta,
                )
        except OSError:
            pass

    # Rule 3: Same format — need sufficient score delta
    delta = new_score - current_score
    if delta >= effective_delta:
        return (True, f"Score improvement +{delta} (>={effective_delta} threshold)")

    return (False, f"Score delta {delta} below threshold {effective_delta}")
