"""REST API for the Profiles & Overrides Settings page (Codex Template C).

See docs/superpowers/specs/2026-04-25-profiles-overrides-design.md.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from auth import require_api_key
from db.models.core import (
    LanguageProfile,
    MovieLanguageProfile,
    SeriesLanguageProfile,
)
from extensions import db

bp = Blueprint("profiles_overrides", __name__, url_prefix="/api/v1/profiles-overrides")


# ─── /scopes ─────────────────────────────────────────────────────────────────


@bp.route("/scopes", methods=["GET"])
@require_api_key
def get_scopes():
    """Return the full scope tree: every profile with its assigned series
    and movies, plus the 'unassigned' bucket for items with no profile."""
    profiles = LanguageProfile.query.order_by(
        LanguageProfile.is_default.desc(), LanguageProfile.name
    ).all()

    # Build profile_id → list of series/movies via the mapping tables.
    series_map = SeriesLanguageProfile.query.all()
    movie_map = MovieLanguageProfile.query.all()
    series_by_profile: dict[int, list[int]] = {}
    movie_by_profile: dict[int, list[int]] = {}
    assigned_series_ids: set[int] = set()
    assigned_movie_ids: set[int] = set()
    for m in series_map:
        series_by_profile.setdefault(m.profile_id, []).append(m.sonarr_series_id)
        assigned_series_ids.add(m.sonarr_series_id)
    for m in movie_map:
        movie_by_profile.setdefault(m.profile_id, []).append(m.radarr_movie_id)
        assigned_movie_ids.add(m.radarr_movie_id)

    # Resolve series/movie titles via the existing library tables.
    # Both tables are populated by Sonarr/Radarr sync and may be absent on
    # fresh installs or in test environments — degrade gracefully.
    from sqlalchemy import text

    try:
        title_rows = db.session.execute(
            text("SELECT sonarr_series_id, title FROM series")
        ).all()
        series_titles = {r[0]: r[1] for r in title_rows}
    except Exception:
        series_titles = {}  # series table absent (fresh install / test)
    try:
        movie_rows = db.session.execute(
            text("SELECT radarr_movie_id, title FROM movies")
        ).all()
        movie_titles = {r[0]: r[1] for r in movie_rows}
    except Exception:
        movie_titles = {}  # movies table absent (fresh install / test)

    def _entries(ids: list[int], titles: dict[int, str]) -> list[dict]:
        return [{"id": i, "title": titles.get(i, f"#{i}")} for i in ids]

    profile_nodes = []
    for p in profiles:
        profile_nodes.append(
            {
                "id": p.id,
                "name": p.name,
                "is_default": bool(p.is_default),
                "series": _entries(series_by_profile.get(p.id, []), series_titles),
                "movies": _entries(movie_by_profile.get(p.id, []), movie_titles),
            }
        )

    unassigned_series = _entries(
        [sid for sid in series_titles if sid not in assigned_series_ids],
        series_titles,
    )
    unassigned_movies = _entries(
        [mid for mid in movie_titles if mid not in assigned_movie_ids],
        movie_titles,
    )

    return jsonify(
        {
            "profiles": profile_nodes,
            "unassigned_series": unassigned_series,
            "unassigned_movies": unassigned_movies,
        }
    )
