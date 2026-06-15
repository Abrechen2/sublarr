"""Scheduled dubtitle-detection sweep (roadmap A4 / issue #146).

Unattended **Level 1** automation: when ``dubtitle_detection`` is enabled,
periodically classify the dubtitle on library files that ship several
embedded English subtitle tracks, and persist the result (flag only — no
file is modified). The track panel then shows the flag on load without the
user clicking "Detect".

Design notes:
* **Gated** — no-op unless ``dubtitle_detection`` is on (off by default).
* **Only-on-ambiguous** — Tier-2 (Whisper) only fires for files with ≥2
  English subtitle tracks; single-track files are skipped before any probe
  cost beyond ffprobe (which is itself cached).
* **Cached** — files with a fresh cached result (same mtime) are skipped, so
  a daily sweep never re-Whispers an unchanged file.
* **Bounded** — at most ``_BATCH_CAP`` newly-detected files per run, so one
  sweep can't saturate the Whisper backend or run unbounded.
* **automated=True** — applies the stricter margin + cue-floor guardrails.

Module-level ``dubtitle_scan_tick`` is picklable (no closures) per the
SQLAlchemyJobStore requirement for scheduler jobs.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_BATCH_CAP = 200  # max files newly detected per sweep run


def _candidate_file_paths(limit: int) -> list[str]:
    """Distinct on-disk video paths from wanted_items, capped at ``limit``."""
    try:
        from sqlalchemy import text as _text

        from db import get_db

        db = get_db()
        rows = db.execute(
            _text(
                "SELECT DISTINCT file_path FROM wanted_items "
                "WHERE file_path IS NOT NULL AND file_path != '' "
                "ORDER BY file_path LIMIT :lim"
            ),
            {"lim": limit},
        ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        logger.debug("dubtitle sweep: candidate query failed", exc_info=True)
        return []


def dubtitle_scan_tick() -> dict:
    """Classify dubtitles across multi-EN-track library files (flag only).

    Returns a small stats dict for the scheduler run history.
    """
    from config import get_settings, map_path

    settings = get_settings()
    if not bool(getattr(settings, "dubtitle_detection", False)):
        logger.debug("dubtitle sweep: disabled (dubtitle_detection off) — skipping")
        return {"enabled": False, "processed": 0, "skipped": 0}

    from ass_utils import get_media_streams
    from services.dubtitle import detect_dubtitle_cached, get_cached_detection
    from services.dubtitle.detector import _english_subtitle_streams

    # Probe a generous superset; we stop after _BATCH_CAP *new* detections.
    paths = _candidate_file_paths(_BATCH_CAP * 8)
    processed = 0
    skipped = 0
    for raw in paths:
        if processed >= _BATCH_CAP:
            break
        path = map_path(raw)
        if not os.path.exists(path):
            skipped += 1
            continue
        # Fresh cache → nothing to do (covers the unchanged-file fast path).
        if get_cached_detection(path) is not None:
            skipped += 1
            continue
        try:
            probe = get_media_streams(path, use_cache=True)
        except Exception:
            logger.debug("dubtitle sweep: probe failed for %s", path, exc_info=True)
            skipped += 1
            continue
        # Only-on-ambiguous: a file with <2 English subtitle tracks can't have a
        # mislabeled-dubtitle problem worth a (potentially Whisper-backed) pass.
        if len(_english_subtitle_streams(probe)) < 2:
            skipped += 1
            continue
        try:
            detect_dubtitle_cached(path, automated=True, probe_data=probe)
            processed += 1
        except Exception:
            logger.warning("dubtitle sweep: detection failed for %s", path, exc_info=True)
            skipped += 1

    if processed:
        logger.info("dubtitle sweep: detected %d file(s), skipped %d", processed, skipped)
    return {"enabled": True, "processed": processed, "skipped": skipped}
