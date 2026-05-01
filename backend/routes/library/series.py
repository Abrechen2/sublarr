"""Library series detail endpoint — GET /library/series/<id>.

Per-series settings (PUT) and glossary-candidate suggestions live in
routes/library/series_settings.py (B1Se split).
"""

import logging

from flask import jsonify

from routes.library import bp

logger = logging.getLogger(__name__)


def _get_standalone_series_detail(series_id: int, settings) -> dict | None:
    """Build a Sonarr-compatible series detail dict from standalone DB data."""
    import re
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import bindparam, text

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
    profile_id = profile.get("id") if profile else None

    db = get_db()
    rows = db.execute(
        text("SELECT * FROM wanted_items WHERE standalone_series_id=:sid ORDER BY file_path"),
        {"sid": series_id},
    ).fetchall()
    wanted_items = [dict(r._mapping) for r in rows]

    # Load subtitle_downloads score/provider for all file paths in this series
    standalone_scores: dict = {}  # fp -> {lang: (score, provider_name)}
    file_paths_all = list(
        {item.get("file_path", "") for item in wanted_items if item.get("file_path")}
    )
    if file_paths_all:
        try:
            # `?` placeholders + a positional list are SQLite-only; SQLAlchemy
            # 2.x bound to PostgreSQL raises on every call and the catch-all
            # below masks it as a debug log, so every standalone-series detail
            # used to render score=null + provider=null even with downloads
            # actually persisted. Use named binds via expanding-IN to stay
            # cross-DB.
            stmt = text(
                "SELECT file_path, language, format, score, provider_name "
                "FROM subtitle_downloads "
                "WHERE file_path IN :fps AND format != '' "
                "ORDER BY downloaded_at DESC"
            ).bindparams(bindparam("fps", expanding=True))
            rows_sa = db.execute(stmt, {"fps": file_paths_all}).fetchall()
            for row in rows_sa:
                sa_path, sa_lang, sa_fmt = row[0], row[1], row[2]
                sa_score, sa_provider = row[3], row[4]
                if sa_fmt:
                    if sa_path not in standalone_scores:
                        standalone_scores[sa_path] = {}
                    if sa_lang not in standalone_scores[sa_path]:
                        standalone_scores[sa_path][sa_lang] = (sa_score, sa_provider)
        except Exception as exc:
            logger.warning("subtitle_downloads score query failed: %s", exc, exc_info=True)

    # Collect unique file paths for parallel subtitle detection
    unique_fps = list({item.get("file_path", "") for item in wanted_items if item.get("file_path")})

    def _detect_subtitles(file_path: str) -> dict:
        """Detect subtitles for a single file across all target languages."""
        result = {}
        for lang in target_languages:
            try:
                detected = detect_existing_target_for_lang(file_path, lang)
                result[lang] = detected or ""
            except Exception:
                result[lang] = ""
        return result

    # Parallel filesystem I/O — 2x+ faster for series with many episodes
    subtitle_map: dict = {}
    if unique_fps:
        with ThreadPoolExecutor(max_workers=min(8, len(unique_fps))) as executor:
            futures = {fp: executor.submit(_detect_subtitles, fp) for fp in unique_fps}
        subtitle_map = {fp: f.result() for fp, f in futures.items()}

    # 0.71.0 Phase 8 — wanted_items.existing_sub fallback keyed by file_path.
    # Maps file_path → {lang: existing_sub} so embedded_srt/embedded_ass fills
    # the gap where the filesystem sidecar hasn't been written yet. Mirrors
    # the Sonarr path's wanted_fallback merge at line ~357.
    wanted_fallback_sa: dict = {}
    for _it in wanted_items:
        _fp = _it.get("file_path", "")
        _lang = _it.get("target_language") or ""
        _existing = _it.get("existing_sub") or ""
        if _fp and _lang and _existing:
            wanted_fallback_sa.setdefault(_fp, {})[_lang] = _existing

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
        fs_subs = subtitle_map.get(fp, {})
        subtitles = {}
        for lang in target_languages:
            fs = fs_subs.get(lang, "") if fs_subs else ""
            if fs:
                subtitles[lang] = fs
            else:
                subtitles[lang] = wanted_fallback_sa.get(fp, {}).get(lang, "")
        ep_scores_sa = standalone_scores.get(fp, {})
        episodes.append(
            {
                "id": item.get("id"),
                "season": season,
                "episode": episode,
                "title": item.get("title", ""),
                "has_file": True,
                "file_path": fp,
                "subtitles": subtitles,
                "subtitle_scores": {
                    lang: ep_scores_sa.get(lang, (None, None))[0] for lang in subtitles
                },
                "subtitle_providers": {
                    lang: ep_scores_sa.get(lang, (None, None))[1] for lang in subtitles
                },
                "audio_languages": [],
                "monitored": True,
            }
        )

    poster = f"/api/v1/standalone/series/{series_id}/poster" if series.get("poster_url") else ""

    # Standalone series have no SeriesSettings row — override is always null,
    # effective policy mirrors the global default.
    global_default = bool(getattr(settings, "cleanup_foreign_tracks_default", False))

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
        "profile_id": profile_id,
        "target_languages": target_languages,
        "target_language_names": target_language_names,
        "source_language": settings.source_language,
        "source_language_name": settings.source_language_name,
        "absolute_order": False,
        "cleanup_foreign_tracks_override": None,
        "cleanup_foreign_tracks_effective": global_default,
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

    from sqlalchemy import bindparam, text

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
    profile_id = profile.get("id") if profile else None

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
    history_scores: dict = {}  # ep_id -> {lang: (score, provider_name)}
    if ep_id_to_file:
        try:
            ep_id_to_mapped = {
                ep_id: map_path(info["path"]) for ep_id, info in ep_id_to_file.items()
            }
            mapped_to_ep_id = {v: k for k, v in ep_id_to_mapped.items()}
            paths = list(mapped_to_ep_id.keys())
            conn = get_db()
            stmt = text(
                "SELECT file_path, language, format, score, provider_name "
                "FROM subtitle_downloads "
                "WHERE file_path IN :paths AND format != '' "
                "ORDER BY downloaded_at DESC"
            ).bindparams(bindparam("paths", expanding=True))
            rows = conn.execute(stmt, {"paths": paths}).fetchall()
            for row in rows:
                path, lang, fmt = row[0], row[1], row[2]
                score, provider_name = row[3], row[4]
                ep_id = mapped_to_ep_id.get(path)
                if ep_id and fmt:
                    if ep_id not in history_fallback:
                        history_fallback[ep_id] = {}
                    if ep_id not in history_scores:
                        history_scores[ep_id] = {}
                    # First row per lang = most recent (ORDER BY downloaded_at DESC)
                    if lang not in history_fallback[ep_id]:
                        history_fallback[ep_id][lang] = fmt
                    if lang not in history_scores[ep_id]:
                        history_scores[ep_id][lang] = (score, provider_name)
        except Exception as exc:
            logger.warning("subtitle_downloads score query failed: %s", exc, exc_info=True)

    # Fallback 2: wanted_items.existing_sub — covers embedded_srt/embedded_ass
    # detected by the scanner but not findable via filesystem check.
    ep_ids = [ep["id"] for ep in episodes_raw]
    wanted_fallback: dict = {}  # ep_id -> {lang: existing_sub}
    if ep_ids:
        try:
            conn = get_db()
            stmt = text(
                "SELECT sonarr_episode_id, target_language, existing_sub "
                "FROM wanted_items WHERE sonarr_episode_id IN :ep_ids"
            ).bindparams(bindparam("ep_ids", expanding=True))
            rows = conn.execute(stmt, {"ep_ids": ep_ids}).fetchall()
            for row in rows:
                eid, lang, existing = row[0], row[1], row[2]
                if eid not in wanted_fallback:
                    wanted_fallback[eid] = {}
                if existing:
                    wanted_fallback[eid][lang] = existing
        except Exception as exc:
            logger.warning("Failed to load wanted fallback for series episodes: %s", exc, exc_info=True)

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

        ep_scores = history_scores.get(ep_id, {})
        episodes.append(
            {
                "id": ep.get("id"),
                "season": ep.get("seasonNumber", 0),
                "episode": ep.get("episodeNumber", 0),
                "title": ep.get("title", ""),
                "has_file": has_file,
                "file_path": file_path or "",
                "subtitles": subtitles,
                "subtitle_scores": {
                    lang: ep_scores.get(lang, (None, None))[0] for lang in subtitles
                },
                "subtitle_providers": {
                    lang: ep_scores.get(lang, (None, None))[1] for lang in subtitles
                },
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

    # Load processing config override + cleanup_foreign_tracks override for this series
    import json as _json

    from services.foreign_track_cleanup import should_cleanup_foreign_tracks

    processing_config: dict = {}
    cleanup_override: bool | None = None
    try:
        from db.models.core import SeriesSettings
        from extensions import db as _db

        row = _db.session.get(SeriesSettings, series_id)
        if row:
            if row.processing_config:
                processing_config = _json.loads(row.processing_config)
            cleanup_override = row.cleanup_foreign_tracks
    except Exception as _e:
        logger.debug("Could not load series settings for %d: %s", series_id, _e)

    global_default = bool(getattr(settings, "cleanup_foreign_tracks_default", False))
    cleanup_effective = should_cleanup_foreign_tracks(
        series_override=cleanup_override, global_default=global_default
    )

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
            "profile_id": profile_id,
            "target_languages": target_languages,
            "target_language_names": target_language_names,
            "source_language": settings.source_language,
            "source_language_name": settings.source_language_name,
            "absolute_order": absolute_order,
            "cleanup_foreign_tracks_override": cleanup_override,
            "cleanup_foreign_tracks_effective": cleanup_effective,
            "processing_config": processing_config,
            "episodes": episodes,
        }
    )
