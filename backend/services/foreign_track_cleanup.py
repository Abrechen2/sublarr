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

from config_language_data import _get_language_tags

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
        always_keep = getattr(settings, "cleanup_foreign_tracks_keep_languages", None) or []
    except Exception:
        logger.debug("foreign-track cleanup: settings unavailable", exc_info=True)
        return

    series_override = _get_series_override(item)
    if not should_cleanup_foreign_tracks(
        series_override=series_override, global_default=global_default
    ):
        return

    # Base keep-set: the item's wanted/target languages (resolved from the
    # item when the caller didn't pass an explicit set) unioned with the
    # configured always-keep languages, so a download target of just "de"
    # still preserves English embedded tracks.
    if target_languages is None:
        target_languages = set()
        for lang in item.get("missing_languages") or []:
            if lang:
                target_languages.add(str(lang).lower())
        tgt = item.get("target_language")
        if tgt:
            target_languages.add(str(tgt).lower())
    base_codes = {str(t).lower() for t in target_languages if t}
    base_codes |= {str(a).lower() for a in always_keep if a}

    # Expand to every known tag (de -> {de, deu, ger, german}) because the
    # remux strip compares the *raw* ffprobe language tag, which is usually
    # ISO-639-2 ("ger"/"eng") — comparing against bare 2-letter codes would
    # mis-classify the target language itself as foreign.
    keep_tags: set[str] = set()
    for code in base_codes:
        keep_tags.update(_get_language_tags(code))
    keep_tags = {t for t in keep_tags if t}
    if not keep_tags:
        logger.debug("foreign-track cleanup: no target languages resolved for %s", file_path)
        return
    target_languages = keep_tags

    # Audit G13: previously every failure went through a single
    # ``except Exception`` with a generic warning. That hid persistent
    # configuration problems (mkvmerge missing, read-only mount, ENOSPC)
    # behind one-line log entries that looked like transient blips.
    # Distinguishing the failure classes lets ops see what's actually
    # broken without having to crack open the traceback.
    try:
        from remux import RemuxError, remove_foreign_subtitle_streams

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
    except FileNotFoundError as exc:
        logger.warning(
            "foreign-track cleanup: file vanished mid-run (%s): %s — file untouched",
            file_path,
            exc,
        )
    except PermissionError as exc:
        logger.error(
            "foreign-track cleanup: permission denied on %s (%s) — fix mount permissions",
            file_path,
            exc,
        )
    except OSError as exc:
        # ENOSPC, ENOSYS, network errors — usually persistent until ops
        # intervenes. Log at ERROR so it surfaces in monitoring.
        logger.error(
            "foreign-track cleanup: OS error on %s: %s — file untouched",
            file_path,
            exc,
        )
    except RemuxError as exc:
        logger.warning(
            "foreign-track cleanup: remux error on %s: %s — file untouched",
            file_path,
            exc,
        )
    except Exception as exc:
        # Unexpected: include the type so ops can see what to look at.
        logger.error(
            "foreign-track cleanup: unexpected %s on %s: %s — file untouched",
            type(exc).__name__,
            file_path,
            exc,
        )
