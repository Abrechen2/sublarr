"""Library episodes endpoints — episode search, download, and history."""

import logging

from flask import jsonify, request

from routes.library import bp

logger = logging.getLogger(__name__)


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
    from config import get_settings, map_path
    from db.profiles import get_default_profile, get_series_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from sonarr_client import get_sonarr_client
    from wanted_search import search_wanted_item

    settings = get_settings()

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode = sonarr.get_episode_by_id(episode_id)
    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    series_id = episode.get("seriesId")
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )

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
    from config import get_settings, map_path
    from db.profiles import get_default_profile, get_series_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from sonarr_client import get_sonarr_client
    from wanted_search import search_providers_for_item

    settings = get_settings()
    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    episode = sonarr.get_episode_by_id(episode_id)
    if not episode:
        return jsonify({"error": "Episode not found"}), 404

    series_id = episode.get("seriesId")
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )
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
    from config import get_settings, map_path
    from db.profiles import get_default_profile, get_series_profile
    from db.wanted import find_wanted_by_episode, upsert_wanted_item
    from events import emit_event
    from sonarr_client import get_sonarr_client
    from wanted_search import download_specific_for_item

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
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )
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

    emit_event(
        "wanted_item_processed",
        {
            "wanted_id": item_id,
            "episode_id": episode_id,
            "status": "found",
            "output_path": result.get("path"),
            "provider": provider_name,
        },
    )
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
    from config import map_path
    from db.cache import get_episode_history
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client()
    if not sonarr:
        return jsonify({"error": "Sonarr not configured"}), 503

    file_path = sonarr.get_episode_file_path(episode_id)
    if not file_path:
        return jsonify({"entries": []})

    mapped = map_path(file_path)
    entries = get_episode_history(mapped)
    return jsonify({"entries": entries})
