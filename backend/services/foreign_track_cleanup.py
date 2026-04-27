"""Policy + trigger glue for foreign-track cleanup (0.71.0 Phase 6).

Two responsibilities:

1. `should_cleanup_foreign_tracks(series_override, global_default)` —
   resolves the effective policy. Series override wins when not None;
   otherwise the global `cleanup_foreign_tracks_default` config key.

2. `maybe_run_foreign_track_cleanup(item, file_path, probe_data)` — the
   post-extraction hook called from batch_probe / extract after all
   target-language sidecars have landed. Reads settings, resolves the
   series override (if any), and invokes
   `remux.remove_foreign_subtitle_streams` when appropriate. Swallows
   errors with logging — cleanup must never break the happy path.
"""

from __future__ import annotations

import logging

from config_language_data import normalize_language_code

logger = logging.getLogger(__name__)


def should_cleanup_foreign_tracks(*, series_override: bool | None, global_default: bool) -> bool:
    """Return the effective per-item cleanup policy.

    Contract:
      - series_override is True  → cleanup runs even if global is off.
      - series_override is False → cleanup skipped even if global is on.
      - series_override is None  → inherit global_default.
    """
    if series_override is None:
        return bool(global_default)
    return bool(series_override)


def _get_series_override(item: dict) -> bool | None:
    """Look up SeriesSettings.cleanup_foreign_tracks for the item's series."""
    try:
        sonarr_id = item.get("sonarr_series_id")
        if not sonarr_id:
            return None
        from db.models.core import SeriesSettings
        from extensions import db

        ss = db.session.get(SeriesSettings, sonarr_id)
        if ss is None:
            return None
        return ss.cleanup_foreign_tracks
    except Exception:
        logger.debug("foreign-track cleanup: series override lookup failed", exc_info=True)
        return None


def maybe_run_foreign_track_cleanup(
    item: dict,
    file_path: str,
    target_languages: set[str] | None = None,
) -> None:
    """Execute foreign-track cleanup on the file if policy says so.

    Runs *after* the target-language sidecars have been written; any
    failure is logged and swallowed so the happy path never regresses.
    """
    try:
        from config import get_settings

        settings = get_settings()
        global_default = bool(getattr(settings, "cleanup_foreign_tracks_default", False))
        keep_und = bool(getattr(settings, "cleanup_foreign_tracks_keep_und", False))
    except Exception:
        logger.debug("foreign-track cleanup: settings unavailable", exc_info=True)
        return

    series_override = _get_series_override(item)
    if not should_cleanup_foreign_tracks(
        series_override=series_override, global_default=global_default
    ):
        return

    if target_languages is None:
        target_languages = {
            normalize_language_code(lang) for lang in (item.get("missing_languages") or []) if lang
        }
        tgt = item.get("target_language")
        if tgt:
            target_languages.add(normalize_language_code(tgt))
    target_languages = {t for t in target_languages if t}
    if not target_languages:
        logger.debug("foreign-track cleanup: no target languages resolved for %s", file_path)
        return

    try:
        from remux import remove_foreign_subtitle_streams

        backup = remove_foreign_subtitle_streams(
            video_path=file_path,
            target_languages=target_languages,
            keep_und=keep_und,
        )
        if backup:
            logger.info(
                "foreign-track cleanup: stripped non-target subs from %s (backup at %s)",
                file_path,
                backup,
            )
    except Exception as exc:
        logger.warning(
            "foreign-track cleanup failed for %s: %s — file untouched",
            file_path,
            exc,
        )
