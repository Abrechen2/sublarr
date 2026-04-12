"""Item-level scanning logic for wanted subtitle detection.

Handles the per-episode and per-movie scanning that checks for existing
subtitles, embedded streams, upgrade candidates, and forced subtitle
preferences. Used by WantedScanner.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from ass_utils import (
    get_all_subtitle_streams,
    get_media_streams,
    has_target_language_audio,
    has_target_language_stream,
)
from config import get_settings, map_path
from db.profiles import get_movie_profile, get_series_profile
from db.wanted import upsert_wanted_item
from translator import detect_existing_target_for_lang, get_output_path_for_lang
from upgrade_scorer import score_existing_subtitle

logger = logging.getLogger(__name__)


def batch_probe(paths: list[str]) -> dict[str, object]:
    """Run metadata probing on multiple paths in parallel.

    Uses the configured scan_metadata_engine (via get_media_streams) and
    scan_metadata_max_workers from settings.

    Returns dict mapping path -> probe_data (or None on error).
    """
    max_workers = getattr(get_settings(), "scan_metadata_max_workers", 4)
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {executor.submit(get_media_streams, p, True): p for p in paths}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                results[path] = future.result()
            except Exception as e:
                logger.debug("probe failed for %s: %s", path, e)
                results[path] = None
    return results


def _check_language_for_item(
    mapped_path: str,
    target_lang: str,
    probe_data,
    settings,
) -> dict | None:
    """Check a single target language for a media file.

    Returns a dict with upsert fields if the item is wanted, or None if
    the target language is already satisfied.
    """
    existing = detect_existing_target_for_lang(mapped_path, target_lang, probe_data)
    if existing == "ass":
        return None
    if existing == "srt" and not settings.upgrade_enabled:
        return None

    embedded_sub = None
    if probe_data:
        if has_target_language_audio(probe_data, target_lang):
            return None
        embedded_sub = has_target_language_stream(probe_data, target_lang)
        if embedded_sub == "ass":
            existing = "embedded_ass"
        elif embedded_sub == "srt":
            existing = "embedded_srt"

    embedded_langs = []
    if probe_data:
        embedded_langs = get_all_subtitle_streams(probe_data, exclude_language=target_lang)

    existing_sub = existing or ""

    is_upgrade = False
    cur_score = 0
    if existing_sub == "srt" and settings.upgrade_enabled:
        srt_path = get_output_path_for_lang(mapped_path, "srt", target_lang)
        if os.path.exists(srt_path):
            _, cur_score = score_existing_subtitle(srt_path)
            is_upgrade = True

    return {
        "existing_sub": existing_sub,
        "embedded_languages": embedded_langs,
        "upgrade_candidate": is_upgrade,
        "current_score": cur_score,
    }


def scan_radarr_movie(
    radarr,
    movie,
    settings,
    instance_name=None,
    *,
    auto_extract_fn=None,
):
    """Scan a single Radarr movie. Returns (added, updated, scanned_paths)."""
    added = 0
    updated = 0
    scanned_paths = set()

    if not movie.get("hasFile"):
        return added, updated, scanned_paths

    movie_id = movie.get("id")
    movie_title = movie.get("title", f"Movie {movie_id}")

    file_path = None
    movie_file = movie.get("movieFile")
    if movie_file and movie_file.get("path"):
        file_path = movie_file["path"]
    else:
        file_id = movie.get("movieFileId")
        if file_id and file_id != 0:
            file_info = radarr.get_movie_file(file_id)
            if file_info:
                file_path = file_info.get("path")

    if not file_path:
        return added, updated, scanned_paths

    mapped_path = map_path(file_path)
    if not os.path.exists(mapped_path):
        return added, updated, scanned_paths

    scanned_paths.add(mapped_path)

    profile = get_movie_profile(movie_id)
    target_languages = profile.get("target_languages", [settings.target_language])
    target_language_names = profile.get(
        "target_language_names", [settings.target_language_name]
    )

    probe_data = None
    if settings.use_embedded_subs and mapped_path.lower().endswith((".mkv", ".mp4", ".m4v")):
        try:
            probe_data = get_media_streams(mapped_path, use_cache=True)
        except Exception as e:
            logger.debug("ffprobe failed for %s: %s", mapped_path, e)

    for target_lang, _target_name in zip(target_languages, target_language_names):
        lang_result = _check_language_for_item(mapped_path, target_lang, probe_data, settings)
        if lang_result is None:
            continue

        title = movie_title
        if len(target_languages) > 1:
            title = f"{title} [{target_lang.upper()}]"

        item_id, was_updated = upsert_wanted_item(
            item_type="movie",
            file_path=mapped_path,
            title=title,
            existing_sub=lang_result["existing_sub"],
            missing_languages=[target_lang],
            radarr_movie_id=movie_id,
            upgrade_candidate=lang_result["upgrade_candidate"],
            current_score=lang_result["current_score"],
            target_language=target_lang,
            instance_name=instance_name or "",
            subtitle_type="full",
            embedded_languages=lang_result["embedded_languages"],
        )
        if was_updated:
            updated += 1
        else:
            added += 1
            if lang_result["existing_sub"] in ("embedded_ass", "embedded_srt") and auto_extract_fn:
                auto_extract_fn(item_id, mapped_path)

        # Forced subtitle handling
        forced_preference = profile.get("forced_preference", "disabled")
        if forced_preference == "separate":
            existing_forced = detect_existing_target_for_lang(
                mapped_path, target_lang, probe_data, subtitle_type="forced"
            )
            if existing_forced is None:
                forced_title = f"{title} [Forced]"
                _, forced_was_updated = upsert_wanted_item(
                    item_type="movie",
                    file_path=mapped_path,
                    title=forced_title,
                    existing_sub="",
                    missing_languages=[target_lang],
                    radarr_movie_id=movie_id,
                    upgrade_candidate=False,
                    current_score=0,
                    target_language=target_lang,
                    instance_name=instance_name or "",
                    subtitle_type="forced",
                )
                if forced_was_updated:
                    updated += 1
                else:
                    added += 1

    return added, updated, scanned_paths


def scan_sonarr_series(
    sonarr,
    series_id,
    settings,
    series_info=None,
    instance_name=None,
    *,
    auto_extract_fn=None,
):
    """Scan a single series. Returns (added, updated, scanned_paths)."""
    if not series_info:
        series_info = sonarr.get_series_by_id(series_id) or {}

    series_title = series_info.get("title", f"Series {series_id}")
    episodes = sonarr.get_episodes(series_id)
    if not episodes:
        return 0, 0, set()

    profile = get_series_profile(series_id)
    target_languages = profile.get("target_languages", [settings.target_language])
    target_language_names = profile.get(
        "target_language_names", [settings.target_language_name]
    )

    added = 0
    updated = 0
    scanned_paths = set()

    # Collect episode file paths for batch ffprobe
    episode_data = []
    for ep in episodes:
        if not ep.get("hasFile"):
            continue

        episode_id = ep.get("id")
        file_path = None

        ep_file = ep.get("episodeFile")
        if ep_file and ep_file.get("path"):
            file_path = ep_file["path"]
        else:
            file_path = sonarr.get_episode_file_path(episode_id)

        if not file_path:
            continue

        mapped_path = map_path(file_path)
        if not os.path.exists(mapped_path):
            continue

        episode_data.append((ep, mapped_path))

    # Batch ffprobe
    probe_results = {}
    if settings.use_embedded_subs and episode_data:
        probeable = [
            mp for _, mp in episode_data if mp.lower().endswith((".mkv", ".mp4", ".m4v"))
        ]
        if probeable:
            probe_results = batch_probe(probeable)

    for ep, mapped_path in episode_data:
        scanned_paths.add(mapped_path)

        episode_id = ep.get("id")
        season_num = ep.get("seasonNumber", 0)
        episode_num = ep.get("episodeNumber", 0)
        season_episode = f"S{season_num:02d}E{episode_num:02d}"

        probe_data = probe_results.get(mapped_path)

        for target_lang, _target_name in zip(target_languages, target_language_names):
            lang_result = _check_language_for_item(mapped_path, target_lang, probe_data, settings)
            if lang_result is None:
                continue

            title = f"{series_title} — {season_episode}"
            if len(target_languages) > 1:
                title = f"{title} [{target_lang.upper()}]"

            item_id, was_updated = upsert_wanted_item(
                item_type="episode",
                file_path=mapped_path,
                title=title,
                season_episode=season_episode,
                existing_sub=lang_result["existing_sub"],
                missing_languages=[target_lang],
                sonarr_series_id=series_id,
                sonarr_episode_id=episode_id,
                upgrade_candidate=lang_result["upgrade_candidate"],
                current_score=lang_result["current_score"],
                target_language=target_lang,
                instance_name=instance_name or "",
                subtitle_type="full",
                embedded_languages=lang_result["embedded_languages"],
            )
            if was_updated:
                updated += 1
            else:
                added += 1
                if lang_result["existing_sub"] in ("embedded_ass", "embedded_srt") and auto_extract_fn:
                    auto_extract_fn(item_id, mapped_path)

            # Forced subtitle handling
            forced_preference = profile.get("forced_preference", "disabled")
            if forced_preference == "separate":
                existing_forced = detect_existing_target_for_lang(
                    mapped_path, target_lang, probe_data, subtitle_type="forced"
                )
                if existing_forced is None:
                    forced_title = f"{title} [Forced]"
                    _, forced_was_updated = upsert_wanted_item(
                        item_type="episode",
                        file_path=mapped_path,
                        title=forced_title,
                        season_episode=season_episode,
                        existing_sub="",
                        missing_languages=[target_lang],
                        sonarr_series_id=series_id,
                        sonarr_episode_id=episode_id,
                        upgrade_candidate=False,
                        current_score=0,
                        target_language=target_lang,
                        instance_name=instance_name or "",
                        subtitle_type="forced",
                    )
                    if forced_was_updated:
                        updated += 1
                    else:
                        added += 1

    return added, updated, scanned_paths
