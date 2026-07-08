"""Provisional machine-translation: record MT output + keep the wanted item
provisional (seeking the human original) instead of deleting it, per profile.

Phase 1: flag + provisional state. Re-seek/replace of the original is phase 2.
See docs/plans/2026-07-03-v1.6-provisional-mt.md.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _resolve_profile_for_item(item: dict) -> dict | None:
    """Resolve the LanguageProfile dict governing a wanted item.

    Mirrors the series -> movie -> default resolution order used elsewhere
    (e.g. services.embedded_extractor.resolve_profile_for_item), but also
    covers standalone-managed items which store their series/movie id under
    ``standalone_series_id`` / ``standalone_movie_id`` instead of the
    Sonarr/Radarr-native fields. The assignment tables (SeriesLanguageProfile /
    MovieLanguageProfile) are keyed by that same id regardless of origin, so
    ``get_series_profile`` / ``get_movie_profile`` work unchanged for both.
    """
    from db.profiles import get_default_profile, get_movie_profile, get_series_profile

    sid = item.get("sonarr_series_id") or item.get("standalone_series_id")
    mid = item.get("radarr_movie_id") or item.get("standalone_movie_id")
    if sid:
        return get_series_profile(sid)
    if mid:
        return get_movie_profile(mid)
    return get_default_profile()


def resolve_keep_seeking(item: dict) -> bool:
    """Whether this item's profile keeps MT provisional. Fails safe to False.

    ``db.profiles.get_series_profile`` / ``get_movie_profile`` /
    ``get_default_profile`` all return plain dicts (via
    ``ProfileRepository._row_to_profile``), not ORM instances -- including the
    synthetic zero-profiles fallback dict, which does not carry the
    ``mt_keep_seeking_original`` key at all. Use ``dict.get`` accordingly.
    """
    try:
        prof = _resolve_profile_for_item(item)
        if not prof:
            return False
        return bool(prof.get("mt_keep_seeking_original", 0))
    except Exception as e:
        logger.debug("resolve_keep_seeking failed, defaulting to delete: %s", e)
        return False


def record_mt_output(video_path: str, output_path: str, target_lang: str, target_fmt: str) -> None:
    """Record an MT subtitle_downloads row (source="machine_translation").

    ``file_path`` is always the VIDEO path, matching the invariant every other
    source uses (provider downloads, manual uploads, whisper, combine -- see
    their own record_subtitle_download calls) -- not ``output_path``, the
    generated subtitle's own path. History's preview button reconstructs
    "{base}.{lang}.{fmt}" from this column assuming it's the video; storing
    the subtitle path there double-suffixed the reconstructed path and 404'd
    (bug found 2026-07-08). ``output_path`` only feeds the synthetic subtitle_id.

    Recorded unconditionally whenever an output_path is available -- callers
    decide whether/how to react to a missing wanted-item context.
    """
    from db.providers import record_subtitle_download

    try:
        record_subtitle_download(
            provider_name="translation",
            subtitle_id=f"mt:{os.path.basename(output_path)}",
            language=target_lang,
            fmt=target_fmt,
            file_path=video_path,
            score=0,
            source="machine_translation",
            # The site-provider subtitle that fed this translation already
            # bumped daily_stats via its own record_subtitle_download call.
            # This synthetic MT row must land for history/upgrade-scan
            # purposes but must NOT double-count the same translation on
            # the Statistics dashboard.
            record_stats=False,
        )
    except Exception as e:
        logger.warning("record_mt_output: failed to record MT row for %s: %s", output_path, e)


def finalize_translation(item_id, item, output_path, target_lang, target_fmt) -> None:
    """Record MT output (source="machine_translation") + set provisional or delete per profile.

    The MT subtitle_downloads row is recorded unconditionally whenever an
    output_path is available -- only the keep-provisional-vs-delete decision
    for the wanted item is gated by the profile, and that gate fails safe to
    delete (current behaviour) on any profile-resolution error.
    """
    from db.wanted import delete_wanted_item, update_wanted_status

    if output_path:
        record_mt_output(item["file_path"], output_path, target_lang, target_fmt)

    if resolve_keep_seeking(item):
        update_wanted_status(item_id, "provisional")
    else:
        delete_wanted_item(item_id)
