"""Library list endpoint — GET /library."""

import logging

from flask import jsonify

from routes.library import bp

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
    from db.profiles import get_default_profile, get_series_profile_map
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
                    s["profile_name"] = (
                        default_profile.get("name", "Default") if default_profile else "Default"
                    )
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

    # If no Sonarr/Radarr data, fall back to standalone series/movies
    if not result["series"] and not result["movies"]:
        try:
            from sqlalchemy import text

            from config import get_settings
            from db import get_db
            from db.profiles import get_default_profile
            from db.standalone import get_standalone_movies, get_standalone_series

            settings = get_settings()
            if getattr(settings, "standalone_enabled", False):
                default_profile = get_default_profile()
                profile_id = default_profile.get("id", 0) if default_profile else 0
                profile_name = (
                    default_profile.get("name", "Default") if default_profile else "Default"
                )

                db = get_db()

                for s in get_standalone_series():
                    row = db.execute(
                        text(
                            "SELECT COUNT(*) FROM wanted_items WHERE standalone_series_id=:sid AND status='wanted'"
                        ),
                        {"sid": s["id"]},
                    ).fetchone()
                    # Use the API endpoint for local posters (browser can't load file:// URLs)
                    poster = (
                        f"/api/v1/standalone/series/{s['id']}/poster" if s.get("poster_url") else ""
                    )
                    result["series"].append(
                        {
                            "id": s["id"],
                            "title": s["title"],
                            "year": s.get("year"),
                            "seasons": s.get("season_count") or 0,
                            "episodes": s.get("episode_count") or 0,
                            "episodes_with_files": s.get("episode_count") or 0,
                            "path": s.get("folder_path", ""),
                            "poster": poster,
                            "status": "continuing",
                            "profile_id": profile_id,
                            "profile_name": profile_name,
                            "missing_count": row[0] if row else 0,
                            "source": "standalone",
                        }
                    )

                for m in get_standalone_movies():
                    # Skip misidentified entries (files inside series folders)
                    title = m.get("title", "")
                    if not title or title.lower() in (
                        "tvshow",
                        "movie",
                        "trailer",
                        "featurette",
                        "sample",
                    ):
                        continue
                    row = db.execute(
                        text(
                            "SELECT COUNT(*) FROM wanted_items WHERE standalone_movie_id=:mid AND status='wanted'"
                        ),
                        {"mid": m["id"]},
                    ).fetchone()
                    movie_poster = (
                        f"/api/v1/standalone/movies/{m['id']}/poster" if m.get("poster_url") else ""
                    )
                    result["movies"].append(
                        {
                            "id": m["id"],
                            "title": title,
                            "year": m.get("year"),
                            "has_file": True,
                            "path": m.get("file_path", ""),
                            "poster": movie_poster,
                            "status": "released",
                            "missing_count": row[0] if row else 0,
                            "source": "standalone",
                        }
                    )
        except Exception as e:
            logger.warning("Failed to get standalone library: %s", e)

    return jsonify(result)
