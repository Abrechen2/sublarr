"""Orchestration for combined/bilingual subtitles (V1.6 Feature #1).

Bridges the pure composition engine (``services.subtitle_combine``) to the
filesystem + DB: resolves the best sidecar per requested language (source
priority), composes them, writes the combined sidecar atomically inside a
configured media root, and records it as a managed ``source="combined"``
subtitle row (mirroring the manual-upload save path).

The ``translate_missing`` on-demand path (generate a missing language via the
translation stack, then combine) is a separate follow-on — this module composes
only what already exists on disk and raises :class:`CombineError` (422) when a
requested language is missing.
"""

from __future__ import annotations

import logging
import os

from services.subtitle_combine import CombineError, combine_subtitles, pick_best_sidecar

logger = logging.getLogger(__name__)


def resolve_combine_sources(video_path: str, languages: list[str]) -> tuple[list[dict], list[str]]:
    """Split ``languages`` into (present_inputs, missing).

    ``present_inputs`` are ``{"language", "path", "format"}`` dicts ordered to
    match ``languages`` (primary first), each the best sidecar for that language
    by ``plain > hi > forced`` priority.
    """
    from routes.subtitles.helpers import scan_subtitle_sidecars

    by_lang: dict[str, list[dict]] = {}
    for side in scan_subtitle_sidecars(video_path):
        by_lang.setdefault(side.get("language"), []).append(side)

    present: list[dict] = []
    missing: list[str] = []
    for lang in languages:
        best = pick_best_sidecar(by_lang.get(lang, []))
        if best is None:
            missing.append(lang)
        else:
            present.append({"language": lang, "path": best["path"], "format": best["format"]})
    return present, missing


def build_combined_path(video_path: str, languages: list[str], fmt: str) -> str:
    """Combined sidecar path: ``<stem>.<lang1>-<lang2>.combined.<fmt>``."""
    base, _ = os.path.splitext(video_path)
    lang_tag = "-".join(languages)
    return f"{base}.{lang_tag}.combined.{fmt}"


def _record_combined(out_path: str, language: str, fmt: str, content: bytes) -> None:
    """Register hash + history row for a written combined sidecar.

    Mirrors ``services.subtitle_upload.save_manual_subtitle`` — failures here
    must never lose the written file, but are logged (never silently swallowed).
    """
    try:
        from db.repositories.cleanup import CleanupRepository
        from dedup_engine import compute_content_hash_from_bytes

        content_hash = compute_content_hash_from_bytes(content)
        CleanupRepository().upsert_hash(
            file_path=out_path,
            content_hash=content_hash,
            file_size=len(content),
            format=fmt,
            language=language,
        )
    except Exception as exc:
        try:
            from extensions import db as _db

            _db.session.rollback()
        except Exception:
            pass
        logger.warning("combine: hash registration failed for %s: %s", out_path, exc)

    try:
        from db.providers import record_subtitle_download

        record_subtitle_download(
            provider_name="combined",
            subtitle_id=f"combined:{os.path.basename(out_path)}",
            language=language,
            fmt=fmt,
            file_path=out_path,
            score=0,
            source="combined",
        )
    except Exception as exc:
        logger.warning("combine: history record failed for %s: %s", out_path, exc)


def combine_for_video(
    video_path: str,
    languages: list[str],
    fmt: str,
    position: dict | None,
    media_roots: list[str],
) -> dict:
    """Compose ``languages`` for ``video_path`` and write the combined sidecar.

    Every requested language must already exist as a sidecar. Returns
    ``{"combined_path", "languages", "format"}``. Raises :class:`CombineError`
    on missing languages, an output path outside every media root, or any
    composition failure.
    """
    import security_utils
    from utils.atomic_write import atomic_write_bytes

    present, missing = resolve_combine_sources(video_path, languages)
    if missing:
        raise CombineError(422, "Missing subtitle language(s): " + ", ".join(missing))

    content = combine_subtitles(present, fmt, position)

    out_path = build_combined_path(video_path, languages, fmt)
    media_root = next(
        (root for root in media_roots if security_utils.is_safe_path(out_path, root)), None
    )
    if media_root is None:
        raise CombineError(400, "Resolved combined path is outside the media directory")

    atomic_write_bytes(out_path, content)
    _record_combined(out_path, languages[0], fmt, content)

    return {"combined_path": out_path, "languages": languages, "format": fmt}
