"""Persistence + caching for dubtitle detection (roadmap A4 / issue #146).

Stores each detection result keyed by ``file_path`` and invalidated by the
file's mtime, so:

* the UI can render the dubtitle flag without re-running detection, and
* a scheduled sweep skips files it has already classified at the same mtime
  (including the "no dubtitle present" outcome — that is cached too, so an
  expensive Tier-2 pass never repeats on an unchanged file).

All DB failures are swallowed with logging: caching must never break the
detection happy path.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def _file_mtime(file_path: str) -> float | None:
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return None


def get_cached_detection(file_path: str) -> dict | None:
    """Return the cached result dict for ``file_path`` if fresh, else None.

    Freshness = the stored mtime equals the file's current mtime. A changed
    or missing file invalidates the cache.
    """
    mtime = _file_mtime(file_path)
    if mtime is None:
        return None
    try:
        from db.models.core import DubtitleDetection
        from extensions import db

        entry = db.session.get(DubtitleDetection, file_path)
        if entry is None or entry.mtime != mtime:
            return None
        return json.loads(entry.result_json)
    except Exception:
        logger.debug("dubtitle cache: read failed for %s", file_path, exc_info=True)
        return None


def store_detection(file_path: str, result_dict: dict) -> None:
    """Persist ``result_dict`` for ``file_path`` at the current mtime (upsert)."""
    mtime = _file_mtime(file_path)
    if mtime is None:
        return
    try:
        from db.models.core import DubtitleDetection
        from extensions import db

        entry = DubtitleDetection(
            file_path=file_path,
            mtime=mtime,
            dubtitle_sub_index=result_dict.get("dubtitle_sub_index"),
            method=result_dict.get("method", "none"),
            result_json=json.dumps(result_dict),
            detected_at=datetime.now(UTC),
        )
        db.session.merge(entry)
        db.session.commit()
    except Exception:
        logger.debug("dubtitle cache: write failed for %s", file_path, exc_info=True)
        try:
            from extensions import db

            db.session.rollback()
        except Exception:
            pass


def detect_dubtitle_cached(
    file_path: str,
    *,
    automated: bool = False,
    force: bool = False,
    **detect_kwargs,
) -> dict:
    """Return a detection result dict, using the cache when fresh.

    On a cache miss (or ``force=True``) runs :func:`detect_dubtitle`, stores
    the serialized result, and returns it. The returned dict matches the API
    payload shape (see :func:`result_to_dict`).
    """
    if not force:
        cached = get_cached_detection(file_path)
        if cached is not None:
            return cached

    from services.dubtitle.detector import detect_dubtitle, result_to_dict

    result = detect_dubtitle(file_path, automated=automated, **detect_kwargs)
    payload = result_to_dict(result)
    store_detection(file_path, payload)
    return payload
