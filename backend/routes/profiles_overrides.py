"""REST API for the Profiles & Overrides Settings page (Codex Template C).

See docs/superpowers/specs/2026-04-25-profiles-overrides-design.md.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

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
from schemas.profiles_overrides import OverridePatch
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

    # Sublarr does not maintain a master `series` / `movies` table — Sonarr
    # and Radarr own that. We aggregate every series/movie that has *any*
    # touchpoint in Sublarr's own DB: cached searches, wanted items,
    # per-series/movie settings, profile mappings, or standalone library
    # entries. For titles we prefer search_series.title / standalone_*.title
    # when present, otherwise we fall back to a `#<id>` placeholder.
    from sqlalchemy import text

    def _safe_query(sql: str) -> list:
        try:
            return list(db.session.execute(text(sql)).all())
        except Exception:
            return []

    series_id_titles: dict[int, str] = {}
    # search_series: id is the sonarr_series_id, populated whenever a search
    # for an episode of that series ran. Title is the cached display name.
    for row in _safe_query("SELECT id, title FROM search_series"):
        sid, title = int(row[0]), str(row[1] or "")
        # Strip episode-tail like " — S01E01 [DE]" if present.
        clean = title.split(" — ")[0] if " — " in title else title
        series_id_titles.setdefault(sid, clean or f"#{sid}")
    # standalone_series: manual library entries with their own id + title.
    for row in _safe_query("SELECT id, title FROM standalone_series"):
        sid, title = int(row[0]), str(row[1] or "")
        series_id_titles.setdefault(sid, title or f"#{sid}")
    # Pure-id sources — no title, only existence. Used to surface series that
    # have settings or wanted items even if no search ever ran.
    for sql in (
        "SELECT DISTINCT sonarr_series_id FROM wanted_items WHERE sonarr_series_id IS NOT NULL",
        "SELECT DISTINCT sonarr_series_id FROM series_settings",
    ):
        for row in _safe_query(sql):
            sid = int(row[0])
            series_id_titles.setdefault(sid, f"#{sid}")
    # Mapping table itself — make sure assigned IDs always show up.
    for sid in assigned_series_ids:
        series_id_titles.setdefault(sid, f"#{sid}")

    movie_id_titles: dict[int, str] = {}
    for row in _safe_query("SELECT id, title FROM standalone_movies"):
        mid, title = int(row[0]), str(row[1] or "")
        movie_id_titles.setdefault(mid, title or f"#{mid}")
    for sql in (
        "SELECT DISTINCT radarr_movie_id FROM wanted_items WHERE radarr_movie_id IS NOT NULL",
        "SELECT DISTINCT radarr_movie_id FROM movie_settings",
    ):
        for row in _safe_query(sql):
            mid = int(row[0])
            movie_id_titles.setdefault(mid, f"#{mid}")
    for mid in assigned_movie_ids:
        movie_id_titles.setdefault(mid, f"#{mid}")

    series_titles = series_id_titles
    movie_titles = movie_id_titles

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
            chain.append(
                {
                    "scope": "global",
                    "value": _decode(raw_global, field.value_kind),
                    "label": "Global default",
                }
            )
        if field.profile_attr is not None:
            raw_profile = getattr(profile, field.profile_attr, None)
            chain.append(
                {
                    "scope": "profile",
                    "value": _decode(raw_profile, field.value_kind),
                    "label": profile.name,
                }
            )
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


# ─── PATCH /series/<id> ─────────────────────────────────────────────────────
_SERIES_ONLY_FIELDS = {
    "cleanup_foreign_tracks",
    "preferred_audio_track_index",
    "priority_override",
    "min_attempts_per_day",
}


def _column_name_for_field(display_name: str) -> str:
    """Map display_name to the actual override column name."""
    for field in INHERITABLE_FIELDS:
        if field.display_name == display_name:
            return field.override_col
    raise KeyError(display_name)


def _serialize_for_storage(field: str, value) -> object:
    """JSON-encode list values, return scalars as-is."""
    if value is None:
        return None
    if isinstance(value, list):
        import json

        return json.dumps(value)
    return value


@bp.route("/series/<int:series_id>", methods=["PATCH"])
@require_api_key
def patch_series(series_id: int):
    try:
        patch = OverridePatch.model_validate(request.get_json() or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 422

    ss = SeriesSettings.query.get(series_id)
    if ss is None:
        ss = SeriesSettings(
            sonarr_series_id=series_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ss)

    for field_name, value in patch.changes.items():
        col = _column_name_for_field(field_name)
        setattr(ss, col, _serialize_for_storage(field_name, value))
    ss.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/movie/<int:movie_id>", methods=["PATCH"])
@require_api_key
def patch_movie(movie_id: int):
    try:
        patch = OverridePatch.model_validate(request.get_json() or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 422

    ms = MovieSettings.query.get(movie_id)
    if ms is None:
        ms = MovieSettings(
            radarr_movie_id=movie_id,
            updated_at=datetime.now(UTC),
        )
        db.session.add(ms)

    for field_name, value in patch.changes.items():
        col = _column_name_for_field(field_name)
        setattr(ms, col, _serialize_for_storage(field_name, value))
    ms.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/series/<int:series_id>/reset", methods=["POST"])
@require_api_key
def reset_series(series_id: int):
    ss = SeriesSettings.query.get(series_id)
    if ss is None:
        return jsonify({"ok": True})  # nothing to reset
    for field in INHERITABLE_FIELDS:
        if hasattr(ss, field.override_col) and field.display_name not in {"min_attempts_per_day"}:
            setattr(ss, field.override_col, None)
    ss.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/movie/<int:movie_id>/reset", methods=["POST"])
@require_api_key
def reset_movie(movie_id: int):
    ms = MovieSettings.query.get(movie_id)
    if ms is None:
        return jsonify({"ok": True})
    for field in INHERITABLE_FIELDS:
        if hasattr(ms, field.override_col) and field.display_name not in {"min_attempts_per_day"}:
            setattr(ms, field.override_col, None)
    ms.updated_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"ok": True})
