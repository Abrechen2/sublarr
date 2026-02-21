"""Library routes — /library, /sonarr/*, /radarr/*, /episodes/*."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("library", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/library", methods=["GET"])
def get_library():
    """Get series/movies with subtitle status, profile assignments, and missing counts.
    ---
    get:
      tags:
        - Library
      summary: Get library
      description: Returns all series and movies from Sonarr/Radarr with subtitle status, language profile assignments, and missing subtitle counts.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Library data
          content:
            application/json:
              schema:
                type: object
                properties:
                  series:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
                  movies:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
    """
    from db.profiles import get_series_profile_map, get_default_profile
    from db.wanted import get_series_missing_counts

    result = {"series": [], "movies": []}

    try:
        from sonarr_client import get_sonarr_client
        sonarr = get_sonarr_client()
        if sonarr:
            series_list = sonarr.get_library_info()
            # Enrich with profile assignments and missing counts
            profile_map = get_series_profile_map()
            missing_map = get_series_missing_counts()
            default_profile = None
            for s in series_list:
                sid = s["id"]
                if sid in profile_map:
                    s["profile_id"] = profile_map[sid]["profile_id"]
                    s["profile_name"] = profile_map[sid]["profile_name"]
                else:
                    if default_profile is None:
                        default_profile = get_default_profile()
                    s["profile_id"] = default_profile.get("id", 0) if default_profile else 0
                    s["profile_name"] = default_profile.get("name", "Default") if default_profile else "Default"
                s["missing_count"] = missing_map.get(sid, 0)
            result["series"] = series_list
    except Exception as e:
        logger.warning("Failed to get Sonarr library: %s", e)

    try:
        from radarr_client import get_radarr_client
        radarr = get_radarr_client()
        if radarr:
            result["movies"] = radarr.get_library_info()
    except Exception as e:
        logger.warning("Failed to get Radarr library: %s", e)

    return jsonify(result)


@bp.route("/sonarr/instances", methods=["GET"])
def get_sonarr_instances():
    """Get all configured Sonarr instances.
    ---
    get:
      tags:
        - Library
      summary: List Sonarr instances
      description: Returns all configured Sonarr instance connections.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Sonarr instances
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    url:
                      type: string
    """
    from config import get_sonarr_instances
    instances = get_sonarr_instances()
    return jsonify(instances)


@bp.route("/radarr/instances", methods=["GET"])
def get_radarr_instances():
    """Get all configured Radarr instances.
    ---
    get:
      tags:
        - Library
      summary: List Radarr instances
      description: Returns all configured Radarr instance connections.
      security:
        - apiKeyAuth: []
      responses:
        200:
          description: Radarr instances
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    name:
                      type: string
                    url:
                      type: string
    """
    from config import get_radarr_instances
    instances = get_radarr_instances()
    return jsonify(instances)


@bp.route("/sonarr/instances/test", methods=["POST"])
def test_sonarr_instance():
    """Test connection to a Sonarr instance.
    ---
    post:
      tags:
        - Library
      summary: Test Sonarr connection
      description: Tests connectivity to a Sonarr instance using the provided URL and API key.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [url, api_key]
              properties:
                url:
                  type: string
                  description: Sonarr base URL
                api_key:
                  type: string
                  description: Sonarr API key
      responses:
        200:
          description: Connection test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        400:
          description: Missing url or api_key
        500:
          description: Connection failed
    """
    data = request.get_json() or {}
    url = data.get("url")
    api_key = data.get("api_key")

    if not url or not api_key:
        return jsonify({"error": "url and api_key required"}), 400

    try:
        from sonarr_client import SonarrClient
        client = SonarrClient(url, api_key)
        is_healthy, message = client.health_check()
        return jsonify({"healthy": is_healthy, "message": message})
    except Exception as e:
        return jsonify({"healthy": False, "message": str(e)}), 500


@bp.route("/radarr/instances/test", methods=["POST"])
def test_radarr_instance():
    """Test connection to a Radarr instance.
    ---
    post:
      tags:
        - Library
      summary: Test Radarr connection
      description: Tests connectivity to a Radarr instance using the provided URL and API key.
      security:
        - apiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [url, api_key]
              properties:
                url:
                  type: string
                  description: Radarr base URL
                api_key:
                  type: string
                  description: Radarr API key
      responses:
        200:
          description: Connection test result
          content:
            application/json:
              schema:
                type: object
                properties:
                  healthy:
                    type: boolean
                  message:
                    type: string
        400:
          description: Missing url or api_key
        500:
          description: Connection failed
    """
    data = request.get_json() or {}
    url = data.get("url")
    api_key = data.get("api_key")

    if not url or not api_key:
        return jsonify({"error": "url and api_key required"}), 400

    try:
        from radarr_client import RadarrClient
        client = RadarrClient(url, api_key)
        is_healthy, message = client.health_check()
        return jsonify({"healthy": is_healthy, "message": message})
    except Exception as e:
        return jsonify({"healthy": False, "message": str(e)}), 500


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
    from sonarr_client import get_sonarr_client
    from translator import detect_existing_target_for_lang
    from db.profiles import get_series_profile, get_default_profile
    from config import get_settings, map_path
    from database import get_db, _db_lock

    settings = get_settings()

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    series = sonarr.get_series_by_id(series_id)
    if not series:
        return jsonify({"error": "Series not found"}), 404

    # Get language profile for this series
    profile = get_series_profile(series_id)
    if not profile:
        profile = get_default_profile()
    target_languages = profile.get("target_languages", [settings.target_language]) if profile else [settings.target_language]
    target_language_names = profile.get("target_language_names", [settings.target_language_name]) if profile else [settings.target_language_name]
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
    episodes_to_check = {
        ep_id: info["path"]
        for ep_id, info in ep_id_to_file.items()
    }

    def _detect_subtitles(file_path: str) -> dict:
        mapped = map_path(file_path)
        return {lang: detect_existing_target_for_lang(mapped, lang) or "" for lang in target_languages}

    # Parallel filesystem I/O — ~8x faster for series with many episodes
    subtitle_map: dict = {}
    if episodes_to_check:
        with ThreadPoolExecutor(max_workers=min(8, len(episodes_to_check))) as executor:
            futures = {ep_id: executor.submit(_detect_subtitles, path)
                       for ep_id, path in episodes_to_check.items()}
        subtitle_map = {ep_id: f.result() for ep_id, f in futures.items()}

    # Fallback 1: subtitle_downloads — records saved at download time with format
    # Uses the same mapped paths as wanted_search, so path-mapping is consistent.
    # Most recent download per (file_path, language) wins.
    history_fallback: dict = {}  # ep_id -> {lang: format}
    if ep_id_to_file:
        try:
            ep_id_to_mapped = {
                ep_id: map_path(info["path"])
                for ep_id, info in ep_id_to_file.items()
            }
            mapped_to_ep_id = {v: k for k, v in ep_id_to_mapped.items()}
            paths = list(mapped_to_ep_id.keys())
            with _db_lock:
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
            with _db_lock:
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
        file_path = file_info["path"] if file_info else ""
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

        episodes.append({
            "id": ep.get("id"),
            "season": ep.get("seasonNumber", 0),
            "episode": ep.get("episodeNumber", 0),
            "title": ep.get("title", ""),
            "has_file": has_file,
            "file_path": file_path or "",
            "subtitles": subtitles,
            "audio_languages": audio_languages,
            "monitored": ep.get("monitored", False),
        })

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

    return jsonify({
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
        "episodes": episodes,
    })


@bp.route("/episodes/<int:episode_id>/search", methods=["POST"])
def episode_search(episode_id):
    """Search providers for a specific episode's subtitles.
    ---
    post:
      tags:
        - Library
      summary: Search episode subtitles
      description: Finds or creates a wanted item for the episode and searches all providers for matching subtitles.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: episode_id
          required: true
          schema:
            type: integer
          description: Sonarr episode ID
      responses:
        200:
          description: Search results
          content:
            application/json:
              schema:
                type: object
                additionalProperties: true
        400:
          description: Search error
        404:
          description: Episode not found or has no file
        503:
          description: Sonarr not configured
    """
    from sonarr_client import get_sonarr_client
    from db.profiles import get_series_profile, get_default_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from wanted_search import search_wanted_item
    from config import get_settings, map_path

    settings = get_settings()

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode = sonarr.get_episode_by_id(episode_id)
    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    series_id = episode.get("seriesId")
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = profile.get("target_languages", [settings.target_language]) if profile else [settings.target_language]

    # Use the first target language (primary)
    target_lang = target_languages[0] if target_languages else settings.target_language

    # Check if wanted item already exists for this episode
    wanted = find_wanted_by_episode(episode_id, target_lang)

    if not wanted:
        # Get file path from episode
        file_path = sonarr.get_episode_file_path(episode_id)
        if not file_path:
            return jsonify({"error": "Episode has no file"}), 404

        file_path = map_path(file_path)
        series = sonarr.get_series_by_id(series_id) if series_id else None
        title = series.get("title", "") if series else ""
        se = f"S{episode.get('seasonNumber', 0):02d}E{episode.get('episodeNumber', 0):02d}"

        # Create a wanted item
        item_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=file_path,
            title=title,
            season_episode=se,
            sonarr_series_id=series_id,
            sonarr_episode_id=episode_id,
            target_language=target_lang,
        )
    else:
        item_id = wanted["id"]

    result = search_wanted_item(item_id)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)


@bp.route("/episodes/<int:episode_id>/search-providers", methods=["GET"])
def episode_search_providers_interactive(episode_id):
    """Return all provider results for interactive subtitle selection (episode view).
    ---
    get:
      tags:
        - Library
      summary: Interactive provider search for episode
      description: Finds or creates a wanted item for the episode and returns all provider results for manual selection.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: episode_id
          required: true
          schema:
            type: integer
          description: Sonarr episode ID
      responses:
        200:
          description: All provider results
        404:
          description: Episode not found or has no file
        503:
          description: Sonarr not configured
    """
    from sonarr_client import get_sonarr_client
    from db.profiles import get_series_profile, get_default_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from wanted_search import search_providers_for_item
    from config import get_settings, map_path

    settings = get_settings()
    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode = sonarr.get_episode_by_id(episode_id)
    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    series_id = episode.get("seriesId")
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = profile.get("target_languages", [settings.target_language]) if profile else [settings.target_language]
    target_lang = target_languages[0] if target_languages else settings.target_language

    wanted = find_wanted_by_episode(episode_id, target_lang)
    if not wanted:
        file_path = sonarr.get_episode_file_path(episode_id)
        if not file_path:
            return jsonify({"error": "Episode has no file"}), 404
        file_path = map_path(file_path)
        series = sonarr.get_series_by_id(series_id) if series_id else None
        title = series.get("title", "") if series else ""
        se = f"S{episode.get('seasonNumber', 0):02d}E{episode.get('episodeNumber', 0):02d}"
        item_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=file_path,
            title=title,
            season_episode=se,
            sonarr_series_id=series_id,
            sonarr_episode_id=episode_id,
            target_language=target_lang,
        )
    else:
        item_id = wanted["id"]

    result = search_providers_for_item(item_id)
    return jsonify(result)


@bp.route("/episodes/<int:episode_id>/download-specific", methods=["POST"])
def episode_download_specific(episode_id):
    """Download a specific subtitle chosen via interactive search (episode view).
    ---
    post:
      tags:
        - Library
      summary: Download specific subtitle for episode
      description: Finds or creates a wanted item for the episode, then downloads the selected subtitle.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: episode_id
          required: true
          schema:
            type: integer
          description: Sonarr episode ID
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [provider_name, subtitle_id, language]
              properties:
                provider_name:
                  type: string
                subtitle_id:
                  type: string
                language:
                  type: string
                translate:
                  type: boolean
                  default: false
      responses:
        200:
          description: Subtitle downloaded
        400:
          description: Validation or download error
        404:
          description: Episode not found or has no file
        503:
          description: Sonarr not configured
    """
    from sonarr_client import get_sonarr_client
    from db.profiles import get_series_profile, get_default_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from wanted_search import download_specific_for_item
    from config import get_settings, map_path
    from events import emit_event

    settings = get_settings()
    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    data = request.get_json() or {}
    provider_name = (data.get("provider_name") or "").strip()
    subtitle_id = (data.get("subtitle_id") or "").strip()
    language = (data.get("language") or "").strip()
    translate = bool(data.get("translate", False))

    if not provider_name or not subtitle_id or not language:
        return jsonify({"error": "provider_name, subtitle_id, and language are required"}), 400

    episode = sonarr.get_episode_by_id(episode_id)
    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    series_id = episode.get("seriesId")
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = profile.get("target_languages", [settings.target_language]) if profile else [settings.target_language]
    target_lang = target_languages[0] if target_languages else settings.target_language

    wanted = find_wanted_by_episode(episode_id, target_lang)
    if not wanted:
        file_path = sonarr.get_episode_file_path(episode_id)
        if not file_path:
            return jsonify({"error": "Episode has no file"}), 404
        file_path = map_path(file_path)
        series = sonarr.get_series_by_id(series_id) if series_id else None
        title = series.get("title", "") if series else ""
        se = f"S{episode.get('seasonNumber', 0):02d}E{episode.get('episodeNumber', 0):02d}"
        item_id, _ = upsert_wanted_item(
            item_type="episode",
            file_path=file_path,
            title=title,
            season_episode=se,
            sonarr_series_id=series_id,
            sonarr_episode_id=episode_id,
            target_language=target_lang,
        )
    else:
        item_id = wanted["id"]

    result = download_specific_for_item(item_id, provider_name, subtitle_id, language, translate)
    if not result.get("success"):
        return jsonify(result), 400

    emit_event("wanted_item_processed", {
        "wanted_id": item_id,
        "episode_id": episode_id,
        "status": "found",
        "output_path": result.get("path"),
        "provider": provider_name,
    })
    return jsonify(result)


@bp.route("/episodes/<int:episode_id>/history", methods=["GET"])
def episode_history(episode_id):
    """Get download/translation history for a specific episode.
    ---
    get:
      tags:
        - Library
      summary: Get episode history
      description: Returns the download and translation history for a specific episode, including provider, format, and timestamps.
      security:
        - apiKeyAuth: []
      parameters:
        - in: path
          name: episode_id
          required: true
          schema:
            type: integer
          description: Sonarr episode ID
      responses:
        200:
          description: Episode history
          content:
            application/json:
              schema:
                type: object
                properties:
                  entries:
                    type: array
                    items:
                      type: object
                      additionalProperties: true
        503:
          description: Sonarr not configured
    """
    from sonarr_client import get_sonarr_client
    from db.cache import get_episode_history
    from config import map_path

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    file_path = sonarr.get_episode_file_path(episode_id)
    if not file_path:
        return jsonify({"entries": []})

    mapped = map_path(file_path)
    entries = get_episode_history(mapped)
    return jsonify({"entries": entries})
