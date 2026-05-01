"""Library list endpoint — GET /library."""

import logging

from flask import jsonify

from routes.library import bp

logger = logging.getLogger(__name__)

# Directory names commonly used by media servers / scrapers for extras that
# are NOT the main movie file. When a standalone-scanned movie's file_path
# lives under one of these segments, the entry is almost always a sample,
# trailer, or featurette and should be excluded from the library list. Path-
# based detection replaces the older title-blacklist approach which produced
# false positives on real movies literally titled "Movie", "Sample", etc.
_EXTRAS_PATH_MARKERS = frozenset(
    {
        "sample",
        "samples",
        "trailer",
        "trailers",
        "featurette",
        "featurettes",
        "extras",
        "extra",
        "behind the scenes",
        "deleted scenes",
        "interviews",
        "bonus",
        "bonus features",
    }
)


def _looks_like_extras(file_path: str) -> bool:
    """Return True if any path segment matches an extras-folder convention."""
    if not file_path:
        return False
    normalised = file_path.replace("\\", "/").lower()
    for segment in normalised.split("/"):
        if segment.strip() in _EXTRAS_PATH_MARKERS:
            return True
    return False


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
    sonarr_returned = False
    radarr_returned = False

    try:
        from sonarr_client import get_sonarr_client

        sonarr = get_sonarr_client()
        if sonarr:
            series_list = sonarr.get_library_info(anime_only=False)
            sonarr_returned = bool(series_list)
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
            radarr_movies = radarr.get_library_info(anime_only=False)
            radarr_returned = bool(radarr_movies)
            result["movies"] = radarr_movies
    except Exception as e:
        logger.warning("Failed to get Radarr library: %s", e)

    # Augment with standalone data on a per-side basis. Previously this branch
    # only fired when BOTH Sonarr and Radarr returned empty, which silently
    # dropped standalone movies in mixed deployments (e.g. Sonarr-managed
    # series + standalone-scan a separate movie folder). Now each side falls
    # back independently so a Sonarr-only or Radarr-only setup keeps the other
    # side populated from standalone.
    need_standalone_series = not sonarr_returned
    need_standalone_movies = not radarr_returned
    if need_standalone_series or need_standalone_movies:
        try:
            from sqlalchemy import text

            from config import is_standalone_mode
            from db import get_db
            from db.profiles import get_default_profile
            from db.standalone import get_standalone_movies, get_standalone_series

            if is_standalone_mode():
                default_profile = get_default_profile()
                profile_id = default_profile.get("id", 0) if default_profile else 0
                profile_name = (
                    default_profile.get("name", "Default") if default_profile else "Default"
                )

                db = get_db()

                if need_standalone_series:
                    series_missing_rows = db.execute(
                        text(
                            "SELECT standalone_series_id, COUNT(*) FROM wanted_items "
                            "WHERE standalone_series_id IS NOT NULL AND status='wanted' "
                            "GROUP BY standalone_series_id"
                        )
                    ).fetchall()
                    series_missing_map = {row[0]: row[1] for row in series_missing_rows}

                    for s in get_standalone_series():
                        # Use the API endpoint for local posters (browser can't load file:// URLs)
                        poster = (
                            f"/api/v1/standalone/series/{s['id']}/poster"
                            if s.get("poster_url")
                            else ""
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
                                "missing_count": series_missing_map.get(s["id"], 0),
                                "source": "standalone",
                            }
                        )

                if need_standalone_movies:
                    movie_missing_rows = db.execute(
                        text(
                            "SELECT standalone_movie_id, COUNT(*) FROM wanted_items "
                            "WHERE standalone_movie_id IS NOT NULL AND status='wanted' "
                            "GROUP BY standalone_movie_id"
                        )
                    ).fetchall()
                    movie_missing_map = {row[0]: row[1] for row in movie_missing_rows}

                    for m in get_standalone_movies():
                        title = m.get("title", "")
                        if not title:
                            continue
                        # Path-based heuristic — skip files that live under
                        # extras directories (Sample/Trailer/Featurette/...).
                        # Replaces the older title-blacklist that rejected real
                        # movies literally titled "Movie" / "Sample" / etc.
                        if _looks_like_extras(m.get("file_path", "")):
                            continue
                        movie_poster = (
                            f"/api/v1/standalone/movies/{m['id']}/poster"
                            if m.get("poster_url")
                            else ""
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
                                "missing_count": movie_missing_map.get(m["id"], 0),
                                "source": "standalone",
                            }
                        )
        except Exception as e:
            logger.warning("Failed to get standalone library: %s", e)

    return jsonify(result)
