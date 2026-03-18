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
    """
    preferred_lower = [g.lower() for g in preferred]
    excluded_lower = [g.lower() for g in excluded]

    for result in results:
        info = result.get("release_info", "").lower()
        if any(g in info for g in excluded_lower):
            result["score"] -= 999
        elif any(g in info for g in preferred_lower):
            result["score"] += bonus
