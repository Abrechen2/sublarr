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
    from services.sidecar_scan import scan_subtitle_sidecars

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


def _language_name(code: str) -> str:
    from config_language_data import SUPPORTED_LANGUAGES

    for entry in SUPPORTED_LANGUAGES:
        if entry.get("code") == code:
            return entry.get("name", code)
    return code


def _translation_enabled() -> bool:
    """True iff the translation feature is enabled (config flag, DB override →
    Pydantic default). Inlined from routes.translate._helpers to keep the
    services layer free of routes imports (layering contract)."""
    try:
        from db.config import get_config_entry

        value = get_config_entry("translation_enabled")
        if value is None:
            from config import get_settings

            return bool(getattr(get_settings(), "translation_enabled", False))
        return value.lower() in ("true", "1", "yes")
    except Exception:
        return False


def _translate_missing_languages(video_path: str, missing: list[str]) -> None:
    """Generate each missing target language via the translation stack.

    Runs synchronously in the caller's app-context (on-demand path). Raises
    :class:`CombineError` (422) if translation is disabled or fails to produce a
    sidecar — the caller re-resolves sources afterwards and errors if any
    language is still missing, so no partial combined artifact is written.
    """
    from translator import translate_file

    if not _translation_enabled():
        raise CombineError(422, "Translation is disabled — cannot generate missing language(s)")

    for lang in missing:
        try:
            result = translate_file(
                video_path, target_language=lang, target_language_name=_language_name(lang)
            )
        except Exception as exc:
            raise CombineError(422, f"Translation for '{lang}' failed: {exc}") from exc
        if not result or not result.get("success"):
            reason = (result or {}).get("error") or "no translatable source found"
            raise CombineError(422, f"Could not generate '{lang}': {reason}")


def build_combined_path(video_path: str, languages: list[str], fmt: str) -> str:
    """Combined sidecar path: ``<stem>.<lang1>-<lang2>.combined.<fmt>``."""
    base, _ = os.path.splitext(video_path)
    lang_tag = "-".join(languages)
    return f"{base}.{lang_tag}.combined.{fmt}"


def _record_combined(
    out_path: str, language: str, fmt: str, content: bytes, video_path: str
) -> None:
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
            # file_path is the VIDEO path, matching every other source (see
            # mt_provisional.record_mt_output) -- not the combined sidecar's
            # own path.
            file_path=video_path,
            score=0,
            source="combined",
            # A combined file is composed from already-counted sidecars, not a
            # fresh provider fetch — don't inflate downloads_today / success rate
            # (same rule as the MT double-count fix, commit 0a7a9b52).
            record_stats=False,
        )
    except Exception as exc:
        logger.warning("combine: history record failed for %s: %s", out_path, exc)


def combine_for_video(
    video_path: str,
    languages: list[str],
    fmt: str,
    position: dict | None,
    media_roots: list[str],
    translate_missing: bool = False,
) -> dict:
    """Compose ``languages`` for ``video_path`` and write the combined sidecar.

    When ``translate_missing`` is set, any missing target language is generated
    via the translation stack first (synchronously, in the caller's app-context)
    and sources are re-resolved. Every requested language must exist (or be
    generated) as a sidecar. Returns ``{"combined_path", "languages", "format"}``.
    Raises :class:`CombineError` on a still-missing language, a disabled/failed
    translation, an output path outside every media root, or a composition
    failure.
    """
    import security_utils
    from utils.atomic_write import atomic_write_bytes

    present, missing = resolve_combine_sources(video_path, languages)
    if missing and translate_missing:
        _translate_missing_languages(video_path, missing)
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
    _record_combined(out_path, languages[0], fmt, content, video_path)

    return {"combined_path": out_path, "languages": languages, "format": fmt}


def _combined_is_fresh(out_path: str, sources: list[dict]) -> bool:
    """True if a combined file exists and is at least as new as every source."""
    try:
        if not os.path.exists(out_path):
            return False
        out_mtime = os.path.getmtime(out_path)
        return all(
            os.path.exists(s["path"]) and os.path.getmtime(s["path"]) <= out_mtime for s in sources
        )
    except OSError:
        return False


def maybe_auto_combine(
    video_path: str, item: dict | None = None, profile: dict | None = None
) -> dict | None:
    """Automatic per-profile combine, fired after a sidecar lands.

    Composes when the governing profile has ``combine_enabled`` and every
    ``combine_languages`` sidecar is present (never translates — a missing
    language is a silent skip). NEVER raises: the acquisition pipeline must not
    break on a combine failure. Returns the combine result dict when a combined
    file was written, else ``None`` (disabled, missing language, already fresh,
    or error). ``profile`` may be passed directly; otherwise it is resolved from
    ``item``.
    """
    try:
        if profile is None:
            from config import get_settings
            from services.embedded_extractor import resolve_profile_for_item

            profile = resolve_profile_for_item(item or {}, get_settings())
        if not profile or not profile.get("combine_enabled"):
            return None

        languages = profile.get("combine_languages") or []
        if len(languages) < 2:
            return None
        fmt = profile.get("combine_format") or "ass"
        position = profile.get("combine_position")

        present, missing = resolve_combine_sources(video_path, languages)
        if missing:
            logger.debug("auto-combine: skip %s (missing %s)", video_path, ", ".join(missing))
            return None

        out_path = build_combined_path(video_path, languages, fmt)
        if _combined_is_fresh(out_path, present):
            return None

        from services.trash_locations import media_paths

        return combine_for_video(
            video_path, languages, fmt, position, media_paths(), translate_missing=False
        )
    except CombineError as exc:
        logger.info("auto-combine skipped for %s: %s", video_path, exc.message)
        return None
    except Exception as exc:
        logger.warning("auto-combine failed for %s: %s", video_path, exc)
        return None
