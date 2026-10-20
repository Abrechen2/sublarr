"""Sidecars Sublarr downloaded that turned out to belong to another episode.

Prod 2026-10 (Clevatess): ffsubsync measured shifts beyond the sanity
threshold on subtitles of other episodes. The sync left the file alone, the
automation row went terminal, and since a target ASS was on disk the wanted
scanner never queued the episode again — the wrong subtitle stayed for good.

``quarantine_wrong_sidecar`` handles such a sidecar when it came from an
automatic provider download (never a manual upload, an extraction or a file
the user edited):

  1. blacklists the provider + subtitle id, so no search picks it again;
  2. marks the sidecar suspect — the blacklist row carries the sidecar path
     and a reason starting with :data:`SUSPECT_REASON_PREFIX` (no schema
     change). A suspect sidecar does not count as an existing subtitle for
     the wanted scanner or the search;
  3. requeues the item (a scan of its Sonarr series / Radarr movie, or a
     plain wanted row when neither knows the file).

The file itself is kept until a replacement lands: one saved under the same
name replaces it (and its newer mtime ends the suspect state), one saved in
the other format retires it (:func:`retire_suspect_siblings`).
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

SUSPECT_REASON_PREFIX = "Suspect wrong subtitle"
#: Only an automatic provider download is quarantined; a user's own choice
#: (manual upload, interactive pick) or an extraction never is.
_QUARANTINE_SOURCES = frozenset({"provider"})
_SIDECAR_FORMATS = ("ass", "srt")
#: A sidecar written later than its suspect flag by more than this was
#: replaced since and is no longer the suspect file.
_REPLACED_GRACE = timedelta(seconds=60)
_CACHE_TTL_S = 60.0
_EPISODE_RE = re.compile(r"S\d{1,3}E\d{1,4}", re.IGNORECASE)

_cache_lock = threading.Lock()
_cache: tuple[float, dict[str, datetime]] | None = None


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _suspects() -> dict[str, datetime]:
    """Suspect sidecar path → flag time. Cached briefly: the scanner asks per file."""
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now - _cache[0] < _CACHE_TTL_S:
            return _cache[1]
    try:
        from sqlalchemy import select

        from db.models.core import BlacklistEntry
        from extensions import db

        rows = db.session.execute(
            select(BlacklistEntry.file_path, BlacklistEntry.added_at).where(
                BlacklistEntry.reason.like(SUSPECT_REASON_PREFIX + "%")
            )
        ).all()
        suspects = {_norm(p): _aware(at) for p, at in rows if p and at}
    except Exception as exc:  # noqa: BLE001 — unknown means "nothing is suspect"
        logger.debug("suspect sidecars: lookup failed: %s", exc)
        return {}
    with _cache_lock:
        _cache = (now, suspects)
    return suspects


def is_suspect_sidecar(path: str) -> bool:
    """True while ``path`` is the very file that was flagged (not replaced since)."""
    flagged_at = _suspects().get(_norm(path))
    if flagged_at is None:
        return False
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)
    except OSError:
        return False
    return mtime <= flagged_at + _REPLACED_GRACE


def existing_ignoring_suspects(video_path: str, language: str, existing: str | None):
    """``existing`` (as from ``detect_existing_target_for_lang``) minus suspect sidecars.

    A suspect ASS next to a genuine SRT reads as ``"srt"``; with no genuine
    sidecar left the answer is None. Unchanged when nothing is suspect (the
    common case costs one cached lookup) or no sidecar file is involved.
    """
    if existing not in _SIDECAR_FORMATS or not _suspects():
        return existing
    from translator import find_existing_target_file

    found = {fmt: find_existing_target_file(video_path, language, fmt) for fmt in _SIDECAR_FORMATS}
    if not any(found.values()):
        return existing  # an embedded track, not a sidecar
    for fmt in _SIDECAR_FORMATS:
        if found[fmt] and not is_suspect_sidecar(found[fmt]):
            return fmt
    return None


def retire_suspect_siblings(saved_path: str, language: str) -> None:
    """Remove suspect sidecars of the same video and language once ``saved_path`` landed.

    Never raises: the new subtitle is saved; a leftover is a tidy-up problem.
    """
    try:
        if not _suspects():
            return
        from providers.download_manager import _video_for_sidecar
        from translator import find_existing_target_file

        video = _video_for_sidecar(saved_path)
        if not video:
            return
        keep = _norm(saved_path)
        for fmt in _SIDECAR_FORMATS:
            other = find_existing_target_file(video, language, fmt)
            if other and _norm(other) != keep and is_suspect_sidecar(other):
                os.remove(other)
                logger.info("suspect sidecar %s retired, replaced by %s", other, saved_path)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: could not retire siblings of %s: %s", saved_path, exc)


def _download_vouching_for(subtitle_path: str):
    """``(video, language, download_row)`` when an automatic download wrote this file."""
    from db.quality import is_user_modified
    from services.foreign_tracks.sidecars import _identify, _latest_download, _latest_origin

    identity = _identify(subtitle_path)
    if identity is None:
        return None
    video, language, fmt = identity
    if is_user_modified(subtitle_path):
        return None
    download = _latest_download(video, language)
    if download is None or not download.subtitle_id or not download.provider_name:
        return None
    if (download.source or "provider") not in _QUARANTINE_SOURCES:
        return None
    if download.provider_name == "translation" or (download.format or "").lower() != fmt:
        return None
    origin = _latest_origin(video, language)
    if (
        origin is not None
        and origin.origin != "resync"
        and _aware(origin.recorded_at) >= _aware(download.downloaded_at)
    ):
        return None  # extracted or restored after the download
    return video, language, download


def quarantine_wrong_sidecar(subtitle_path: str, video_path: str, reason: str) -> bool:
    """Blacklist, flag and requeue a downloaded sidecar that belongs elsewhere.

    Returns True when the sidecar was quarantined. Never raises — the caller
    is a sync failure path that must still book its own outcome.
    """
    try:
        vouched = _download_vouching_for(subtitle_path)
        if vouched is None:
            logger.info(
                "suspect sidecar: %s not quarantined (not an automatic download): %s",
                subtitle_path,
                reason,
            )
            return False
        video, language, download = vouched
        from db.blacklist import add_blacklist_entry

        add_blacklist_entry(
            provider_name=download.provider_name,
            subtitle_id=download.subtitle_id,
            language=language,
            file_path=subtitle_path,
            title=os.path.basename(video_path or video),
            reason=f"{SUSPECT_REASON_PREFIX}: {reason}"[:500],
        )
        invalidate_cache()
        logger.warning(
            "suspect sidecar: %s (%s/%s) does not fit %s — blacklisted, kept until "
            "replaced, wanted search requeued: %s",
            subtitle_path,
            download.provider_name,
            download.subtitle_id,
            video,
            reason,
        )
        _requeue(video, language)
        return True
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: quarantine of %s failed: %s", subtitle_path, exc)
        return False


def _is_under(path: str, root: str) -> bool:
    root = _norm(root).rstrip(os.sep)
    return bool(root) and _norm(path).startswith(root + os.sep)


def _rescan_arr(video: str) -> bool:
    """Rescan the Sonarr series / Radarr movie holding ``video``; True when one ran."""
    from config import map_path
    from radarr_client import get_radarr_client
    from services.wanted_scanner import get_scanner
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client()
    if sonarr:
        for series in sonarr.get_series() or []:
            if series.get("id") and _is_under(video, map_path(series.get("path") or "")):
                return "error" not in get_scanner().scan_series(series["id"])
    radarr = get_radarr_client()
    if radarr:
        for movie in radarr.get_movies() or []:
            if movie.get("id") and _is_under(video, map_path(movie.get("path") or "")):
                return "error" not in get_scanner().scan_movie(movie["id"])
    return False


def _requeue(video: str, language: str) -> None:
    """Get a fresh wanted search for ``video``/``language``. Never raises."""
    try:
        if _rescan_arr(video):
            return
    except Exception as exc:  # noqa: BLE001 — fall back to a plain row
        logger.warning("suspect sidecar: arr rescan for %s failed: %s", video, exc)
    try:
        from db.wanted import upsert_wanted_item

        name = os.path.splitext(os.path.basename(video))[0]
        episode = _EPISODE_RE.search(name)
        # The next scan of the series/movie fills in the arr ids on this row
        # (same file, language and type).
        upsert_wanted_item(
            item_type="episode" if episode else "movie",
            file_path=video,
            title=name,
            season_episode=episode.group(0).upper() if episode else "",
            target_language=language,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: could not requeue %s/%s: %s", video, language, exc)
