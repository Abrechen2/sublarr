"""Multi-signal forced/signs subtitle detection engine.

Detects whether a subtitle stream or file is a forced/signs subtitle
using multiple signals: ffprobe disposition, filename patterns, stream
title keywords, and ASS style analysis. Returns a type and confidence
score for reliable classification.
"""

import logging
import os
import re
from collections import Counter

logger = logging.getLogger(__name__)

# Valid subtitle type enum values
SUBTITLE_TYPES = ("full", "forced", "signs")

# Standard forced/signs filename patterns (Plex/Jellyfin/Emby/Kodi compatible)
FORCED_FILENAME_RE = re.compile(
    r'\.(?:forced|signs?|foreign)\.(?:ass|srt|ssa|vtt)$',
    re.IGNORECASE,
)

# Stream title keywords indicating forced/signs content
FORCED_STREAM_TITLE_RE = re.compile(
    r'\b(?:forced|signs?|songs?|foreign)\b',
    re.IGNORECASE,
)


def detect_subtitle_type(stream_info=None, file_path=None, ass_content=None):
    """Detect whether a subtitle is full, forced, or signs using multiple signals.

    Signals are checked in priority order:
      1. ffprobe disposition.forced == 1 -> ("forced", 1.0)
      2. Filename pattern (.forced. / .signs. / .foreign.) -> ("forced"|"signs", 0.9)
      3. Stream title keywords -> ("forced"|"signs", 0.8)
      4. ASS all-signs heuristic (classify_styles) -> ("signs", 0.7)
      5. No signals -> ("full", 1.0)

    Multi-signal agreement: if 2+ signals agree on type, return that type
    with the highest confidence among agreeing signals.

    Args:
        stream_info: Dict from ffprobe with disposition and tags (optional).
        file_path: Path to subtitle file for filename-based detection (optional).
        ass_content: pysubs2.SSAFile object for ASS style analysis (optional).

    Returns:
        tuple: (subtitle_type: str, confidence: float)
    """
    signals = []

    # Signal 1: ffprobe disposition (highest confidence)
    if stream_info:
        disposition = stream_info.get("disposition", {})
        if isinstance(disposition, dict) and disposition.get("forced", 0) == 1:
            signals.append(("forced", 1.0))

    # Signal 2: Filename pattern
    if file_path:
        name_lower = os.path.basename(file_path).lower()
        if ".forced." in name_lower or ".foreign." in name_lower:
            signals.append(("forced", 0.9))
        if ".signs." in name_lower or ".sign." in name_lower:
            signals.append(("signs", 0.9))

    # Signal 3: Stream title keywords
    if stream_info:
        title = ""
        tags = stream_info.get("tags", {})
        if isinstance(tags, dict):
            title = (tags.get("title", "") or "").lower()
        if title:
            if "forced" in title or "foreign" in title:
                signals.append(("forced", 0.8))
            if "sign" in title or "song" in title:
                signals.append(("signs", 0.8))

    # Signal 4: ASS all-signs heuristic (lazy import to avoid circular deps)
    if ass_content is not None:
        try:
            from ass_utils import classify_styles
            dialog_styles, signs_styles = classify_styles(ass_content)
            if signs_styles and not dialog_styles:
                signals.append(("signs", 0.7))
        except Exception as e:
            logger.debug("ASS style classification failed: %s", e)

    # No signals -> full subtitle
    if not signals:
        return ("full", 1.0)

    # Multi-signal agreement: count votes per type
    type_counts = Counter(s[0] for s in signals)
    type_max_conf = {}
    for stype, conf in signals:
        if stype not in type_max_conf or conf > type_max_conf[stype]:
            type_max_conf[stype] = conf

    # If 2+ signals agree on a type, prefer that type
    for stype, count in type_counts.most_common():
        if count >= 2:
            return (stype, type_max_conf[stype])

    # Single signal: return the highest-confidence signal
    best = max(signals, key=lambda s: s[1])
    return best


def is_forced_external_sub(file_path: str) -> bool:
    """Check if an external subtitle file is forced/signs by filename pattern.

    Simple filename-only check for fast scanning. Uses the standard
    naming convention: .forced., .signs., .sign., .foreign. before the
    subtitle extension.

    Args:
        file_path: Path to the subtitle file.

    Returns:
        True if filename matches forced/signs pattern.
    """
    return bool(FORCED_FILENAME_RE.search(os.path.basename(file_path)))


def classify_forced_result(result_filename: str, provider_data: dict = None) -> str:
    """Classify a provider search result as full, forced, or signs.

    Checks the result filename for forced/signs patterns and uses
    provider-specific metadata when available (e.g., OpenSubtitles
    foreign_parts_only).

    Args:
        result_filename: Filename of the subtitle result.
        provider_data: Optional provider-specific metadata dict.

    Returns:
        str: 'full', 'forced', or 'signs'
    """
    # Check provider-specific metadata first
    if provider_data and provider_data.get("foreign_parts_only"):
        return "forced"

    # Check filename patterns
    if not result_filename:
        return "full"

    name_lower = result_filename.lower()
    if ".forced." in name_lower or ".foreign." in name_lower:
        return "forced"
    if ".signs." in name_lower or ".sign." in name_lower:
        return "signs"

    # Check for signs/songs keywords in filename (common in fansub releases)
    # e.g., "[SubGroup] Show - 01 (Signs & Songs).ass"
    if re.search(r'\bsigns?\s*[&+]\s*songs?\b', name_lower):
        return "signs"
    if re.search(r'\bsigns?\s*only\b', name_lower):
        return "signs"
    if re.search(r'\bforced\b', name_lower):
        return "forced"

    return "full"
