"""Library episodes endpoints — episode search, download, and history."""

import logging

from flask import jsonify, request

from routes.library import bp

logger = logging.getLogger(__name__)


def _get_or_create_episode_wanted(
    sonarr, episode: dict, episode_id: int, target_lang: str
) -> tuple[int | None, object | None]:
    """Find or create a WantedItem for a Sonarr episode.

    Returns (item_id, None) on success or (None, flask_response) when the episode
    has no file and a 404 should be returned to the caller.
    """
    from config import map_path
    from db.wanted import find_wanted_by_episode, upsert_wanted_item

    wanted = find_wanted_by_episode(episode_id, target_lang)
    if wanted:
        return wanted["id"], None

    file_path = sonarr.get_episode_file_path(episode_id)
    if not file_path:
        return None, (jsonify({"error": "Episode has no file"}), 404)

    file_path = map_path(file_path)
    series_id = episode.get("seriesId")
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
    return item_id, None


def _sonarr_target_language(series_id) -> str:
    """First target language of the series' profile (default profile fallback)."""
    from config import get_settings
    from db.profiles import get_default_profile, get_series_profile

    settings = get_settings()
    profile = get_series_profile(series_id) if series_id else get_default_profile()
    target_languages = (
        profile.get("target_languages", [settings.target_language])
        if profile
        else [settings.target_language]
    )
    return target_languages[0] if target_languages else settings.target_language


def _resolve_episode_wanted_id(episode_id: int) -> tuple[int | None, object | None]:
    """Resolve an episode id to the wanted item that search/download operate on.

    Sonarr mode: ``episode_id`` is a Sonarr episode id. Standalone mode (no
    Sonarr client, same rule as the series detail): it is the standalone
    ``wanted_items`` row id, or a negative synthetic id plus a ``file_path``
    query parameter for an episode with no wanted row yet (#226).

    Returns ``(item_id, None)`` or ``(None, flask_response)``.
    """
    from sonarr_client import get_sonarr_client

    # A negative id is a standalone episode whatever is configured; a
    # positive one without Sonarr is the legacy standalone wanted-row id.
    sonarr = get_sonarr_client() if episode_id > 0 else None
    if not sonarr:
        from services.standalone_episode import (
            StandaloneEpisodeNotFoundError,
            resolve_standalone_episode_wanted_id,
        )

        try:
            return resolve_standalone_episode_wanted_id(
                episode_id, request.args.get("file_path") or None
            ), None
        except StandaloneEpisodeNotFoundError:
            return None, (jsonify({"error": "Episode not found"}), 404)

    episode = sonarr.get_episode_by_id(episode_id) if episode_id > 0 else None
    if not episode:
        return None, (jsonify({"error": "Episode not found"}), 404)

    target_lang = _sonarr_target_language(episode.get("seriesId"))
    return _get_or_create_episode_wanted(sonarr, episode, episode_id, target_lang)


@bp.route("/episodes/<int(signed=True):episode_id>/search", methods=["POST"])
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
          description: Sonarr episode ID, or a negative standalone episode ID (a positive ID without Sonarr is read as a standalone wanted item ID)
        - in: query
          name: file_path
          required: false
          schema:
            type: string
          description: Standalone mode only — the episode's video path, used when the ID has no wanted item
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
    """
    from wanted_search import search_wanted_item

    item_id, err = _resolve_episode_wanted_id(episode_id)
    if err:
        return err

    result = search_wanted_item(item_id)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)


@bp.route("/episodes/<int(signed=True):episode_id>/search-providers", methods=["GET"])
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
          description: Sonarr episode ID, or a negative standalone episode ID (a positive ID without Sonarr is read as a standalone wanted item ID)
        - in: query
          name: file_path
          required: false
          schema:
            type: string
          description: Standalone mode only — the episode's video path, used when the ID has no wanted item
      responses:
        200:
          description: All provider results
        404:
          description: Episode not found or has no file
    """
    from wanted_search import search_providers_for_item

    item_id, err = _resolve_episode_wanted_id(episode_id)
    if err:
        return err

    all_providers = request.args.get("all_providers", "").lower() in ("1", "true", "yes")
    result = search_providers_for_item(item_id, all_providers=all_providers)
    return jsonify(result)


@bp.route("/episodes/<int(signed=True):episode_id>/download-specific", methods=["POST"])
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
          description: Sonarr episode ID, or a negative standalone episode ID (a positive ID without Sonarr is read as a standalone wanted item ID)
        - in: query
          name: file_path
          required: false
          schema:
            type: string
          description: Standalone mode only — the episode's video path, used when the ID has no wanted item
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
    """
    from events import emit_event
    from wanted_search import download_specific_for_item

    data = request.get_json() or {}
    provider_name = (data.get("provider_name") or "").strip()
    subtitle_id = (data.get("subtitle_id") or "").strip()
    language = (data.get("language") or "").strip()
    translate = bool(data.get("translate", False))

    if not provider_name or not subtitle_id or not language:
        return jsonify({"error": "provider_name, subtitle_id, and language are required"}), 400

    item_id, err = _resolve_episode_wanted_id(episode_id)
    if err:
        return err

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


@bp.route("/episodes/<int(signed=True):episode_id>/history", methods=["GET"])
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
          description: Sonarr episode ID, or a negative standalone episode ID (a positive ID without Sonarr is read as a standalone wanted item ID)
        - in: query
          name: file_path
          required: false
          schema:
            type: string
          description: Standalone mode only — the episode's video path, used when the ID has no wanted item
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
    """
    from config import map_path
    from db.cache import get_episode_history
    from sonarr_client import get_sonarr_client

    sonarr = get_sonarr_client() if episode_id > 0 else None
    if not sonarr:
        # Standalone (#226): the stable negative episode id, the legacy wanted
        # row id, or a 1.17.3 stand-in id + file_path. Read-only — never
        # creates a wanted row.
        from services.standalone_episode import resolve_standalone_episode_file

        file_path = resolve_standalone_episode_file(
            episode_id, request.args.get("file_path") or None
        )
        return jsonify({"entries": get_episode_history(file_path) if file_path else []})

    file_path = sonarr.get_episode_file_path(episode_id) if episode_id > 0 else None
    if not file_path:
        return jsonify({"entries": []})

    mapped = map_path(file_path)
    entries = get_episode_history(mapped)
    return jsonify({"entries": entries})
