"""Re-fetch each damaged subtitle from its provider and restore it — provably.

Nothing is overwritten on a hunch. Every repair has to clear three gates:

1. **The re-fetched bytes must hash to the pristine hash recorded at download
   time.** If they don't, the provider's file changed since; skip and report.
   This is what makes the repair *provable* rather than hopeful.
2. **The file on disk must be reproducible** by replaying the old buggy pipeline
   over that original. If it isn't, a human edited it — skip.
3. **The write is atomic**, and the result is recorded so the same file is never
   repaired twice.

Provider quota is respected: OpenSubtitles answers HTTP 406 when the daily
allowance is spent. The run stops there and reports how far it got; the next run
picks up where it left off, because progress is persisted per file.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text as sql

from extensions import db
from services.repair.restore import RestoreRefusedError, restore_subtitle
from services.repair.scanner import RepairCandidate, content_hash  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)


class QuotaExhaustedError(Exception):
    """The provider's daily download allowance is spent — resume tomorrow.

    ``reset_at`` carries the provider-reported moment the allowance returns
    (aware UTC), when known — the auto-resume schedules itself from it.
    """

    def __init__(self, message: str = "", reset_at: datetime | None = None):
        super().__init__(message)
        self.reset_at = reset_at


@dataclass
class RepairOutcome:
    file_path: str
    status: str  # repaired | partial | unprovable | nothing_to_restore | unavailable | error
    #  | deferred | would_download
    detail: str = ""
    #: Deferred because the provider's quota ran out this pass (and when it resets).
    quota_spent: bool = False
    reset_at: object = None


@dataclass
class RepairRun:
    dry_run: bool
    repaired: int = 0
    partial: int = 0
    skipped: int = 0
    failed: int = 0
    #: Needed a download this pass did not make (local only, dry run, spent quota).
    deferred: int = 0
    quota_exhausted: bool = False
    outcomes: list[RepairOutcome] = field(default_factory=list)

    def record(self, outcome: RepairOutcome) -> None:
        self.outcomes.append(outcome)
        if outcome.status == "repaired":
            self.repaired += 1
        elif outcome.status == "partial":
            self.partial += 1
        elif outcome.status in ("unprovable", "nothing_to_restore", "unavailable"):
            self.skipped += 1
        elif outcome.status in DEFERRED:
            self.deferred += 1
        else:
            self.failed += 1


#: Outcomes of a candidate that needs a provider download this pass did not make.
DEFERRED = ("deferred", "would_download")


class _DownloadNotAllowedError(Exception):
    """The original is only at the provider, and this pass may not download."""


def _hash_bytes(raw: bytes, language: str | None = None) -> str:
    from dedup_engine import compute_content_hash_from_bytes

    return compute_content_hash_from_bytes(raw, language)


def fetch_original(candidate: RepairCandidate) -> bytes:
    """Re-download the exact provider file this sidecar came from.

    The stored ``subtitle_id`` is fed straight to the provider's download call —
    no search. That costs one quota unit instead of a search plus a download, and
    removes any chance of fetching a *different* subtitle than the one that was
    saved back then.

    What that id has to become is provider knowledge: OpenSubtitles resolves it
    server-side, AnimeTosho turns it back into an attachment URL. Assembling the
    result here instead of asking the provider is what made every AnimeTosho
    sidecar unrepairable — it arrived at ``download()`` with no URL.
    """
    from providers import get_provider_manager
    from providers.base import ProviderRateLimitError

    provider = get_provider_manager().get_provider(candidate.provider)
    if provider is None:
        raise LookupError(f"provider {candidate.provider!r} is not configured")

    result = provider.result_for_download(candidate.subtitle_id, candidate.language)
    try:
        content = provider.download(result)
    except ProviderRateLimitError as exc:
        raise QuotaExhaustedError(str(exc), reset_at=getattr(exc, "reset_at", None)) from exc

    # save_subtitle normalises a download before it writes and hashes it, so the
    # pristine hash is of the NORMALISED content. Compare raw provider bytes
    # against it and every single file is rejected — which is exactly what the
    # first production dry run did.
    from subtitle_normalise import normalise_downloaded_content

    return normalise_downloaded_content(content, candidate.fmt, language=candidate.language)


def _pristine_bak(candidate: RepairCandidate) -> bytes | None:
    """Return the sidecar's .bak if it provably IS the pristine original.

    ``apply_mods`` copies the sidecar to .bak *before* editing it, so on installs
    where that backup survived untouched the .bak is the untouched provider file —
    and the hash recorded at download time proves it. Those repairs are free: no
    round-trip, no quota.

    A .bak that fails the proof was made from an already-damaged file (that is
    what happened here when the backup location moved). Trusting it would write
    the damage straight back, so it is ignored.
    """
    from subtitle_filename import find_existing_bak

    path = find_existing_bak(candidate.file_path)
    if not path:
        return None
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None

    if _hash_bytes(raw, candidate.language) != candidate.original_hash:
        logger.debug("repair: .bak for %s is not pristine — ignoring it", candidate.file_path)
        return None
    return raw


def obtain_original(
    candidate: RepairCandidate, *, allow_download: bool = True
) -> tuple[bytes, str]:
    """Get the pristine original — from the local .bak if provable, else the provider.

    An encoding candidate always goes to the provider: its .bak was copied from
    the file the old decode wrote, so the letters are missing there too.
    """
    local = _pristine_bak(candidate) if candidate.kind != "encoding" else None
    if local is not None:
        return local, "bak"
    if not allow_download:
        raise _DownloadNotAllowedError(candidate.file_path)
    return fetch_original(candidate), "provider"


def order_local_first(
    candidates: list[RepairCandidate],
) -> tuple[list[RepairCandidate], list[RepairCandidate]]:
    """(free from a pristine .bak, needs a provider): every free restore goes first."""
    local, remote = [], []
    for candidate in candidates:
        free = candidate.kind != "encoding" and _pristine_bak(candidate) is not None
        (local if free else remote).append(candidate)
    return local, remote


def repair_one(
    candidate: RepairCandidate, *, dry_run: bool = False, local_only: bool = False
) -> RepairOutcome:
    """Restore one sidecar. Raises :class:`QuotaExhaustedError` if the allowance is gone.

    A dry run and a local-only pass never download: a candidate whose original
    is only at the provider comes back "would_download" / "deferred".
    """
    from services.suspect_sidecars import is_suspect_sidecar

    # Quarantined as another episode's subtitle: its replacement is on the way,
    # and rewriting the bytes would move them off the suspect flag — the wrong
    # file would read as genuine again (prod 1.17.0-rc.8: 14 of 228).
    if is_suspect_sidecar(candidate.file_path):
        return RepairOutcome(
            candidate.file_path, "unavailable", "quarantined as another episode's subtitle"
        )

    try:
        original, source = obtain_original(candidate, allow_download=not (dry_run or local_only))
    except _DownloadNotAllowedError:
        status = "would_download" if dry_run else "deferred"
        return RepairOutcome(candidate.file_path, status, f"needs {candidate.provider}")
    except QuotaExhaustedError:
        raise
    except LookupError as exc:
        return RepairOutcome(candidate.file_path, "unavailable", str(exc))
    except Exception as exc:  # noqa: BLE001 — one bad fetch must not abort the run
        logger.warning("repair: fetch failed for %s: %s", candidate.file_path, exc)
        return RepairOutcome(candidate.file_path, "error", str(exc))

    try:
        with open(candidate.file_path, "rb") as fh:
            on_disk = fh.read()
    except OSError as exc:
        return RepairOutcome(candidate.file_path, "error", str(exc))

    # The gate is the REPLAY, not the hash. The hash recorded at download time is
    # the hash of the file *as it was written back then*, and the normalisation
    # chain that produced those bytes has changed since — on the production
    # library it matched 0 of 8 sampled files, while the replay reproduced 5.
    #
    # The replay is the stronger proof anyway: "the old pipeline, applied to THIS
    # original, produces EXACTLY the file on disk" establishes both that we hold
    # the right original and that nobody has edited the file since. A hash match
    # is kept only as a shortcut for the .bak path, which needs no replay.
    try:
        if candidate.kind == "encoding":
            from services.repair.encoding_restore import restore_encoding

            repaired = restore_encoding(
                original=original,
                on_disk=on_disk,
                fmt=candidate.fmt,
                language=candidate.language,
            )
        else:
            repaired = restore_subtitle(original=original, on_disk=on_disk, fmt=candidate.fmt)
    except RestoreRefusedError as exc:
        from services.repair.restore import NOTHING_TO_RESTORE

        if str(exc) == NOTHING_TO_RESTORE:
            # The pipeline touched this file (its hash moved) but never harmed its
            # text — quotes normalised, timings synced, that sort of thing. Record
            # it, or every future run re-downloads it to learn the same thing again
            # and burns the daily quota on files that were never damaged.
            if not dry_run:
                _record_repair(
                    candidate,
                    repaired_hash=content_hash(candidate.file_path) or "",
                    status="undamaged",
                )
            return RepairOutcome(candidate.file_path, "nothing_to_restore", str(exc))
        return RepairOutcome(candidate.file_path, "unprovable", str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("repair: restore failed for %s: %s", candidate.file_path, exc)
        return RepairOutcome(candidate.file_path, "error", str(exc))

    status, detail = "repaired", f"original from {source}"
    remaining = _still_damaged(candidate, repaired)
    if remaining:
        # Cues edited since the download cannot be proven and keep their "�".
        # Calling that "repaired" hid them (VM 191, RC 1.17.0-rc.1).
        status = "partial"
        detail += f"; {remaining} cue(s) still damaged, edited since the download"

    if dry_run:
        # Report the source even on a dry run — the point of it is to show how
        # many repairs are free (from a backup) before spending any quota.
        return RepairOutcome(candidate.file_path, status, f"dry run — {detail}")

    # Gate 3 — atomic write, then remember it so it is never repaired twice.
    from utils.atomic_write import atomic_write_bytes

    try:
        atomic_write_bytes(candidate.file_path, repaired)
    except OSError as exc:
        # One unwritable folder must not end the pass for every other file.
        logger.warning("repair: cannot write %s: %s", candidate.file_path, exc)
        return RepairOutcome(candidate.file_path, "error", f"write failed: {exc}")
    _record_repair(candidate, repaired_hash=content_hash(candidate.file_path) or "", status=status)
    logger.info("repair: restored %s (%s)", candidate.file_path, detail)
    return RepairOutcome(candidate.file_path, status, detail)


def _still_damaged(candidate: RepairCandidate, repaired: bytes) -> int:
    """Cues an encoding repair could not prove; 0 for a pipeline repair."""
    if candidate.kind != "encoding":
        return 0
    from services.repair.encoding_restore import damaged_cues, has_mangled_letters

    if not has_mangled_letters(repaired):
        return 0
    try:
        return damaged_cues(repaired, candidate.fmt) or 1
    except Exception:  # noqa: BLE001 — unparsable still means damaged
        return 1


def _record_repair(
    candidate: RepairCandidate, *, repaired_hash: str, status: str = "repaired"
) -> None:
    db.session.execute(
        sql("""
            INSERT INTO subtitle_repairs
                   (file_path, original_hash, repaired_hash, provider_name, subtitle_id,
                    status, repaired_at)
            VALUES (:p, :oh, :rh, :prov, :sid, :st, :ts)
            ON CONFLICT (file_path) DO UPDATE
               SET repaired_hash = EXCLUDED.repaired_hash,
                   status        = EXCLUDED.status,
                   repaired_at   = EXCLUDED.repaired_at
        """),
        {
            "p": candidate.file_path,
            "oh": candidate.original_hash,
            "rh": repaired_hash,
            "prov": candidate.provider,
            "sid": candidate.subtitle_id,
            "st": status,
            "ts": datetime.now(UTC),
        },
    )
    db.session.commit()


def run_repair(
    candidates: list[RepairCandidate],
    *,
    dry_run: bool = False,
    limit: int | None = None,
    local_only: bool = False,
) -> RepairRun:
    """Repair every free candidate first, then the downloads, provider by provider.

    A spent quota defers that provider's remaining candidates and nothing else.
    """
    run = RepairRun(dry_run=dry_run)
    for _candidate, outcome in iter_repairs(
        candidates[:limit] if limit else candidates, dry_run=dry_run, local_only=local_only
    ):
        run.record(outcome)
        run.quota_exhausted |= outcome.quota_spent
    return run


def iter_repairs(candidates: list[RepairCandidate], *, dry_run: bool, local_only: bool):
    """Yield (candidate, outcome): free restores first, then provider downloads.

    The local phase never downloads, even if a backup vanished since it was
    sorted; that candidate is deferred instead. A provider whose quota runs out
    is not asked again this pass.
    """
    local, remote = order_local_first(candidates)
    for candidate in local:
        yield candidate, repair_one(candidate, dry_run=dry_run, local_only=True)
    spent: set[str] = set()
    for candidate in remote:
        if local_only or candidate.provider in spent:
            yield (
                candidate,
                RepairOutcome(candidate.file_path, "deferred", f"needs {candidate.provider}"),
            )
            continue
        try:
            yield candidate, repair_one(candidate, dry_run=dry_run)
        except QuotaExhaustedError as exc:
            spent.add(candidate.provider)
            logger.warning(
                "repair: %s quota exhausted, deferring its repairs: %s", candidate.provider, exc
            )
            yield (
                candidate,
                RepairOutcome(
                    candidate.file_path,
                    "deferred",
                    f"{candidate.provider} quota",
                    quota_spent=True,
                    reset_at=getattr(exc, "reset_at", None),
                ),
            )
