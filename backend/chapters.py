"""Chapter extraction and caching for MKV/MP4 video files.

Provides get_chapters(video_path) -> list of chapter dicts with millisecond timestamps.
Results are cached in chapter_cache DB table (invalidated by file mtime).
"""

import json
import logging
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)


def get_chapters(video_path: str) -> list[dict]:
    """Return chapter list for a video file.

    Checks chapter_cache first (mtime-validated). On miss, runs ffprobe and caches.
    Returns [] if the file has no chapters or ffprobe is unavailable.
    """
    import os

    try:
        mtime = os.path.getmtime(video_path)
    except OSError:
        return []

    cached = _get_cached(video_path, mtime)
    if cached is not None:
        return cached

    chapters = _probe_chapters(video_path)
    _set_cached(video_path, mtime, chapters)
    return chapters


def _probe_chapters(video_path: str) -> list[dict]:
    """Run ffprobe -show_chapters and return normalized chapter list."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", video_path],
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(result.stdout or "{}")
        return [_normalize_chapter(c) for c in data.get("chapters", [])]
    except Exception as exc:
        logger.debug("Chapter probe failed for %s: %s", video_path, exc)
        return []


def _normalize_chapter(raw: dict) -> dict:
    """Convert raw ffprobe chapter dict to {id, title, start_ms, end_ms}."""
    idx = raw["id"]
    title = raw.get("tags", {}).get("title") or f"Chapter {idx + 1}"
    return {
        "id": idx,
        "title": title,
        "start_ms": int(float(raw["start_time"]) * 1000),
        "end_ms": int(float(raw["end_time"]) * 1000),
    }


def _get_cached(file_path: str, mtime: float) -> list[dict] | None:
    """Return cached chapters if mtime matches, else None."""
    from db.models.core import ChapterCache
    from extensions import db

    row = db.session.get(ChapterCache, file_path)
    if row is None or row.mtime != mtime:
        return None
    return json.loads(row.chapters_json)


def _set_cached(file_path: str, mtime: float, chapters: list[dict]) -> None:
    """Write chapters to chapter_cache (upsert)."""
    from db.models.core import ChapterCache
    from extensions import db

    now = datetime.utcnow().isoformat()
    existing = db.session.get(ChapterCache, file_path)
    if existing:
        existing.mtime = mtime
        existing.chapters_json = json.dumps(chapters)
        existing.cached_at = now
    else:
        db.session.add(
            ChapterCache(
                file_path=file_path,
                mtime=mtime,
                chapters_json=json.dumps(chapters),
                cached_at=now,
            )
        )
    db.session.commit()
