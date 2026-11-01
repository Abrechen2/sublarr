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
    r"\.(?:forced|signs?|foreign)\.(?:ass|srt|ssa|vtt)$",
    re.IGNORECASE,
)

# Stream title keywords indicating forced/signs content
FORCED_STREAM_TITLE_RE = re.compile(
    r"\b(?:forced|signs?|songs?|foreign)\b",
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
            # The same rules as search results: "Full + Signs" is a dialogue
            # track, a substring "sign" alone said signs.
            kind, _confidence = classify_track_label(title)
            if kind != "full":
                signals.append((kind, 0.8))

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


# Track labels and file names after normalisation: lower case, every
# separator a space. AnimeTosho's secure_filename turns "Signs & Songs" into
# "Signs__Songs", so "&" may be gone by the time a name reaches us.
_LABEL_SEPARATORS_RE = re.compile(r"[\s_.()\[\]{}|,/:;-]+")
_SIGNS_AND_SONGS_RE = re.compile(r"\bsigns?\s*(?:&|\+|and)?\s*songs?\b")
_SIGNS_ONLY_RE = re.compile(r"\bsigns?\s+only\b")
_SIGNS_RE = re.compile(r"\bsigns?\b")
_SONGS_RE = re.compile(r"\bsongs?\b")
_FORCED_RE = re.compile(r"\b(?:forced|foreign)\b")
_DIALOGUE_RE = re.compile(r"\b(?:full|dialogue|dialog|complete)\b")
_SUBTITLE_EXT_RE = re.compile(r"\.(?:ass|ssa|srt|vtt|sub|zip)$", re.IGNORECASE)


def _normalise_label(text: str) -> str:
    text = _SUBTITLE_EXT_RE.sub("", text or "").lower()
    return " ".join(_LABEL_SEPARATORS_RE.sub(" ", text).split())


def classify_track_label(label: str) -> tuple[str, float]:
    """Kind and confidence for a subtitle track name ("Signs & Songs", "Dialogue").

    Explicit names ("Signs & Songs", "Signs Only") are certain. A bare "Signs"
    ("English (Signs) Official") is signs with lower confidence. A name that
    also says Full/Dialogue ("Full + Signs") is a dialogue track.
    """
    text = _normalise_label(label)
    if _DIALOGUE_RE.search(text):
        return "full", 0.9
    if _SIGNS_AND_SONGS_RE.search(text) or _SIGNS_ONLY_RE.search(text):
        return "signs", 0.95
    if _FORCED_RE.search(text):
        return "forced", 0.9
    if _SIGNS_RE.search(text):
        return "signs", 0.7
    if _SONGS_RE.search(text):
        # "Songs Only", "Songs": lyrics without dialogue.
        return "signs", 0.8
    return "full", 1.0


def _classify_filename(result_filename: str) -> tuple[str, float] | None:
    """Only explicit forms count in a release file name: a title may say "Signs"."""
    name_lower = (result_filename or "").lower()
    if ".forced." in name_lower or ".foreign." in name_lower:
        return "forced", 0.9
    if ".signs." in name_lower or ".sign." in name_lower:
        return "signs", 0.9
    text = _normalise_label(result_filename)
    if _SIGNS_AND_SONGS_RE.search(text) or _SIGNS_ONLY_RE.search(text):
        return "signs", 0.95
    if re.search(r"\bforced\b", text):
        return "forced", 0.9
    return None


def classify_result_kind(
    result_filename: str, provider_data: dict | None = None
) -> tuple[str, float, str]:
    """Kind (full|forced|signs), confidence and the signal that decided it.

    Signals, strongest first: provider metadata (OpenSubtitles
    ``foreign_parts_only``, the MKV forced flag of an AnimeTosho track), the
    track name the provider reported, then the file name. A forced flag says
    "not full"; the track name says whether that is signs & songs. A track
    flagged forced but named like dialogue stays forced, with low confidence.
    """
    data = provider_data or {}
    if data.get("foreign_parts_only"):
        return "forced", 0.95, "provider_flag"

    track_name = data.get("track_name") or ""
    flagged = bool(data.get("track_forced"))
    if track_name:
        kind, confidence = classify_track_label(track_name)
        if flagged:
            if kind == "full" and _DIALOGUE_RE.search(_normalise_label(track_name)):
                return "forced", 0.5, "conflict"
            if kind == "full":
                return "forced", 0.9, "provider_flag"
            return kind, max(confidence, 0.9), "track_name"
        if kind != "full":
            return kind, confidence, "track_name"
        return "full", 1.0, "track_name"
    if flagged:
        return "forced", 0.9, "provider_flag"

    by_name = _classify_filename(result_filename)
    if by_name:
        return by_name[0], by_name[1], "filename"
    return "full", 1.0, "default"


def classify_forced_result(result_filename: str, provider_data: dict = None) -> str:
    """Classify a provider search result as full, forced, or signs.

    See ``classify_result_kind`` for the signals.

    Returns:
        str: 'full', 'forced', or 'signs'
    """
    return classify_result_kind(result_filename, provider_data)[0]

    name_lower = result_filename.lower()
    if ".forced." in name_lower or ".foreign." in name_lower:
        return "forced"
    if ".signs." in name_lower or ".sign." in name_lower:
        return "signs"

    # Check for signs/songs keywords in filename (common in fansub releases)
    # e.g., "[SubGroup] Show - 01 (Signs & Songs).ass"
    if re.search(r"\bsigns?\s*[&+]\s*songs?\b", name_lower):
        return "signs"
    if re.search(r"\bsigns?\s*only\b", name_lower):
        return "signs"
    if re.search(r"\bforced\b", name_lower):
        return "forced"

    return "full"


# A file the search took for signs & songs that turns out to be a full
# dialogue track: this many dialogue lines, and this share of all lines.
_DIALOGUE_EVENTS_MIN = 150
_DIALOGUE_SHARE_MIN = 0.6


def content_kind_mismatch(
    result, content: bytes, query, duration_s: float | None = None
) -> str | None:
    """Why a downloaded file is not the kind the wanted item waits for.

    Corroborates the search-time classification after download: a [Forced]
    item refuses an ASS file that is plainly full dialogue, a regular item
    refuses one that holds nothing but signs & songs styles (an unlabeled
    signs track) or, when the video length ``duration_s`` is known, too few
    dialogue lines to be its dialogue subtitle, in any format. Anything
    unreadable or uncertain passes.
    """
    forced_only = getattr(query, "forced_only", False)
    full_only = getattr(query, "full_only", False)
    if not (forced_only or full_only) or not content:
        return None
    judge_sparse = full_only and bool(duration_s)
    if not getattr(result, "is_ass", False):
        if judge_sparse:
            from subtitle_dialogue import assess_content

            verdict = assess_content(content, duration_s)
            if verdict is not None and verdict.sparse_reason:
                return f"sparse, not a full subtitle: {verdict.sparse_reason}"
        return None
    try:
        import pysubs2

        from ass_utils import classify_styles

        subs = pysubs2.SSAFile.from_string(content.decode("utf-8-sig", errors="replace"))
    except Exception:  # noqa: BLE001 — unreadable: no verdict, the file decides elsewhere
        return None

    if judge_sparse:
        from subtitle_dialogue import assess

        try:
            sparse = assess(subs, duration_s, is_ass=True).sparse_reason
        except Exception:  # noqa: BLE001 — a check that cannot run must not block
            sparse = None
        if sparse:
            return f"sparse, not a full subtitle: {sparse}"

    events = [e for e in subs.events if not e.is_comment and e.text.strip()]
    if not events:
        return None
    dialog_styles, signs_styles = classify_styles(subs)
    dialogue_lines = sum(1 for e in events if e.style in dialog_styles)

    if forced_only:
        share = dialogue_lines / len(events)
        if dialogue_lines >= _DIALOGUE_EVENTS_MIN and share >= _DIALOGUE_SHARE_MIN:
            return (
                f"full dialogue, not {result.kind}: {dialogue_lines} of "
                f"{len(events)} lines use dialogue styles"
            )
        return None
    if signs_styles and not dialog_styles:
        return f"signs & songs only: every style is a signs style ({len(events)} lines)"
    return None
