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

The file itself goes to the subtitle trash (one restorable batch), so no job
can take it for an existing subtitle any more. Until 1.17.0-rc.11 it stayed on
disk until a replacement landed, and every job that asks "is there a
subtitle?" or rewrites one had to check the flag itself; prod 1.17.0 lost
quarantined episodes through one such job after another (the repair, the wanted
scan's cleanup, the translator, the sync). Files flagged while they were still
kept are moved out by :func:`trash_quarantined_on_disk`; a file the trash
cannot take stays and is still guarded by the flag.

The flag records the SHA-256 of the file it was raised on, so only those bytes
are suspect: a replacement saved in the same second is not (an mtime grace
window kept it suspect for good), and the same wrong file saved again is
refused (:func:`is_quarantined_content`).
"""

from __future__ import annotations

import contextlib
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


def invalidate_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _file_digest(path: str) -> str | None:
    """SHA-256 of the file's bytes, or None when it cannot be read.

    Read every time, never memoised: no stat field proves the bytes are the
    same (a rewrite within one timestamp tick with the mtime set back changes
    none of them). Only flagged sidecars are hashed, a handful of small files.
    """
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
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
    if not found[existing] or not is_suspect_sidecar(found[existing]):
        # The answer came from a genuine sidecar, or from an embedded track:
        # an embedded ASS next to an SRT sidecar reads "ass" and must stay so
        # (it read "srt" whenever anything at all was suspect).
        return existing
    for fmt in _SIDECAR_FORMATS:
        if found[fmt] and not is_suspect_sidecar(found[fmt]):
            return fmt
    return None


def is_quarantined_content(path: str, content: bytes) -> bool:
    """True when ``content`` is a file quarantined for the video ``path`` belongs to.

    The flagged file is in the trash, so the duplicate check finds nothing on
    disk to compare against; another provider serving the same bytes would
    otherwise save the wrong subtitle again. Matched per video, not per name:
    the same bytes quarantined as ``.ger.ass`` must not return as ``.de.ass``.
    """
    suspects = _suspects()
    if not suspects:
        return False
    stem = _video_stem_of(path)
    digest = hashlib.sha256(content).hexdigest()
    return any(
        flag.digest == digest
        for flagged, flags in suspects.items()
        if _video_stem_of(flagged) == stem
        for flag in flags
    )


def _put_back(trashed: str, original: str) -> bool:
    """Move ``trashed`` back to ``original`` unless something is there now."""
    from utils.atomic_write import move_no_replace

    try:
        move_no_replace(trashed, original)
    except FileExistsError:
        return False
    with contextlib.suppress(OSError):
        move_no_replace(trashed + ".quality.json", original + ".quality.json")
    return True


def _holds_flagged_bytes(original: str, trashed: str) -> bool:
    """Whether the file moved out of ``original`` is the one that was flagged there."""
    return any(_flag_holds(trashed, flag) for flag in _suspects().get(_norm(original), ()))


def _trash(sidecars: list[str], *, notify: bool = True) -> list[str]:
    """Move ``sidecars`` into one restorable trash batch; returns those quarantined.

    The batch's manifest names a file before the file is moved: a batch
    without one never shows on the trash page, so a move it does not record
    would lose the file. A file whose entry cannot be written is not moved.

    Each file is checked after the move, not before: what was moved is what
    was at the path then, so a replacement saved in between is never taken
    for the quarantined file. It goes straight back, or — if yet another file
    landed there — stays restorable in the batch. Never raises: a file the
    trash refuses stays where it is, still flagged.
    """
    if not sidecars:
        return []
    in_trash: list[dict] = []
    quarantined: list[str] = []
    try:
        import shutil
        import uuid

        from config import get_settings
        from services.sidecar_trash import get_batch_dir, trash_sidecar, write_manifest

        media_path = getattr(get_settings(), "media_path", "/media")
        batch_id = uuid.uuid4().hex
        batch_dir = get_batch_dir(media_path, batch_id)
        for sidecar in sidecars:
            # A fresh batch of one folder's files: no name collides, so this is
            # where trash_sidecar puts it.
            planned = {
                "original": sidecar,
                "trashed": os.path.join(batch_dir, os.path.basename(sidecar)),
            }
            try:
                write_manifest(batch_dir, batch_id, [*in_trash, planned])
            except OSError as exc:
                logger.warning("suspect sidecar: no trash manifest, %s stays: %s", sidecar, exc)
                break
            trashed, error = trash_sidecar(sidecar, media_path, batch_dir)
            if error:
                logger.warning("suspect sidecar: could not trash %s: %s", sidecar, error)
                continue
            entry = {"original": sidecar, "trashed": trashed}
            in_trash.append(entry)
            if _holds_flagged_bytes(sidecar, trashed):
                quarantined.append(sidecar)
                continue
            logger.info("suspect sidecar: %s was replaced meanwhile, putting it back", sidecar)
            if _put_back(trashed, sidecar):
                in_trash.remove(entry)
        if in_trash:
            # Drops the entries of files not moved; a failure here leaves a
            # manifest naming a few files more than the batch holds.
            write_manifest(batch_dir, batch_id, in_trash)
        else:
            shutil.rmtree(batch_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: could not trash %s: %s", sidecars, exc)
    if notify and quarantined:
        _notify(quarantined)
    return quarantined


def _notify(sidecars: list[str]) -> None:
    """Tell the media servers the subtitle is gone (they would keep offering it)."""
    try:
        from providers.download_manager import _video_for_sidecar
        from services.media_server_notify import notify_media_servers_batch

        notify_media_servers_batch([_video_for_sidecar(s) or s for s in sidecars])
    except Exception as exc:  # noqa: BLE001 — a refresh is a courtesy
        logger.debug("suspect sidecar: media server refresh failed: %s", exc)


def _restored_since_flagged(path: str, flags: list[_Flag]) -> bool:
    """The user put the file back (trash restore, rollback) after it was flagged."""
    from services.foreign_tracks.sidecars import _RESTORED, _identify, _latest_origin

    identity = _identify(path)
    if identity is None:
        return False
    origin = _latest_origin(identity[0], identity[1])
    if origin is None or origin.origin != _RESTORED:
        return False
    flagged_at = max(flag.at for flag in flags)
    return _aware(origin.recorded_at) > flagged_at


def trash_quarantined_on_disk() -> int:
    """Move quarantined sidecars still on disk to the trash; returns how many.

    Those are files flagged before quarantine moved them out (1.17.0-rc.10 and
    older) and files the trash refused then. A file the user restored after it
    was flagged is theirs to keep. One trash batch per folder, one media server
    refresh for all of them. Never raises.
    """
    try:
        by_folder: dict[str, list[str]] = {}
        for path, flags in _suspects().items():
            if not os.path.isfile(path) or not is_suspect_sidecar(path):
                continue
            if _restored_since_flagged(path, flags):
                continue
            by_folder.setdefault(os.path.dirname(path), []).append(path)
        moved = [
            sidecar
            for paths in by_folder.values()
            for sidecar in _trash(sorted(paths), notify=False)
        ]
        if moved:
            _notify(moved)
            logger.info("suspect sidecars: moved %d quarantined file(s) to the trash", len(moved))
        return len(moved)
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecars: trashing quarantined files failed: %s", exc)
        return 0


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
        trashed = bool(_trash([subtitle_path]))
        logger.warning(
            "suspect sidecar: %s (%s/%s) does not fit %s — blacklisted, %s, wanted "
            "search requeued: %s",
            subtitle_path,
            download.provider_name,
            download.subtitle_id,
            video,
            "moved to the trash" if trashed else "kept (the trash refused it)",
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


def _standalone_owner(video: str) -> dict:
    """``upsert_wanted_item`` kwargs linking ``video`` to its standalone series
    (folder contains it) or movie (same file), or ``{}``.

    Without them the upsert's update branch overwrote an existing row's
    standalone ids with NULL, and the row vanished from the standalone series
    page and cleanup until the next standalone scan re-adopted it.
    """
    from db.standalone import get_standalone_movies, get_standalone_series

    for movie in get_standalone_movies() or []:
        if movie.get("id") and movie.get("file_path") and _norm(movie["file_path"]) == _norm(video):
            return {"standalone_movie_id": movie["id"], "instance_name": "standalone"}
    best: dict = {}
    best_len = -1
    for series in get_standalone_series() or []:
        folder = series.get("folder_path") or ""
        if series.get("id") and _is_under(video, folder) and len(folder) > best_len:
            best_len = len(folder)
            best = {"standalone_series_id": series["id"], "instance_name": "standalone"}
    return best


def _plain_wanted_row(video: str, language: str) -> None:
    try:
        from db.wanted import upsert_wanted_item

        name = os.path.splitext(os.path.basename(video))[0]
        episode = _EPISODE_RE.search(name)
        try:
            owner = _standalone_owner(video)
        except Exception as exc:  # noqa: BLE001 — a plain row is still better than none
            logger.warning("suspect sidecar: standalone lookup for %s failed: %s", video, exc)
            owner = {}
        # The next scan of the series/movie fills in the arr ids on this row
        # (same file, language and type); standalone owners are linked here.
        upsert_wanted_item(
            item_type="episode" if episode else "movie",
            file_path=video,
            title=name,
            season_episode=episode.group(0).upper() if episode else "",
            target_language=language,
            **owner,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning("suspect sidecar: could not requeue %s/%s: %s", video, language, exc)
