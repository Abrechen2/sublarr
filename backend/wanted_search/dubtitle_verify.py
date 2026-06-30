"""Audio-verify a downloaded English sidecar against the dub before keeping it.

Opt-in via ``dubtitle_verify_on_download``. Never *blocks*: a confident
low-score mismatch returns False (caller keeps + flags); every unverifiable /
disabled / error case returns True (keep silently).
"""

import logging

from services.dubtitle import validate_subtitle_against_audio

logger = logging.getLogger(__name__)

_SKIP_MARKERS = ("validation skipped", "no readable cues", "no cues in sampled")


def verify_dubtitle_on_keep(saved_path: str, video_path: str, settings) -> bool:
    """Return True if the sub should be kept clean; False on a confident mismatch.

    False is returned ONLY for a real low-score audio mismatch. The caller keeps
    the file either way — False just means "flag it".
    """
    if not getattr(settings, "dubtitle_verify_on_download", False):
        return True
    low = saved_path.lower()
    if ".en." not in low and not low.endswith(".en.srt"):
        return True  # only English subs are dub-verifiable
    try:
        result = validate_subtitle_against_audio(
            video_path, saved_path, min_score=getattr(settings, "dubtitle_min_score", 0.55)
        )
    except Exception as exc:  # never block on a verifier crash
        logger.warning("dubtitle verify errored for %s: %s — keeping", saved_path, exc)
        return True
    if result.passed:
        return True
    msg = (result.message or "").lower()
    if any(marker in msg for marker in _SKIP_MARKERS):
        logger.info(
            "dubtitle verify unverifiable for %s — keeping (%s)", saved_path, result.message
        )
        return True
    logger.warning(
        "dubtitle verify: %s is a likely dub mismatch (score %.2f) — kept but flagged: %s",
        saved_path,
        result.score,
        result.message,
    )
    return False
