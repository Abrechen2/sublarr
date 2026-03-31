# -*- coding: utf-8 -*-
"""
check_datetime_migration.py - Sublarr timestamp migration consistency check

Usage:
    python scripts/check_datetime_migration.py --db /path/to/sublarr.db --mode before
    python scripts/check_datetime_migration.py --db /path/to/sublarr.db --mode after

Modes:
    before  -verifies existing data is in ISO format ("T" + "+00:00" / "Z")
              and saves a snapshot to .migration-snapshot.json alongside the DB
    after   -verifies all timestamps are in SQLAlchemy format ("space", no offset)
              and compares row counts + non-null counts against the snapshot

Exit codes:
    0 -all checks passed
    1 -one or more checks failed (see output for details)
"""

import argparse
import io
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─── Column registry (mirrors migration file exactly) ────────────────────────

COLUMNS: list[tuple[str, str, bool]] = [
    ("jobs", "created_at", False),
    ("jobs", "completed_at", True),
    ("config_entries", "updated_at", False),
    ("wanted_items", "last_search_at", True),
    ("wanted_items", "added_at", False),
    ("wanted_items", "updated_at", False),
    ("wanted_items", "retry_after", True),
    ("upgrade_history", "upgraded_at", False),
    ("language_profiles", "created_at", False),
    ("language_profiles", "updated_at", False),
    ("ffprobe_cache", "cached_at", False),
    ("chapter_cache", "cached_at", False),
    ("blacklist_entries", "added_at", False),
    ("filter_presets", "created_at", False),
    ("filter_presets", "updated_at", False),
    ("anidb_absolute_mappings", "updated_at", False),
    ("series_settings", "updated_at", False),
    ("fansub_preferences", "updated_at", False),
    ("subtitle_hashes", "last_scanned", False),
    ("cleanup_rules", "last_run_at", True),
    ("cleanup_rules", "created_at", False),
    ("cleanup_rules", "updated_at", False),
    ("cleanup_history", "performed_at", False),
    ("hook_configs", "last_triggered_at", True),
    ("hook_configs", "created_at", False),
    ("hook_configs", "updated_at", False),
    ("webhook_configs", "last_triggered_at", True),
    ("webhook_configs", "created_at", False),
    ("webhook_configs", "updated_at", False),
    ("hook_log", "triggered_at", False),
    ("notification_templates", "created_at", False),
    ("notification_templates", "updated_at", False),
    ("notification_history", "sent_at", False),
    ("quiet_hours_config", "created_at", False),
    ("quiet_hours_config", "updated_at", False),
    ("provider_cache", "cached_at", False),
    ("provider_cache", "expires_at", False),
    ("subtitle_downloads", "downloaded_at", False),
    ("provider_stats", "last_success_at", True),
    ("provider_stats", "last_failure_at", True),
    ("provider_stats", "updated_at", False),
    ("provider_stats", "disabled_until", True),
    ("provider_score_modifiers", "updated_at", False),
    ("scoring_weights", "updated_at", False),
    ("watched_folders", "last_scan_at", True),
    ("watched_folders", "created_at", False),
    ("watched_folders", "updated_at", False),
    ("standalone_series", "created_at", False),
    ("standalone_series", "updated_at", False),
    ("standalone_movies", "created_at", False),
    ("standalone_movies", "updated_at", False),
    ("metadata_cache", "cached_at", False),
    ("metadata_cache", "expires_at", False),
    ("anidb_mappings", "created_at", True),
    ("anidb_mappings", "last_used", True),
    ("translation_config_history", "first_used_at", False),
    ("translation_config_history", "last_used_at", False),
    ("glossary_entries", "created_at", False),
    ("glossary_entries", "updated_at", False),
    ("prompt_presets", "created_at", False),
    ("prompt_presets", "updated_at", False),
    ("translation_backend_stats", "last_success_at", True),
    ("translation_backend_stats", "last_failure_at", True),
    ("translation_backend_stats", "updated_at", False),
    ("whisper_jobs", "created_at", False),
    ("whisper_jobs", "started_at", True),
    ("whisper_jobs", "completed_at", True),
    ("translation_memory", "created_at", False),
    ("installed_plugins", "installed_at", False),
    ("marketplace_cache", "last_fetched", False),
]

# ─── Format patterns ──────────────────────────────────────────────────────────

# Before migration: ISO 8601 with T separator and +00:00 or Z suffix
_RE_BEFORE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$"
)

# After migration: space separator, no timezone suffix
_RE_AFTER = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?$"
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _column_exists(cur: sqlite3.Cursor, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())


def _fetch_values(
    cur: sqlite3.Cursor, table: str, col: str
) -> list[str | None]:
    cur.execute(f"SELECT {col} FROM {table}")  # noqa: S608
    return [row[0] for row in cur.fetchall()]


def _count_non_null(values: list[str | None]) -> int:
    return sum(1 for v in values if v is not None)


def _snapshot_path(db_path: Path) -> Path:
    return db_path.parent / f".migration-snapshot-{db_path.stem}.json"


# ─── Mode: before ────────────────────────────────────────────────────────────


def run_before(db_path: Path) -> int:
    print(f"\n{'-'*60}")
    print(f"PRE-MIGRATION CHECK -{db_path}")
    print(f"{'='*60}\n")

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    snapshot: dict[str, dict[str, int]] = {}
    errors: list[str] = []
    skipped: list[str] = []
    total_rows = 0
    bad_format_count = 0

    for table, col, nullable in COLUMNS:
        key = f"{table}.{col}"

        if not _table_exists(cur, table):
            skipped.append(f"  SKIP  {key} (table does not exist yet)")
            continue
        if not _column_exists(cur, table, col):
            skipped.append(f"  SKIP  {key} (column does not exist yet)")
            continue

        values = _fetch_values(cur, table, col)
        non_null = _count_non_null(values)
        snapshot[key] = {"total": len(values), "non_null": non_null}
        total_rows += len(values)

        # Check format of all non-null values
        bad: list[str] = []
        for v in values:
            if v is None:
                continue
            if v == "":
                # Empty strings will become NULL after migration -acceptable
                continue
            if not _RE_BEFORE.match(v):
                bad.append(v)

        if bad:
            bad_format_count += len(bad)
            sample = bad[:3]
            errors.append(
                f"  WARN  {key}: {len(bad)} values with unexpected format -"
                f"sample: {sample}"
            )
        else:
            null_info = f"({non_null}/{len(values)} non-null)"
            print(f"  OK    {key} {null_info}")

    con.close()

    if skipped:
        print()
        for s in skipped:
            print(s)

    if errors:
        print()
        for e in errors:
            print(e)
        print(
            f"\n  {bad_format_count} values with unexpected pre-migration format."
        )
        print("  These will still be reformatted -check the samples above.")

    # Save snapshot regardless of format warnings (migration can still proceed)
    snap_path = _snapshot_path(db_path)
    snap_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(),
                "db_path": str(db_path),
                "columns": snapshot,
            },
            indent=2,
        )
    )
    print(f"\n  Snapshot saved -> {snap_path}")
    print(f"  Total rows checked: {total_rows}")

    if errors:
        print(
            "\n  Result: WARNINGS (non-fatal -migration can proceed, "
            "but review samples above)\n"
        )
        return 0  # Warnings only, not fatal
    else:
        print("\n  Result: PASS -all formats look correct for migration\n")
        return 0


# ─── Mode: after ─────────────────────────────────────────────────────────────


def run_after(db_path: Path) -> int:
    print(f"\n{'-'*60}")
    print(f"POST-MIGRATION CHECK -{db_path}")
    print(f"{'='*60}\n")

    snap_path = _snapshot_path(db_path)
    snapshot: dict[str, dict[str, int]] | None = None
    if snap_path.exists():
        try:
            data = json.loads(snap_path.read_text())
            snapshot = data.get("columns", {})
            print(f"  Snapshot loaded from {snap_path}")
            print(f"  Snapshot taken at: {data.get('created_at', 'unknown')}\n")
        except Exception as exc:
            print(f"  WARNING: Could not load snapshot ({exc}) -skipping row count comparison\n")
    else:
        print(f"  WARNING: No snapshot found at {snap_path} -skipping row count comparison\n")

    con = sqlite3.connect(str(db_path))
    cur = con.cursor()

    errors: list[str] = []
    skipped: list[str] = []
    total_ok = 0
    total_rows = 0

    for table, col, nullable in COLUMNS:
        key = f"{table}.{col}"

        if not _table_exists(cur, table):
            skipped.append(f"  SKIP  {key} (table does not exist)")
            continue
        if not _column_exists(cur, table, col):
            skipped.append(f"  SKIP  {key} (column does not exist)")
            continue

        values = _fetch_values(cur, table, col)
        non_null = _count_non_null(values)
        total_rows += len(values)

        # ── 1. Row count must match snapshot ──────────────────────────────
        if snapshot and key in snapshot:
            expected_total = snapshot[key]["total"]
            if len(values) != expected_total:
                errors.append(
                    f"  FAIL  {key}: row count changed "
                    f"({expected_total} -> {len(values)})"
                )

        # ── 2. Non-null count: nullable cols may gain NULLs (empty->NULL) ──
        if snapshot and key in snapshot:
            expected_non_null = snapshot[key]["non_null"]
            if non_null > expected_non_null:
                errors.append(
                    f"  FAIL  {key}: non-null count increased "
                    f"({expected_non_null} -> {non_null}) -unexpected new values"
                )
            elif non_null < expected_non_null and not nullable:
                errors.append(
                    f"  FAIL  {key}: non-null count decreased on NOT NULL column "
                    f"({expected_non_null} -> {non_null})"
                )

        # ── 3. Format check: no T or +00:00 / Z remaining ─────────────────
        bad_old_format: list[str] = []
        bad_new_format: list[str] = []
        for v in values:
            if v is None:
                continue
            if "T" in v or "+00:00" in v or v.endswith("Z"):
                bad_old_format.append(v)
            elif not _RE_AFTER.match(v):
                bad_new_format.append(v)

        if bad_old_format:
            errors.append(
                f"  FAIL  {key}: {len(bad_old_format)} values still in old ISO format "
                f"— sample: {bad_old_format[:3]}"
            )
        elif bad_new_format:
            errors.append(
                f"  FAIL  {key}: {len(bad_new_format)} values with unrecognized format "
                f"— sample: {bad_new_format[:3]}"
            )
        else:
            null_info = f"({non_null}/{len(values)} non-null)"
            print(f"  OK    {key} {null_info}")
            total_ok += 1

    con.close()

    if skipped:
        print()
        for s in skipped:
            print(s)

    if errors:
        print()
        for e in errors:
            print(e)
        print(f"\n  Result: FAIL -{len(errors)} issue(s) found\n")
        return 1
    else:
        print(f"\n  Result: PASS -{total_ok} columns verified, {total_rows} total rows\n")
        return 0


# ─── Entry point ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check DB timestamp format before/after Alembic migration b0c1d2e3f4a5"
    )
    parser.add_argument(
        "--db",
        required=True,
        help="Path to sublarr.db (e.g. /config/sublarr.db or a local copy)",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["before", "after"],
        help="'before' = verify + snapshot; 'after' = verify + compare snapshot",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(2)

    if args.mode == "before":
        sys.exit(run_before(db_path))
    else:
        sys.exit(run_after(db_path))


if __name__ == "__main__":
    main()
