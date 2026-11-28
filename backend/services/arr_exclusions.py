"""Keep Sonarr series / Radarr movies out of automatic subtitle work (Forgejo #83).

Mirrors Bazarr's Sonarr/Radarr options that the TRaSH setup guide recommends:
excluded tags, excluded series types and "only monitored". All are off by
default (empty / False), so an update changes nothing on its own.
"""

from __future__ import annotations

SERIES_TYPES = frozenset({"standard", "anime", "daily"})


def parse_list(value) -> set[str]:
    """Comma-separated setting as a set of lower-case entries."""
    if not value:
        return set()
    return {part.strip().lower() for part in str(value).split(",") if part.strip()}


def _excluded_tag(item: dict, tag_labels: dict, configured: str) -> str | None:
    wanted = parse_list(configured)
    if not wanted:
        return None
    for tag_id in item.get("tags") or []:
        label = str(tag_labels.get(tag_id, "")).lower()
        if label and label in wanted:
            return label
    return None


def series_exclusion(series: dict, tag_labels: dict, settings) -> str | None:
    """Why a Sonarr series is excluded, or None when it is not."""
    tag = _excluded_tag(series, tag_labels, getattr(settings, "sonarr_exclude_tags", ""))
    if tag:
        return f"tag '{tag}'"
    series_type = str(series.get("seriesType") or "").lower()
    if series_type and series_type in parse_list(
        getattr(settings, "sonarr_exclude_series_types", "")
    ):
        return f"series type '{series_type}'"
    if getattr(settings, "sonarr_only_monitored", False) and not series.get("monitored", True):
        return "not monitored"
    return None


def episode_excluded(episode: dict, settings) -> bool:
    """An unmonitored episode when only monitored ones count."""
    return bool(getattr(settings, "sonarr_only_monitored", False)) and not episode.get(
        "monitored", True
    )


def movie_exclusion(movie: dict, tag_labels: dict, settings) -> str | None:
    """Why a Radarr movie is excluded, or None when it is not."""
    tag = _excluded_tag(movie, tag_labels, getattr(settings, "radarr_exclude_tags", ""))
    if tag:
        return f"tag '{tag}'"
    if getattr(settings, "radarr_only_monitored", False) and not movie.get("monitored", True):
        return "not monitored"
    return None


_TAG_CACHE_SECONDS = 60
_tag_cache: dict[str, tuple[float, dict]] = {}


def tag_labels(client, configured) -> dict:
    """``{tag id: label}`` of a Sonarr/Radarr client, only when tags are configured.

    Cached briefly per instance URL: a full scan checks every series and
    must not ask the *arr for its tag list each time.
    """
    import time

    if not parse_list(configured) or client is None:
        return {}
    key = str(getattr(client, "url", id(client)))
    cached = _tag_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _TAG_CACHE_SECONDS:
        return cached[1]
    labels = {t.get("id"): t.get("label", "") for t in (client.get_tags() or []) if "id" in t}
    _tag_cache[key] = (now, labels)
    return labels
