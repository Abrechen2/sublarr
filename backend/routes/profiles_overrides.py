"""REST API for the Profiles & Overrides Settings page (Codex Template C).

See docs/superpowers/specs/2026-04-25-profiles-overrides-design.md.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from auth import require_api_key
from config import get_settings
from db.models.core import (
    LanguageProfile,
    MovieLanguageProfile,
    MovieSettings,
    SeriesLanguageProfile,
    SeriesSettings,
)
from extensions import db
from services.inheritance_resolver import (
    INHERITABLE_FIELDS,
    _decode,
    resolve_for_movie,
    resolve_for_series,
)

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


# ─── /resolved ───────────────────────────────────────────────────────────────


def _resolved_response(scope_type: str, scope_id, scope_name: str, settings: dict) -> dict:
    return {
        "scope": {"type": scope_type, "id": scope_id, "name": scope_name},
        "settings": settings,
    }


@bp.route("/resolved/global", methods=["GET"])
@require_api_key
def get_resolved_global():
    cfg = get_settings()
    out: dict[str, dict] = {}
    for field in INHERITABLE_FIELDS:
        if field.global_key is None:
            chain: list[dict] = []
            effective = None
            source = "global"
        else:
            raw = getattr(cfg, field.global_key, None)
            decoded = _decode(raw, field.value_kind)
            chain = [{"scope": "global", "value": decoded, "label": "Global default"}]
            effective = decoded
            source = "global"
        out[field.display_name] = {
            "effective": effective,
            "source": source,
            "chain": chain,
        }
    return jsonify(_resolved_response("global", None, "Global default", out))


@bp.route("/resolved/profile/<int:profile_id>", methods=["GET"])
@require_api_key
def get_resolved_profile(profile_id: int):
    profile = LanguageProfile.query.get(profile_id)
    if profile is None:
        return jsonify({"error": "profile not found"}), 404
    cfg = get_settings()
    out: dict[str, dict] = {}
    for field in INHERITABLE_FIELDS:
        chain: list[dict] = []
        if field.global_key is not None:
            raw_global = getattr(cfg, field.global_key, None)
            chain.append({
                "scope": "global",
                "value": _decode(raw_global, field.value_kind),
                "label": "Global default",
            })
        if field.profile_attr is not None:
            raw_profile = getattr(profile, field.profile_attr, None)
            chain.append({
                "scope": "profile",
                "value": _decode(raw_profile, field.value_kind),
                "label": profile.name,
            })
        effective = None
        source = "global"
        for step in reversed(chain):
            if step["value"] is not None:
                effective = step["value"]
                source = step["scope"]
                break
        if effective is None and chain:
            effective = chain[0]["value"]
            source = chain[0]["scope"]
        out[field.display_name] = {"effective": effective, "source": source, "chain": chain}
    return jsonify(_resolved_response("profile", profile_id, profile.name, out))


@bp.route("/resolved/series/<int:series_id>", methods=["GET"])
@require_api_key
def get_resolved_series(series_id: int):
    # Require at least a profile mapping or series settings row to prove the
    # series is known to Sublarr. A missing `series` table row (title lookup)
    # is tolerated — Sonarr sync may not have run yet.
    mapping = SeriesLanguageProfile.query.filter_by(sonarr_series_id=series_id).first()
    series = SeriesSettings.query.get(series_id)
    if mapping is None and series is None:
        return jsonify({"error": "series not found"}), 404

    # Best-effort title resolution; degrade to "#<id>" when table absent.
    from sqlalchemy import text

    try:
        title_row = db.session.execute(
            text("SELECT title FROM series WHERE sonarr_series_id = :id"),
            {"id": series_id},
        ).fetchone()
        title = title_row[0] if title_row else f"#{series_id}"
    except Exception:
        title = f"#{series_id}"

    profile = LanguageProfile.query.get(mapping.profile_id) if mapping else None
    cfg = get_settings()
    settings = resolve_for_series(series=series, profile=profile, global_cfg=cfg)
    return jsonify(_resolved_response("series", series_id, title, settings))


@bp.route("/resolved/movie/<int:movie_id>", methods=["GET"])
@require_api_key
def get_resolved_movie(movie_id: int):
    mapping = MovieLanguageProfile.query.filter_by(radarr_movie_id=movie_id).first()
    movie = MovieSettings.query.get(movie_id)
    if mapping is None and movie is None:
        return jsonify({"error": "movie not found"}), 404

    from sqlalchemy import text

    try:
        title_row = db.session.execute(
            text("SELECT title FROM movies WHERE radarr_movie_id = :id"),
            {"id": movie_id},
        ).fetchone()
        title = title_row[0] if title_row else f"#{movie_id}"
    except Exception:
        title = f"#{movie_id}"

    profile = LanguageProfile.query.get(mapping.profile_id) if mapping else None
    cfg = get_settings()
    settings = resolve_for_movie(movie=movie, profile=profile, global_cfg=cfg)
    return jsonify(_resolved_response("movie", movie_id, title, settings))
