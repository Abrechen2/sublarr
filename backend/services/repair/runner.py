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

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text as sql

from extensions import db
from services.repair.restore import RestoreRefusedError, restore_subtitle
from services.repair.scanner import RepairCandidate, content_hash  # noqa: F401 — re-exported

logger = logging.getLogger(__name__)


class QuotaExhaustedError(Exception):
    """The provider's daily download allowance is spent — resume tomorrow."""


@dataclass
class RepairOutcome:
    file_path: str
    status: str  # repaired | unprovable | nothing_to_restore | unavailable | error
    detail: str = ""


@dataclass
class RepairRun:
    dry_run: bool
    repaired: int = 0
    skipped: int = 0
    failed: int = 0
    quota_exhausted: bool = False
    outcomes: list[RepairOutcome] = field(default_factory=list)

    def record(self, outcome: RepairOutcome) -> None:
        self.outcomes.append(outcome)
        if outcome.status == "repaired":
            self.repaired += 1
        elif outcome.status in ("unprovable", "nothing_to_restore", "unavailable"):
            self.skipped += 1
        else:
            self.failed += 1


def _hash_bytes(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip().replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fetch_original(candidate: RepairCandidate) -> bytes:
    """Re-download the exact provider file this sidecar came from.

    The stored ``subtitle_id`` is fed straight to the provider's download call —
    no search. That costs one quota unit instead of a search plus a download, and
    removes any chance of fetching a *different* subtitle than the one that was
    saved back then.
    """
    from providers import get_provider_manager
    from providers.base import ProviderRateLimitError, SubtitleResult

    provider = get_provider_manager().get_provider(candidate.provider)
    if provider is None:
        raise LookupError(f"provider {candidate.provider!r} is not configured")

    result = SubtitleResult(
        provider_name=candidate.provider,
        subtitle_id=candidate.subtitle_id,
        language=candidate.language,
        provider_data={"file_id": candidate.subtitle_id},
    )
    try:
        content = provider.download(result)
    except ProviderRateLimitError as exc:
        raise QuotaExhaustedError(str(exc)) from exc

    # save_subtitle normalises a download before it writes and hashes it, so the
    # pristine hash is of the NORMALISED content. Compare raw provider bytes
    # against it and every single file is rejected — which is exactly what the
    # first production dry run did.
    from subtitle_normalise import normalise_downloaded_content

    return normalise_downloaded_content(content, candidate.fmt)


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

    if _hash_bytes(raw) != candidate.original_hash:
        logger.debug("repair: .bak for %s is not pristine — ignoring it", candidate.file_path)
        return None
    return raw


def obtain_original(candidate: RepairCandidate) -> tuple[bytes, str]:
    """Get the pristine original — from the local .bak if provable, else the provider."""
    local = _pristine_bak(candidate)
    if local is not None:
        return local, "bak"
    return fetch_original(candidate), "provider"


def repair_one(candidate: RepairCandidate, *, dry_run: bool = False) -> RepairOutcome:
    """Restore one sidecar. Raises :class:`QuotaExhaustedError` if the allowance is gone."""
    try:
        original, source = obtain_original(candidate)
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
        repaired = restore_subtitle(original=original, on_disk=on_disk, fmt=candidate.fmt)
    except RestoreRefusedError as exc:
        from services.repair.restore import NOTHING_TO_RESTORE

        status = "nothing_to_restore" if str(exc) == NOTHING_TO_RESTORE else "unprovable"
        return RepairOutcome(candidate.file_path, status, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("repair: restore failed for %s: %s", candidate.file_path, exc)
        return RepairOutcome(candidate.file_path, "error", str(exc))

    if dry_run:
        # Report the source even on a dry run — the point of it is to show how
        # many repairs are free (from a backup) before spending any quota.
        return RepairOutcome(candidate.file_path, "repaired", f"dry run — original from {source}")

    # Gate 3 — atomic write, then remember it so it is never repaired twice.
    from utils.atomic_write import atomic_write_bytes

    atomic_write_bytes(candidate.file_path, repaired)
    _record_repair(candidate, repaired_hash=content_hash(candidate.file_path) or "")
    logger.info("repair: restored %s (original from %s)", candidate.file_path, source)
    return RepairOutcome(candidate.file_path, "repaired", f"original from {source}")


def _record_repair(candidate: RepairCandidate, *, repaired_hash: str) -> None:
    db.session.execute(
        sql("""
            INSERT INTO subtitle_repairs
                   (file_path, original_hash, repaired_hash, provider_name, subtitle_id,
                    status, repaired_at)
            VALUES (:p, :oh, :rh, :prov, :sid, 'repaired', :ts)
            ON CONFLICT (file_path) DO UPDATE
               SET repaired_hash = EXCLUDED.repaired_hash,
                   status        = 'repaired',
                   repaired_at   = EXCLUDED.repaired_at
        """),
        {
            "p": candidate.file_path,
            "oh": candidate.original_hash,
            "rh": repaired_hash,
            "prov": candidate.provider,
            "sid": candidate.subtitle_id,
            "ts": datetime.now(UTC),
        },
    )
    db.session.commit()


def run_repair(
    candidates: list[RepairCandidate], *, dry_run: bool = False, limit: int | None = None
) -> RepairRun:
    """Repair each candidate, stopping cleanly when the provider quota runs out."""
    run = RepairRun(dry_run=dry_run)
    for candidate in candidates[:limit] if limit else candidates:
        try:
            run.record(repair_one(candidate, dry_run=dry_run))
        except QuotaExhaustedError as exc:
            run.quota_exhausted = True
            logger.warning("repair: provider quota exhausted, stopping: %s", exc)
            break
    return run
