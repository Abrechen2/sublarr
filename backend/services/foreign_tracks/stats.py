"""What the foreign-track sweep has freed — history rows, stats, backfill.

Until 1.15.0-rc.4 a slice's result was only logged, so neither the statistics
page nor the Cleanup tab knew how much the sweep had cleaned. Each slice that
rewrote a file now leaves one ``cleanup_history`` row, the stats endpoint
aggregates those rows, and ``backfill_sweep_history`` recovers the strips made
before the row existed.

``cleanup_history.bytes_freed`` is ``INTEGER`` — int4 on Postgres, max
~2.1 GB. A value above that is split over several rows rather than widening
the column: files and tracks are counted on the first row only, so every sum
over the rows stays exact.
"""

import json
import logging
import os
from datetime import UTC, datetime, timedelta

from db.models.foreign_tracks import (
    STATE_AFFECTED,
    STATE_CLEAN,
    STATE_FAILED,
    STATE_PENDING,
    STATE_STRIPPED,
)

logger = logging.getLogger(__name__)

ACTION_TYPE = "scheduled_foreign_track_sweep"
INT4_MAX = 2_147_483_647
RECENT_DAYS = 30
SCAN_STATES = (STATE_PENDING, STATE_CLEAN, STATE_AFFECTED, STATE_STRIPPED, STATE_FAILED)


def _byte_chunks(total: int) -> list[int]:
    """Split ``total`` into parts that each fit an int4 column (at least one)."""
    total = max(0, int(total))
    chunks = []
    while total > INT4_MAX:
        chunks.append(INT4_MAX)
        total -= INT4_MAX
    chunks.append(total)
    return chunks


def _write_rows(repo, *, rule_id, files: int, bytes_freed: int, details: dict, part_extra: dict):
    """Write one logical history entry, split into int4-sized rows if needed.

    All parts commit together: a half-written split would count its files
    without all of its bytes.
    """
    chunks = _byte_chunks(bytes_freed)
    with repo.batch():
        for index, chunk in enumerate(chunks):
            if index == 0:
                row_details = dict(details)
                row_files = files
            else:
                row_details = dict(part_extra)
                row_files = 0
            if len(chunks) > 1:
                row_details.update({"part": index + 1, "parts": len(chunks)})
            repo.log_cleanup(
                action_type=ACTION_TYPE,
                files_processed=row_files,
                files_deleted=0,
                bytes_freed=chunk,
                details_json=json.dumps(row_details),
                rule_id=rule_id,
            )
    return len(chunks)


def record_slice(result: dict, rule_id, repo=None) -> None:
    """Leave one history entry for a slice that rewrote at least one file.

    Never raises: the sweep's own work is already committed, and bookkeeping
    about it must not turn a successful slice into a failed tick.
    """
    if int(result.get("stripped_files") or 0) <= 0:
        return
    try:
        if repo is None:
            from db.repositories.cleanup import CleanupRepository

            repo = CleanupRepository()
        _write_rows(
            repo,
            rule_id=rule_id,
            files=int(result["stripped_files"]),
            bytes_freed=int(result.get("bytes_freed") or 0),
            details={
                "tracks_removed": int(result.get("tracks_removed") or 0),
                "probed": int(result.get("probed") or 0),
                "phase": result.get("phase"),
                "backups_deleted": int(result.get("backups_deleted") or 0),
                "verify_failed": int(result.get("verify_failed") or 0),
            },
            part_extra={"phase": result.get("phase")},
        )
    except Exception as exc:  # noqa: BLE001 — see docstring
        _rollback_quietly()
        logger.warning(
            "foreign_track_sweep: could not record the slice in cleanup history "
            "(stripped=%s bytes_freed=%s): %s",
            result.get("stripped_files"),
            result.get("bytes_freed"),
            exc,
        )


def _rollback_quietly() -> None:
    # A failed flush leaves the session unusable for the next statement
    # (the scheduler thread keeps the same scoped session).
    try:
        from extensions import db

        db.session.rollback()
    except Exception as exc:  # noqa: BLE001 — already on an error path
        logger.warning("foreign_track_sweep: session rollback failed: %s", exc)


def _as_utc(value) -> datetime | None:
    """Normalise a DB timestamp (aware, naive-UTC or ISO text) to aware UTC."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _details(row: dict) -> dict:
    try:
        parsed = json.loads(row.get("details_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def get_sweep_stats() -> dict:
    """Totals of the sweep's cleanup history plus the live worklist state."""
    from db.repositories.cleanup import CleanupRepository
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository
    from services.foreign_tracks.state import load_state

    rows = CleanupRepository().get_history_for_action(ACTION_TYPE)
    cutoff = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    bytes_total = 0
    bytes_recent = 0
    files = 0
    tracks = 0
    for row in rows:
        freed = int(row.get("bytes_freed") or 0)
        bytes_total += freed
        performed = _as_utc(row.get("performed_at"))
        if performed is not None and performed >= cutoff:
            bytes_recent += freed
        files += int(row.get("files_processed") or 0)
        tracks += int(_details(row).get("tracks_removed") or 0)

    counts = ForeignTrackScanRepository().counts_by_state()
    state = load_state()
    return {
        "files_stripped": files,
        "tracks_removed": tracks,
        "bytes_freed_total": bytes_total,
        "bytes_freed_30d": bytes_recent,
        "scan_counts": {name: int(counts.get(name, 0)) for name in SCAN_STATES},
        "phase": state.phase,
        "paused_reason": state.paused_reason,
    }


def backfill_sweep_history(dry_run: bool = True) -> dict:
    """One-off: record strips made before slices wrote history rows.

    Sums ``size_bytes - current size`` over ``stripped`` scan rows processed
    before the oldest sweep history row (all of them when none exists yet).
    ``size_bytes`` is the pre-strip size — ``mark_stripped`` leaves it alone —
    so the difference is what the rewrite freed. Missing files are skipped, a
    file that grew since is clamped to 0. Writes at most one backfill entry,
    ever: a second call finds it and does nothing.
    """
    from db.repositories.cleanup import CleanupRepository
    from db.repositories.foreign_track_scan import ForeignTrackScanRepository

    cleanup_repo = CleanupRepository()
    history = cleanup_repo.get_history_for_action(ACTION_TYPE)
    if any(_details(row).get("backfill") for row in history):
        return {"written": False, "reason": "already backfilled", "dry_run": dry_run}

    slice_times = [_as_utc(row.get("performed_at")) for row in history]
    slice_times = [t for t in slice_times if t is not None]
    cutoff = min(slice_times) if slice_times else None

    files = 0
    tracks = 0
    freed = 0
    skipped_missing = 0
    for row in ForeignTrackScanRepository().stripped_rows():
        processed = _as_utc(row["processed_at"])
        if cutoff is not None and (processed is None or processed >= cutoff):
            continue
        try:
            current = os.path.getsize(row["path"])
        except OSError:
            skipped_missing += 1
            continue
        files += 1
        tracks += row["track_count"]
        freed += max(0, row["size_bytes"] - current)

    summary = {
        "written": False,
        "dry_run": dry_run,
        "files": files,
        "tracks_removed": tracks,
        "bytes_freed": freed,
        "skipped_missing": skipped_missing,
        "cutoff": cutoff.isoformat() if cutoff else None,
    }
    if dry_run:
        summary["reason"] = "dry run"
        return summary
    if files == 0:
        summary["reason"] = "nothing to backfill"
        return summary

    from services.foreign_tracks.sweep import _find_rule

    rule = _find_rule(cleanup_repo)
    summary["rows"] = _write_rows(
        cleanup_repo,
        rule_id=rule.get("id") if rule else None,
        files=files,
        bytes_freed=freed,
        details={"backfill": True, "files": files, "tracks_removed": tracks},
        part_extra={"backfill": True},
    )
    summary["written"] = True
    logger.info("foreign_track_sweep: history backfill written %s", summary)
    return summary
