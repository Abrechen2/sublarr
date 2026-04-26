"""Lightweight in-memory cache for Sonarr / Radarr series & movie titles.

Used by `routes/profiles_overrides.py` to enrich the Profiles & Overrides
scope tree with pretty titles for series/movies that have no row in
`search_series` / `standalone_*` (e.g. items added to the override tree
purely via the SeriesDetail "Subtitle settings" button before any search ran).

Strategy:
    - On first call (or after TTL expiry), fetch the FULL series/movie list
      from every configured Sonarr/Radarr instance via /api/v3/series resp.
      /api/v3/movie. One request per instance — fast even on large libs.
    - Build {sonarr_series_id: title} / {radarr_movie_id: title} maps.
    - Cache for ARR_TITLE_CACHE_TTL_SECS (default 300 s).
    - All errors swallowed silently — title resolution is a UX nicety, not
      a correctness requirement; placeholders ("#<id>") are an acceptable
      fallback when Sonarr/Radarr is unreachable.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config_instances import get_radarr_instances, get_sonarr_instances

logger = logging.getLogger(__name__)

ARR_TITLE_CACHE_TTL_SECS = 300  # 5 minutes
_HTTP_TIMEOUT_SECS = 5

_series_cache: dict[int, str] = {}
_series_cache_at: float = 0.0
_movies_cache: dict[int, str] = {}
_movies_cache_at: float = 0.0


def _fetch_arr_titles(instances: list[dict[str, Any]], path: str, id_field: str) -> dict[int, str]:
    """Aggregate id→title across every configured instance.

    Each instance entry has at least {url, api_key}. Failures are logged at
    debug level and the corresponding instance contributes nothing.
    """
    out: dict[int, str] = {}
    for inst in instances:
        url = inst.get("url", "").rstrip("/")
        api_key = inst.get("api_key")
        if not url or not api_key:
            continue
        try:
            resp = requests.get(
                f"{url}{path}",
                headers={"X-Api-Key": api_key},
                timeout=_HTTP_TIMEOUT_SECS,
            )
            resp.raise_for_status()
            for item in resp.json():
                item_id = item.get(id_field)
                title = item.get("title")
                if isinstance(item_id, int) and isinstance(title, str) and title:
                    out[item_id] = title
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.debug(
                "arr_title_cache: instance %s fetch failed: %s",
                inst.get("name", url),
                e,
            )
    return out


def get_sonarr_series_titles() -> dict[int, str]:
    """Cached map sonarr_series_id → title across all configured Sonarr instances."""
    global _series_cache, _series_cache_at
    now = time.monotonic()
    if not _series_cache or now - _series_cache_at > ARR_TITLE_CACHE_TTL_SECS:
        _series_cache = _fetch_arr_titles(get_sonarr_instances(), "/api/v3/series", "id")
        _series_cache_at = now
    return _series_cache


def get_radarr_movie_titles() -> dict[int, str]:
    """Cached map radarr_movie_id → title across all configured Radarr instances."""
    global _movies_cache, _movies_cache_at
    now = time.monotonic()
    if not _movies_cache or now - _movies_cache_at > ARR_TITLE_CACHE_TTL_SECS:
        _movies_cache = _fetch_arr_titles(get_radarr_instances(), "/api/v3/movie", "id")
        _movies_cache_at = now
    return _movies_cache


def invalidate() -> None:
    """Force-clear caches — useful in tests and after config changes."""
    global _series_cache, _series_cache_at, _movies_cache, _movies_cache_at
    _series_cache = {}
    _series_cache_at = 0.0
    _movies_cache = {}
    _movies_cache_at = 0.0
