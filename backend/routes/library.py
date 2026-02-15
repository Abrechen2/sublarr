"""Library routes — /library, /sonarr/*, /radarr/*, /episodes/*."""

import logging
from flask import Blueprint, request, jsonify

bp = Blueprint("library", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@bp.route("/library", methods=["GET"])
def get_library():
    """Get series/movies with subtitle status, profile assignments, and missing counts."""
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
    """Get all configured Sonarr instances."""
    from config import get_sonarr_instances
    instances = get_sonarr_instances()
    return jsonify(instances)


@bp.route("/radarr/instances", methods=["GET"])
def get_radarr_instances():
    """Get all configured Radarr instances."""
    from config import get_radarr_instances
    instances = get_radarr_instances()
    return jsonify(instances)


@bp.route("/sonarr/instances/test", methods=["POST"])
def test_sonarr_instance():
    """Test connection to a Sonarr instance."""
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
    """Test connection to a Radarr instance."""
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
    """Get detailed series info with episodes and subtitle status."""
    from sonarr_client import get_sonarr_client
    from translator import detect_existing_target_for_lang
    from db.profiles import get_series_profile, get_default_profile
    from config import get_settings, map_path

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

    # Get all episodes
    episodes_raw = sonarr.get_episodes(series_id)

    episodes = []
    for ep in episodes_raw:
        has_file = ep.get("hasFile", False)
        file_path = None
        subtitles = {}

        if has_file:
            ep_file = ep.get("episodeFile")
            if ep_file:
                file_path = ep_file.get("path")

            if file_path:
                mapped = map_path(file_path)
                for lang in target_languages:
                    existing = detect_existing_target_for_lang(mapped, lang)
                    subtitles[lang] = existing or ""

        # Audio language from episode file
        audio_languages = []
        ep_file = ep.get("episodeFile")
        if ep_file:
            media_info = ep_file.get("mediaInfo", {})
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

    return jsonify({
        "id": series.get("id"),
        "title": series.get("title", ""),
        "year": series.get("year"),
        "path": series.get("path", ""),
        "poster": poster,
        "fanart": fanart,
        "overview": series.get("overview", ""),
        "status": series.get("status", ""),
        "season_count": series.get("seasonCount", 0),
        "episode_count": series.get("episodeCount", 0),
        "episode_file_count": series.get("episodeFileCount", 0),
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

    Finds or creates a wanted item, then runs provider search.
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
        item_id = upsert_wanted_item(
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


@bp.route("/episodes/<int:episode_id>/history", methods=["GET"])
def episode_history(episode_id):
    """Get download/translation history for a specific episode."""
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
