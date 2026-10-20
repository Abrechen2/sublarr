"""The release page a wanted file was grabbed from, for the tracker bundles.

The CinemaZ and AvistaZ catalog bundles search nothing but the release page
on their tracker (``video["info_url"]``). Sonarr and Radarr keep that page in
the item's history: a ``grabbed`` record carries it as ``data.nzbInfoUrl``
(for torrents too), and the ``downloadFolderImported`` record of the file on
disk shares that grab's ``downloadId``.

Reading history costs a request per item, so it only happens when one of
those bundles is enabled and allowed for the search, and the answer is kept
per episode/movie for an hour.
"""

import logging
import os
import threading
import time

from config import get_settings
from providers.base import VideoQuery

logger = logging.getLogger(__name__)

RELEASE_PAGE_PROVIDERS = frozenset({"cinemaz", "avistaz"})
_CACHE_TTL = 3600  # seconds
_cache: dict[tuple, tuple[str | None, float]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _records(records) -> list[dict]:
    """Well-formed history records, newest first."""
    valid = [r for r in records or [] if isinstance(r, dict) and isinstance(r.get("data"), dict)]
    return sorted(valid, key=lambda r: str(r.get("date") or ""), reverse=True)


def pick_release_page(records, file_path: str) -> str | None:
    """The release page of the grab the current file came from.

    The grab whose ``downloadId`` matches the newest import of a file with
    this file's name (paths differ between Sublarr and the *arr, names do
    not). When that import has no grab — a manual import, or a grab no longer
    in history — there is no page: any other grab is another release, and the
    tracker bundles would fetch subtitles for a different cut. Only when no
    import carries this name (the file was renamed since) does the newest
    import stand in for it, and without any import the newest grab: a later
    grab may be an upgrade that was never imported.
    """
    ordered = _records(records)
    grabs = [r for r in ordered if r.get("eventType") == "grabbed" and r["data"].get("nzbInfoUrl")]
    if not grabs:
        return None
    imports = [r for r in ordered if r.get("eventType") == "downloadFolderImported"]
    name = os.path.basename(file_path or "")
    same_file = [
        r for r in imports if os.path.basename(str(r["data"].get("importedPath") or "")) == name
    ]
    current = (same_file or imports)[:1]
    if not current:
        return str(grabs[0]["data"]["nzbInfoUrl"])
    download_id = current[0].get("downloadId")
    for grab in grabs:
        if download_id and grab.get("downloadId") == download_id:
            return str(grab["data"]["nzbInfoUrl"])
    return None


def _wanted_by_search(query: VideoQuery) -> bool:
    """Whether a provider that reads the release page will search this query."""
    settings = get_settings()
    if not getattr(settings, "provider_hub_enabled", False):
        return False
    from providers.registry import resolve_enabled_names

    names = (
        resolve_enabled_names(getattr(settings, "providers_enabled", "")) & RELEASE_PAGE_PROVIDERS
    )
    if query.allowed_providers:
        names &= set(query.allowed_providers)
    return bool(names)


def _history_key(wanted_item: dict) -> tuple | None:
    """``(arr, instance, item id)`` of the item's *arr record, None without one."""
    instance = wanted_item.get("instance_name")
    if wanted_item.get("item_type") == "episode" and wanted_item.get("sonarr_episode_id"):
        return ("sonarr", instance, wanted_item["sonarr_episode_id"])
    if wanted_item.get("item_type") == "movie" and wanted_item.get("radarr_movie_id"):
        return ("radarr", instance, wanted_item["radarr_movie_id"])
    return None


def _read_history(key: tuple) -> list:
    arr, instance, item_id = key
    if arr == "sonarr":
        from sonarr_client import get_sonarr_client

        client = get_sonarr_client(instance_name=instance)
        return client.get_episode_history(item_id) if client else []
    from radarr_client import get_radarr_client

    client = get_radarr_client(instance_name=instance)
    return client.get_movie_history(item_id) if client else []


def enrich_release_page(query: VideoQuery, wanted_item: dict) -> None:
    """Set ``query.info_url`` from the *arr history when a tracker bundle will use it."""
    if query.info_url or not _wanted_by_search(query):
        return
    key = _history_key(wanted_item)
    if key is None:
        return
    try:
        now = time.time()
        # The file is part of the key: after an upgrade import it is another
        # release, and the page cached for the old one must not be reused.
        cache_key = (*key, query.file_path)
        with _cache_lock:
            cached = _cache.get(cache_key)
        if cached and now < cached[1]:
            page = cached[0]
        else:
            page = pick_release_page(_read_history(key), query.file_path)
            with _cache_lock:
                _cache[cache_key] = (page, now + _CACHE_TTL)
        if page:
            query.info_url = page
            logger.debug("Wanted %s: release page from %s history", wanted_item.get("id"), key[0])
    except Exception as e:  # noqa: BLE001 — history is a hint, never a search blocker
        logger.warning(
            "Wanted %s: reading the release page from history failed: %s",
            wanted_item.get("id"),
            e,
        )
