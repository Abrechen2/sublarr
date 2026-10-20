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
name replaces it, one saved in the other format retires it
(:func:`retire_suspect_siblings`). The flag records the SHA-256 of the file it
was raised on, so only those bytes are suspect: a replacement saved in the
same second is not (an mtime grace window kept it suspect for good), and the
same wrong file restored later is again.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

from db.repositories.blacklist import SUSPECT_BLOCKED_EVERYWHERE, SUSPECT_REASON_PREFIX

logger = logging.getLogger(__name__)

__all__ = ["SUSPECT_BLOCKED_EVERYWHERE", "SUSPECT_REASON_PREFIX"]
#: Only an automatic provider download is quarantined; a user's own choice
#: (manual upload, interactive pick) or an extraction never is.
_QUARANTINE_SOURCES = frozenset({"provider"})
_SIDECAR_FORMATS = ("ass", "srt")
#: Flags written before 1.17.0 carry no digest: a sidecar written later than
#: such a flag by more than this was replaced since.
_REPLACED_GRACE = timedelta(seconds=60)
_CACHE_TTL_S = 60.0
_EPISODE_RE = re.compile(r"S\d{1,3}E\d{1,4}", re.IGNORECASE)

_cache_lock = threading.Lock()
# (time, suspect sidecar path -> flag, (provider, subtitle id) -> its sidecars,
#  entries the user blocked everywhere)
_cache: (
    tuple[float, dict[str, list[_Flag]], dict[tuple[str, str], set[str]], set[tuple[str, str]]]
    | None
) = None
# (path, mtime_ns, size) -> SHA-256; a sidecar is hashed again only once it changed.
_digests: dict[tuple, str] = {}


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None
    _digests.clear()


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _file_digest(path: str) -> str | None:
    """SHA-256 of the file's bytes, or None when it cannot be read.

    Memoised per file version. Size and mtime alone are not one: a file moved
    in with ``cp -p`` or ``rsync -t`` keeps both, so device, inode and ctime
    (which no tool can set back) are in the key. The stat and the bytes come
    from the same open file.
    """
    try:
        with open(path, "rb") as fh:
            stat = os.fstat(fh.fileno())
            key = (
                _norm(path),
                stat.st_dev,
                stat.st_ino,
                stat.st_ctime_ns,
                stat.st_mtime_ns,
                stat.st_size,
            )
            digest = _digests.get(key)
            if digest is None:
                digest = hashlib.sha256(fh.read()).hexdigest()
                if len(_digests) > 1024:
                    _digests.clear()
                _digests[key] = digest
            return digest
    except OSError:
        return None


class _Flag(NamedTuple):
    at: datetime
    #: SHA-256 of the flagged file; None for a flag written before 1.17.0.
    digest: str | None


def _flagged_paths(file_path: str, added_at: datetime) -> list[tuple[str, _Flag]]:
    """The sidecars one suspect entry stands for, each with its own flag.

    One provider subtitle can be wrong for several videos (S01E05's subtitle
    saved for S02E05 and S03E05), but the blacklist holds one row per
    subtitle: one line per sidecar, ``path<TAB>ISO time<TAB>sha256``. A line
    without a time was flagged at ``added_at``; one without a digest predates
    1.17.0 and is judged by mtime.
    """
    flagged = []
    for line in (file_path or "").splitlines():
        path, _, rest = line.partition("\t")
        if not path:
            continue
        stamp, _, digest = rest.partition("\t")
        try:
            at = _aware(datetime.fromisoformat(stamp)) if stamp else _aware(added_at)
        except ValueError:
            at = _aware(added_at)
        flagged.append((path, _Flag(at, digest or None)))
    return flagged


def _flag_line(sidecar: str) -> str:
    return f"{sidecar}\t{datetime.now(UTC).isoformat()}\t{_file_digest(sidecar) or ''}"


def _load() -> tuple[dict[str, list[_Flag]], dict[tuple[str, str], set[str]], set[tuple[str, str]]]:
    """Suspect entries, cached briefly: the scanner and the search ask per file."""
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and now - _cache[0] < _CACHE_TTL_S:
            return _cache[1], _cache[2], _cache[3]
    try:
        from sqlalchemy import select

        from db.models.core import BlacklistEntry
        from extensions import db

        rows = db.session.execute(
            select(
                BlacklistEntry.provider_name,
                BlacklistEntry.subtitle_id,
                BlacklistEntry.file_path,
                BlacklistEntry.added_at,
                BlacklistEntry.reason,
            ).where(BlacklistEntry.reason.like(SUSPECT_REASON_PREFIX + "%"))
        ).all()
    except Exception as exc:  # noqa: BLE001 — unknown means "nothing is suspect"
        logger.debug("suspect sidecars: lookup failed: %s", exc)
        return {}, {}, set()
    suspects: dict[str, list[_Flag]] = {}
    entries: dict[tuple[str, str], set[str]] = {}
    everywhere: set[tuple[str, str]] = set()
    for provider, subtitle_id, file_path, added_at, reason in rows:
        if not added_at:
            continue
        key = (provider, str(subtitle_id))
        if (reason or "").startswith(SUSPECT_BLOCKED_EVERYWHERE):
            everywhere.add(key)
        for path, flag in _flagged_paths(file_path, added_at):
            # Two providers' wrong files can have been saved under one name.
            suspects.setdefault(_norm(path), []).append(flag)
            entries.setdefault(key, set()).add(path)
    with _cache_lock:
        _cache = (now, suspects, entries, everywhere)
    return suspects, entries, everywhere


def _suspects() -> dict[str, list[_Flag]]:
    """Suspect sidecar path → its flags (one per blacklist entry that names it)."""
    return _load()[0]


def _video_stem_of(sidecar: str) -> str:
    from subtitle_filename import parse_subtitle_filename

    parsed = parse_subtitle_filename(sidecar)
    base = parsed.base if parsed else os.path.splitext(os.path.basename(sidecar))[0]
    return _norm(os.path.join(os.path.dirname(sidecar), base))


def blocks_result_for(provider_name: str, subtitle_id: str, video_path: str | None) -> bool:
    """Whether the blacklist keeps this provider result from ``video_path``.

    A user's blacklist entry blocks the subtitle everywhere. A suspect entry
    only blocks it for the videos it was found not to fit: the subtitle of
    S01E05 that was saved for S02E05 is still S01E05's subtitle.
    """
    from db.blacklist import is_blacklisted

    if not is_blacklisted(provider_name, str(subtitle_id)):
        return False
    _, entries, everywhere = _load()
    key = (provider_name, str(subtitle_id))
    sidecars = entries.get(key)
    if sidecars is None or key in everywhere or not video_path:
        return True
    stem = _norm(os.path.splitext(video_path)[0])
    return any(_video_stem_of(sidecar) == stem for sidecar in sidecars)


def is_suspect_sidecar(path: str) -> bool:
    """True while ``path`` holds the very bytes one of its flags was raised on."""
    flags = _suspects().get(_norm(path))
    if not flags:
        return False
    return any(_flag_holds(path, flag) for flag in flags)


def _flag_holds(path: str, flag: _Flag) -> bool:
    if flag.digest:
        return _file_digest(path) == flag.digest
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=UTC)
    except OSError:
        return False
    return mtime <= flag.at + _REPLACED_GRACE


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


def _blacklist_for(
    provider_name: str, subtitle_id: str, language: str, sidecar: str, video: str, reason: str
) -> None:
    """Add a suspect entry, or add ``sidecar`` to the suspect entry already there."""
    from sqlalchemy import select

    from db.blacklist import add_blacklist_entry
    from db.models.core import BlacklistEntry
    from extensions import db

    entry = db.session.execute(
        select(BlacklistEntry).where(
            BlacklistEntry.provider_name == provider_name,
            BlacklistEntry.subtitle_id == str(subtitle_id),
        )
    ).scalar_one_or_none()
    if entry is None:
        add_blacklist_entry(
            provider_name=provider_name,
            subtitle_id=subtitle_id,
            language=language,
            file_path=_flag_line(sidecar),
            title=os.path.basename(video),
            reason=f"{SUSPECT_REASON_PREFIX}: {reason}"[:500],
        )
        return
    if not (entry.reason or "").startswith(SUSPECT_REASON_PREFIX):
        return  # the user blacklisted it already: blocked everywhere
    # Flagged again (the same wrong file restored or re-picked): the line is
    # rewritten, so the flag stands for the bytes on disk now.
    lines = [
        line
        for line in (entry.file_path or "").splitlines()
        if line and _norm(line.partition("\t")[0]) != _norm(sidecar)
    ]
    entry.file_path = "\n".join([*lines, _flag_line(sidecar)])
    db.session.commit()


def quarantine_wrong_sidecar(
    subtitle_path: str, video_path: str, reason: str, *, requeue: bool = True
) -> bool:
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
        _blacklist_for(
            download.provider_name,
            download.subtitle_id,
            language,
            subtitle_path,
            video_path or video,
            reason,
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
        if requeue:
            _requeue(video, language)
        return True
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: quarantine of %s failed: %s", subtitle_path, exc)
        return False


def _is_under(path: str, root: str) -> bool:
    root = _norm(root).rstrip(os.sep)
    return bool(root) and _norm(path).startswith(root + os.sep)


def _arr_owner(video: str, series_list: list, movie_list: list) -> tuple[str, int] | None:
    """("series" | "movie", id) of the Sonarr series / Radarr movie holding ``video``."""
    from config import map_path

    for kind, items in (("series", series_list), ("movie", movie_list)):
        for item in items:
            if item.get("id") and _is_under(video, map_path(item.get("path") or "")):
                return kind, item["id"]
    return None


def _arr_lists() -> tuple[list, list]:
    from radarr_client import get_radarr_client
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client()
    radarr = get_radarr_client()
    return (
        (sonarr.get_series() or []) if sonarr else [],
        (radarr.get_movies() or []) if radarr else [],
    )


def _rescan(owner: tuple[str, int]) -> bool:
    from services.wanted_scanner import get_scanner

    kind, item_id = owner
    scanner = get_scanner()
    outcome = scanner.scan_series(item_id) if kind == "series" else scanner.scan_movie(item_id)
    return "error" not in outcome


def _rescan_arr(video: str) -> bool:
    """Rescan the Sonarr series / Radarr movie holding ``video``; True when one ran."""
    owner = _arr_owner(video, *_arr_lists())
    return owner is not None and _rescan(owner)


def requeue_videos(videos: list[tuple[str, str]]) -> None:
    """``_requeue`` for many (video, language) pairs: each series is rescanned once."""
    if not videos:
        return
    try:
        lists = _arr_lists()
    except Exception as exc:  # noqa: BLE001 — fall back to plain rows
        logger.warning("suspect sidecar: arr lookup failed: %s", exc)
        lists = ([], [])
    rescanned: dict[tuple[str, int], bool] = {}
    for video, language in videos:
        owner = _arr_owner(video, *lists)
        if owner is not None:
            if owner not in rescanned:
                try:
                    rescanned[owner] = _rescan(owner)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("suspect sidecar: rescan of %s failed: %s", owner, exc)
                    rescanned[owner] = False
        if owner is None or not rescanned[owner]:
            _plain_wanted_row(video, language)
        _clear_backoff(video, language)


def _requeue(video: str, language: str) -> None:
    """Get a fresh wanted search for ``video``/``language``. Never raises."""
    try:
        rescanned = _rescan_arr(video)
    except Exception as exc:  # noqa: BLE001 — fall back to a plain row
        logger.warning("suspect sidecar: arr rescan for %s failed: %s", video, exc)
        rescanned = False
    if not rescanned:
        _plain_wanted_row(video, language)
    _clear_backoff(video, language)


def _clear_backoff(video: str, language: str) -> None:
    """Let the requeued search run now, not after the item's old backoff.

    An episode that searched in vain for weeks sits in slow mode (30 days
    between attempts); its wrong subtitle being found changes the question,
    so the attempts start over (VM 191: the requeue kept the 30-day wait).
    Never raises.
    """
    try:
        from db.repositories.wanted import WantedRepository
        from db.wanted import get_wanted_items_by_path

        ids = [
            item["id"]
            for item in get_wanted_items_by_path(video)
            if (item.get("target_language") or "") == language
        ]
        WantedRepository().reset_search_attempts(ids)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning(
            "suspect sidecar: could not reset backoff of %s/%s: %s", video, language, exc
        )


def _plain_wanted_row(video: str, language: str) -> None:
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
