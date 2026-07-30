"""Wanted search scoring — priority key computation and fansub rules."""


def _get_priority_key(result, target_lang, source_lang):
    """Calculate priority: target.ass=0, source.ass=1, target.srt=2, source.srt=3"""
    is_target = result["language"] == target_lang
    is_ass = result["format"] == "ass"

    if is_target and is_ass:
        return (0, -result["score"])  # Highest priority: target.ass
    elif not is_target and is_ass:
        return (1, -result["score"])  # Second priority: source.ass
    elif is_target and not is_ass:
        return (2, -result["score"])  # Third priority: target.srt
    else:
        return (3, -result["score"])  # Lowest priority: source.srt


def _apply_fansub_rules(
    results: list[dict],
    preferred: list[str],
    excluded: list[str],
    bonus: int,
) -> None:
    """Adjust scores in-place based on fansub group preferences.

    Performs case-insensitive substring matching against result["release_info"].
    Preferred group match: +bonus points.
    Excluded group match: -999 points (effectively removes from selection).

    Empty/whitespace-only entries are filtered out: ``"" in info`` is always
    True, so a single blank entry (trailing comma in the UI, copy-pasted
    newline, historical bad data in the JSON column) would silently match
    every result — killing the entire search if it landed in ``excluded``,
    or granting the bonus to every candidate if in ``preferred``.
    """
    preferred_lower = [g.strip().lower() for g in preferred if g and g.strip()]
    excluded_lower = [g.strip().lower() for g in excluded if g and g.strip()]

    for result in results:
        info = result.get("release_info", "").lower()
        if excluded_lower and any(g in info for g in excluded_lower):
            result["score"] -= 999
        elif preferred_lower and any(g in info for g in preferred_lower):
            result["score"] += bonus


def _apply_release_group_tiers(results: list[dict], tiers: list[str], step: int) -> None:
    """Adjust scores in-place based on the global release-group tier ranking.

    ``tiers`` is an ordered list (best first). A result matching the group at
    index ``i`` (case-insensitive substring on release_info) gets
    ``step * (len(tiers) - i)`` bonus points — the top tier earns the most,
    the last tier still earns ``step``. Only the best (lowest-index) matching
    tier counts per result.

    Empty/whitespace entries are dropped for the same reason as in
    ``_apply_fansub_rules``: ``"" in info`` is always True and would grant
    the bonus to every candidate.
    """
    tiers_lower = [g.strip().lower() for g in tiers if g and g.strip()]
    if not tiers_lower or step <= 0:
        return

    n = len(tiers_lower)
    for result in results:
        info = result.get("release_info", "").lower()
        for idx, group in enumerate(tiers_lower):
            if group in info:
                result["score"] += step * (n - idx)
                break


# Codec family aliases — result release_info uses various spellings
_CODEC_ALIASES: dict[str, list[str]] = {
    "x265": ["x265", "hevc", "h265"],
    "hevc": ["x265", "hevc", "h265"],
    "h265": ["x265", "hevc", "h265"],
    "x264": ["x264", "h264", "avc"],
    "h264": ["x264", "h264", "avc"],
    "avc": ["x264", "h264", "avc"],
    "av1": ["av1"],
}


def apply_video_codec_bonus(results: list[dict], video_codec: str, weight: int) -> None:
    """Add weight to results whose release_info contains the video file's codec.

    Performs in-place mutation on the results list.
    Case-insensitive substring match against release_info.
    """
    if not video_codec or not weight:
        return

    codec_lower = video_codec.lower()
    tags = _CODEC_ALIASES.get(codec_lower, [codec_lower])

    for result in results:
        info = result.get("release_info", "").lower()
        if any(tag in info for tag in tags):
            result["score"] += weight
