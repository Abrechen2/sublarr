"""Library series endpoints — series detail, settings, and glossary."""

import logging

from flask import jsonify, request

from routes.library import bp

logger = logging.getLogger(__name__)


def _get_standalone_series_detail(series_id: int, settings) -> dict | None:
    """Build a Sonarr-compatible series detail dict from standalone DB data."""
    import re

    from sqlalchemy import text

    from db import get_db
    from db.profiles import get_default_profile
    from db.standalone import get_standalone_series
    from translator import detect_existing_target_for_lang

    series = get_standalone_series(series_id)
    if not series:
        return None

    profile = get_default_profile()
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )
    target_language_names = (
        profile.get("target_language_names", [settings.target_language_name])
        if profile
        else [settings.target_language_name]
    )
    profile_name = profile.get("name", "Default") if profile else "Default"

    db = get_db()
    rows = db.execute(
        text("SELECT * FROM wanted_items WHERE standalone_series_id=:sid ORDER BY file_path"),
        {"sid": series_id},
    ).fetchall()
    wanted_items = [dict(r._mapping) for r in rows]

    episodes = []
    seen: set = set()
    for item in wanted_items:
        fp = item.get("file_path", "")
        if fp in seen:
            continue
        seen.add(fp)
        se = item.get("season_episode", "")
        season, episode = 0, 0
        if se:
            m = re.match(r"S(\d+)E(\d+)", se, re.IGNORECASE)
            if m:
                season, episode = int(m.group(1)), int(m.group(2))
        subtitles: dict = {}
        for lang in target_languages:
            try:
                result = detect_existing_target_for_lang(fp, lang)
                subtitles[lang] = result or ""
            except Exception:
                subtitles[lang] = ""
        episodes.append(
            {
                "id": item.get("id"),
                "season": season,
                "episode": episode,
                "title": item.get("title", ""),
                "has_file": True,
                "file_path": fp,
                "subtitles": subtitles,
                "audio_languages": [],
                "monitored": True,
            }
        )

    poster = f"/api/v1/standalone/series/{series_id}/poster" if series.get("poster_url") else ""
    return {
        "id": series.get("id"),
        "title": series.get("title", ""),
        "year": series.get("year"),
        "path": series.get("folder_path", ""),
        "poster": poster,
        "fanart": "",
        "overview": "",
        "status": series.get("status", "continuing"),
        "season_count": series.get("season_count") or 0,
        "episode_count": len(episodes),
        "episode_file_count": len(episodes),
        "tags": [],
        "profile_name": profile_name,
        "target_languages": target_languages,
        "target_language_names": target_language_names,
        "source_language": settings.source_language,
        "source_language_name": settings.source_language_name,
        "absolute_order": False,
        "episodes": episodes,
        "source": "standalone",
    }


@bp.route("/library/series/<int:series_id>", methods=["GET"])
def get_series_detail(series_id):
    """Get detailed series info with episodes and subtitle status.
    ---
    get:
      tags:
        - Library
      summary: Get series detail
      description: Returns detailed series information including all episodes with subtitle status per target language.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
          description: Sonarr series ID
      responses:
        200:
          description: Series detail
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: integer
                  title:
                    type: string
                  year:
                    type: integer
                  path:
                    type: string
                  poster:
                    type: string
                  profile_name:
                    type: string
                  target_languages:
                    type: array
                    items:
                      type: string
                  episodes:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
        404:
          description: Series not found
        503:
          description: Sonarr not configured
    """
    from concurrent.futures import ThreadPoolExecutor

    from config import get_settings, map_path
    from db import get_db
    from db.profiles import get_default_profile, get_series_profile
    from sonarr_client import get_sonarr_client
    from translator import detect_existing_target_for_lang

    settings = get_settings()

    sonarr = get_sonarr_client()
    if not sonarr:
        # Try standalone fallback before giving up
        standalone_response = _get_standalone_series_detail(series_id, settings)
        if standalone_response is not None:
            return jsonify(standalone_response)
        return jsonify({"error": "Sonarr not configured"}), 503

    series = sonarr.get_series_by_id(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    # Get language profile for this series
    profile = get_series_profile(series_id)
    if not profile:
        profile = get_default_profile()
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )
    target_language_names = (
        profile.get("target_language_names", [settings.target_language_name])
        if profile
        else [settings.target_language_name]
    )
    profile_name = profile.get("name", "Default") if profile else "Default"

    # Get all episodes + episode files in parallel
    # /episode?seriesId=X does NOT include episodeFile details in Sonarr v3,
    # so we fetch /episodefile?seriesId=X separately to get paths and mediaInfo.
    episodes_raw = sonarr.get_episodes(series_id)
    ep_file_map = sonarr.get_episode_files_by_series(series_id)  # fileId -> file info

    # Build episodeId -> file info mapping via episodeFileId on each episode
    ep_id_to_file: dict = {}
    for ep in episodes_raw:
        if ep.get("hasFile") and ep.get("episodeFileId"):
            file_info = ep_file_map.get(ep["episodeFileId"])
            if file_info and file_info.get("path"):
                ep_id_to_file[ep["id"]] = file_info

    # Collect file paths for episodes that need subtitle detection
    episodes_to_check = {ep_id: info["path"] for ep_id, info in ep_id_to_file.items()}

    def _detect_subtitles(file_path: str) -> dict:
        mapped = map_path(file_path)
        return {
            lang: detect_existing_target_for_lang(mapped, lang) or "" for lang in target_languages
        }

    # Parallel filesystem I/O — ~8x faster for series with many episodes
    subtitle_map: dict = {}
    if episodes_to_check:
        with ThreadPoolExecutor(max_workers=min(8, len(episodes_to_check))) as executor:
            futures = {
                ep_id: executor.submit(_detect_subtitles, path)
                for ep_id, path in episodes_to_check.items()
            }
        subtitle_map = {ep_id: f.result() for ep_id, f in futures.items()}

    # Fallback 1: subtitle_downloads — records saved at download time with format
    # Uses the same mapped paths as wanted_search, so path-mapping is consistent.
    # Most recent download per (file_path, language) wins.
    ep_id_to_mapped: dict = {}  # ep_id -> local mapped path (used in response + DB lookup)
    history_fallback: dict = {}  # ep_id -> {lang: format}
    if ep_id_to_file:
        try:
            ep_id_to_mapped = {
                ep_id: map_path(info["path"]) for ep_id, info in ep_id_to_file.items()
            }
            mapped_to_ep_id = {v: k for k, v in ep_id_to_mapped.items()}
            paths = list(mapped_to_ep_id.keys())
            conn = get_db()
            placeholders = ",".join("?" * len(paths))
            rows = conn.execute(
                f"SELECT file_path, language, format FROM subtitle_downloads "
                f"WHERE file_path IN ({placeholders}) AND format != '' "
                f"ORDER BY downloaded_at DESC",
                paths,
            ).fetchall()
            for row in rows:
                path, lang, fmt = row[0], row[1], row[2]
                ep_id = mapped_to_ep_id.get(path)
                if ep_id and fmt:
                    if ep_id not in history_fallback:
                        history_fallback[ep_id] = {}
                    # First row per lang = most recent (ORDER BY downloaded_at DESC)
                    if lang not in history_fallback[ep_id]:
                        history_fallback[ep_id][lang] = fmt
        except Exception:
            pass  # best-effort; filesystem detection still primary

    # Fallback 2: wanted_items.existing_sub — covers embedded_srt/embedded_ass
    # detected by the scanner but not findable via filesystem check.
    ep_ids = [ep["id"] for ep in episodes_raw]
    wanted_fallback: dict = {}  # ep_id -> {lang: existing_sub}
    if ep_ids:
        try:
            conn = get_db()
            placeholders = ",".join("?" * len(ep_ids))
            rows = conn.execute(
                f"SELECT sonarr_episode_id, target_language, existing_sub "
                f"FROM wanted_items WHERE sonarr_episode_id IN ({placeholders})",
                ep_ids,
            ).fetchall()
            for row in rows:
                eid, lang, existing = row[0], row[1], row[2]
                if eid not in wanted_fallback:
                    wanted_fallback[eid] = {}
                if existing:
                    wanted_fallback[eid][lang] = existing
        except Exception:
            pass

    episodes = []
    for ep in episodes_raw:
        has_file = ep.get("hasFile", False)
        ep_id = ep.get("id")
        file_info = ep_id_to_file.get(ep_id)
        file_path = ep_id_to_mapped.get(ep_id, "")
        file_subtitles = subtitle_map.get(ep_id, {})

        # Merge: filesystem (primary) → download history → scanner/embedded fallback
        subtitles = {}
        for lang in target_languages:
            file_result = file_subtitles.get(lang, "")
            if file_result:
                subtitles[lang] = file_result  # filesystem: ground truth
            elif lang in history_fallback.get(ep_id, {}):
                subtitles[lang] = history_fallback[ep_id][lang]  # provider download record
            elif lang in wanted_fallback.get(ep_id, {}):
                subtitles[lang] = wanted_fallback[ep_id][lang]  # embedded sub (scanner)
            else:
                subtitles[lang] = ""

        # Audio languages from episodefile mediaInfo
        audio_languages = []
        if file_info:
            media_info = file_info.get("mediaInfo", {})
            audio_lang = media_info.get("audioLanguages", "")
            if audio_lang:
                audio_languages = [a.strip() for a in audio_lang.split("/") if a.strip()]

        episodes.append(
            {
                "id": ep.get("id"),
                "season": ep.get("seasonNumber", 0),
                "episode": ep.get("episodeNumber", 0),
                "title": ep.get("title", ""),
                "has_file": has_file,
                "file_path": file_path or "",
                "subtitles": subtitles,
                "audio_languages": audio_languages,
                "monitored": ep.get("monitored", False),
            }
        )

    # Get poster and fanart
    poster = ""
    fanart = ""
    for img in series.get("images", []):
        if img.get("coverType") == "poster":
            poster = img.get("remoteUrl", "")
        elif img.get("coverType") == "fanart":
            fanart = img.get("remoteUrl", "")

    # Get tags
    tag_list = sonarr.get_tags()
    tag_map = {t["id"]: t["label"] for t in tag_list}
    tags = [tag_map.get(tid, str(tid)) for tid in series.get("tags", [])]

    # Derive counts from the already-fetched episode list — more reliable than
    # Sonarr's statistics (which can be 0 from the single-series endpoint).
    regular_episodes = [ep for ep in episodes if ep["season"] > 0]
    _episode_count = len(regular_episodes)
    _episode_file_count = sum(1 for ep in regular_episodes if ep["has_file"])
    _season_count = len({ep["season"] for ep in regular_episodes})

    # Load series-level settings (absolute_order flag for AniDB episode order)
    absolute_order = False
    try:
        from db.repositories.anidb import AnidbRepository

        absolute_order = AnidbRepository().get_absolute_order(series_id)
    except Exception as _e:
        logger.debug("Could not load series settings for %d: %s", series_id, _e)

    # Load processing config override for this series
    import json as _json

    processing_config: dict = {}
    try:
        from db.models.core import SeriesSettings
        from extensions import db as _db

        row = _db.session.get(SeriesSettings, series_id)
        if row and row.processing_config:
            processing_config = _json.loads(row.processing_config)
    except Exception as _e:
        logger.debug("Could not load processing config for %d: %s", series_id, _e)

    return jsonify(
        {
            "id": series.get("id"),
            "title": series.get("title", ""),
            "year": series.get("year"),
            "path": series.get("path", ""),
            "poster": poster,
            "fanart": fanart,
            "overview": series.get("overview", ""),
            "status": series.get("status", ""),
            "season_count": _season_count,
            "episode_count": _episode_count,
            "episode_file_count": _episode_file_count,
            "tags": tags,
            "profile_name": profile_name,
            "target_languages": target_languages,
            "target_language_names": target_language_names,
            "source_language": settings.source_language,
            "source_language_name": settings.source_language_name,
            "absolute_order": absolute_order,
            "processing_config": processing_config,
            "episodes": episodes,
        }
    )


@bp.route("/library/series/<int:series_id>/settings", methods=["PUT"])
def update_series_settings(series_id):
    """Update per-series settings (e.g. absolute_order flag).
    ---
    put:
      tags:
        - Library
      summary: Update series settings
      description: Updates per-series configuration flags. Currently supports the absolute_order flag for AniDB absolute episode ordering.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
          description: Sonarr series ID
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                absolute_order:
                  type: boolean
                  description: When true, use AniDB absolute episode numbers for provider searches
      responses:
        200:
          description: Settings updated
          content:
            application/json:
              schema:
                type: object
                properties:
                  success:
                    type: boolean
                  series_id:
                    type: integer
                  absolute_order:
                    type: boolean
        400:
          description: Invalid request body
    """
    from db.repositories.anidb import AnidbRepository

    body = request.get_json(force=True, silent=True) or {}
    if "absolute_order" not in body:
        return jsonify({"success": False, "error": "absolute_order field required"}), 400

    enabled = bool(body["absolute_order"])
    AnidbRepository().set_absolute_order(series_id, enabled)
    logger.debug("Series %d: absolute_order set to %s", series_id, enabled)
    return jsonify({"success": True, "series_id": series_id, "absolute_order": enabled})


@bp.route("/series/<int:series_id>/glossary/suggest", methods=["POST"])
def suggest_glossary_candidates(series_id):
    """Extract glossary term candidates from subtitle sidecars for a series.
    ---
    post:
      tags:
        - Library
      summary: Suggest glossary candidates
      description: >
        Scans the series subtitle sidecar files and returns frequency-based
        proper-noun candidates suitable for seeding the glossary. Does not
        write anything to the database.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: series_id
          required: true
          schema:
            type: integer
          description: Sonarr series ID
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                source_lang:
                  type: string
                  default: en
                  description: Language tag used in sidecar filenames (e.g. "en")
                min_freq:
                  type: integer
                  default: 3
                  description: Minimum occurrence count to include a candidate
      responses:
        200:
          description: Candidate terms (empty list when series not found or no subs)
          content:
            application/json:
              schema:
                type: object
                properties:
                  candidates:
                    type: array
                    items:
                      type: object
                  series_id:
                    type: integer
                  message:
                    type: string
                    nullable: true
    """
    import routes.library as _lib_pkg
    from config import map_path
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify(
            {"candidates": [], "series_id": series_id, "message": "Sonarr not configured"}
        )

    series = sonarr.get_series_by_id(series_id)
    if not series or not series.get("path"):
        return jsonify(
            {"candidates": [], "series_id": series_id, "message": "Series media path not found"}
        )

    body = request.get_json(silent=True) or {}
    source_lang = (body.get("source_lang") or "en").strip()
    min_freq = int(body.get("min_freq") or 3)

    media_path = map_path(series["path"])
    candidates = _lib_pkg.extract_candidates(
        media_path,
        source_lang=source_lang,
        min_freq=min_freq,
        max_candidates=100,
    )

    return jsonify({"candidates": candidates, "series_id": series_id})
